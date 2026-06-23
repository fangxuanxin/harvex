"""core 测试：Pipeline 两阶段 + run_sources 故障隔离/去重/告警/异常检测。

这是框架的集成心脏，用内存级假源验证端到端语义。
"""

from __future__ import annotations

import pytest

from fxharvest import BaseSource, SourceProfile
from fxharvest.core.pipeline import Pipeline
from fxharvest.core.runner import run_sources
from fxharvest.meta.metadata_db import MetadataDatabase
from fxharvest.net.http_client import HttpClient
from fxharvest.storage.sqlite_sink import SQLiteSink


class _RecordingNotifier:
    """记录型假通知器，断言告警是否触发。"""

    def __init__(self):
        self.calls = []

    def notify(self, title, message, *, level="info"):
        self.calls.append((title, message, level))


def _make_pipeline(tmp_path, job_record_cls, notifier):
    sink = SQLiteSink(str(tmp_path / "biz.db"), job_record_cls, table="jobs", backup=False)
    meta = MetadataDatabase(str(tmp_path / "meta.db"))
    return Pipeline(sink=sink, meta=meta, http=HttpClient(), notifier=notifier), sink, meta


def _good_source(record_model, count_holder):
    class GoodSource(BaseSource):
        profile = SourceProfile(slug="good", name="正常源")
        record_model = None  # 占位，下面赋值
        def fetch(self):
            return [{"职位名称": f"岗位{i}", "公司": "A"} for i in range(count_holder["n"])]
        def parse(self, raw):
            yield from raw
    GoodSource.record_model = record_model
    return GoodSource


def _broken_source(record_model):
    class BrokenSource(BaseSource):
        profile = SourceProfile(slug="broken", name="故障源")
        record_model = None
        def fetch(self):
            raise RuntimeError("模拟网络炸了")
        def parse(self, raw):
            return []
    BrokenSource.record_model = record_model
    return BrokenSource


def test_fault_isolation_and_dedup(tmp_path, job_record_cls):
    notifier = _RecordingNotifier()
    pipe, sink, meta = _make_pipeline(tmp_path, job_record_cls, notifier)
    holder = {"n": 3}
    sources = [_good_source(job_record_cls, holder), _broken_source(job_record_cls)]

    report = run_sources(sources, pipe, max_workers=2)
    assert len(report.succeeded) == 1
    assert len(report.failed) == 1           # 故障源被隔离，不炸整轮
    assert sink.total_count() == 3
    assert notifier.calls                     # 有失败 → 触发告警

    # 第二轮：good 源数据不变 → 全部 upsert 更新
    report2 = run_sources(sources, pipe, max_workers=2)
    good = next(r for r in report2.results if r.slug == "good")
    assert good.inserted == 0 and good.updated == 3
    assert sink.total_count() == 3
    sink.close(); meta.close()


def test_anomaly_detection_on_zero(tmp_path, job_record_cls):
    notifier = _RecordingNotifier()
    pipe, sink, meta = _make_pipeline(tmp_path, job_record_cls, notifier)
    holder = {"n": 10}
    good = _good_source(job_record_cls, holder)

    run_sources([good], pipe, max_workers=1)      # 首轮 10 条，建立基准
    holder["n"] = 0                                # 第二轮归零
    report = run_sources([good], pipe, max_workers=1)

    assert len(report.anomalies) == 1              # 归零被识别为异常
    assert any("异常" in m or "归零" in m for _, m, _ in notifier.calls)
    sink.close(); meta.close()
