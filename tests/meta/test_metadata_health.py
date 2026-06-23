"""meta 层测试：元数据流水登记 + 数据健康检查。"""

from __future__ import annotations

from fxharvest.core.source import SourceProfile
from fxharvest.meta.health import check_health
from fxharvest.meta.metadata_db import MetadataDatabase


def _meta(tmp_path):
    return MetadataDatabase(str(tmp_path / "meta.db"))


def _profile():
    return SourceProfile(slug="icbc", name="工商银行")


def test_start_finish_and_last_count(tmp_path):
    meta = _meta(tmp_path)
    rid = meta.start_crawl(_profile())
    meta.finish_crawl(rid, status="success", job_count=100, total_job_count=100)
    assert meta.last_count("icbc") == 100
    assert len(meta.recent_runs()) == 1
    assert meta.summaries()[0]["source_slug"] == "icbc"
    meta.close()


def test_consecutive_failures(tmp_path):
    meta = _meta(tmp_path)
    for _ in range(2):
        rid = meta.start_crawl(_profile())
        meta.finish_crawl(rid, status="failed", error_message="boom")
    assert meta.summaries()[0]["consecutive_failures"] == 2
    rid = meta.start_crawl(_profile())
    meta.finish_crawl(rid, status="success", job_count=50, total_job_count=50)
    assert meta.summaries()[0]["consecutive_failures"] == 0
    meta.close()


def test_check_health_zero_drop_ok(tmp_path):
    meta = _meta(tmp_path)
    rid = meta.start_crawl(_profile())
    meta.finish_crawl(rid, status="success", job_count=100, total_job_count=100)

    assert check_health(meta, "icbc", 0).status == "anomaly"       # 归零
    assert check_health(meta, "icbc", 40).status == "anomaly"      # 骤降 60%
    assert check_health(meta, "icbc", 95).status == "ok"           # 正常波动
    meta.close()


def test_check_health_first_run_is_ok(tmp_path):
    meta = _meta(tmp_path)
    # 无历史 → ok
    assert check_health(meta, "newbie", 0).status == "ok"
    meta.close()
