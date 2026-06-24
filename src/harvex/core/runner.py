"""Runner：多源并发统筹（等价招聘项目的 run_all，但解耦且更稳）。

流程：
1. 轮级备份一次（而非每源每次写都备份，避免并发放大磁盘 IO）。
2. 线程池并行执行各源的采集阶段（网络密集，并行收益最大）。
3. 主线程串行执行落地阶段（DB 操作集中，回避 sqlite 线程问题）。
4. 汇总结果；若有 failed/anomaly，统一推一条告警。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from ..obs.logging import get_logger
from .pipeline import Pipeline, SourceResult
from .source import BaseSource


@dataclass
class RunReport:
    """一轮抓取的汇总报告。"""

    results: list[SourceResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def succeeded(self) -> list[SourceResult]:
        return [r for r in self.results if r.status == "success"]

    @property
    def failed(self) -> list[SourceResult]:
        return [r for r in self.results if r.status == "failed"]

    @property
    def anomalies(self) -> list[SourceResult]:
        return [r for r in self.results if r.status == "anomaly"]

    def summary_line(self) -> str:
        return (f"共 {self.total} 源：成功 {len(self.succeeded)}、"
                f"异常 {len(self.anomalies)}、失败 {len(self.failed)}")


def run_sources(
    source_classes: list[type[BaseSource]],
    pipeline: Pipeline,
    *,
    max_workers: int = 4,
    backup_before: bool = True,
) -> RunReport:
    """跑一轮：并行采集 + 串行落地 + 汇总 + 失败告警。"""
    logger = get_logger()
    if not source_classes:
        logger.warning("没有可运行的数据源")
        return RunReport()

    # 1. 轮级备份（若 sink 支持 backup_now）
    if backup_before and hasattr(pipeline.sink, "backup_now"):
        try:
            pipeline.sink.backup_now()  # type: ignore[attr-defined]
            logger.info("轮级备份完成")
        except Exception as error:  # noqa: BLE001 备份失败不应阻断抓取
            logger.error("轮级备份失败（继续抓取）：%s", error)

    # 2. 并行采集
    logger.info("开始抓取 %d 个源（并发 %d）", len(source_classes), max_workers)
    outcomes = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(pipeline.collect, cls): cls for cls in source_classes}
        for fut in as_completed(futures):
            outcomes.append(fut.result())  # collect 不抛，已收敛

    # 3. 串行落地（主线程，保证 DB 单线程访问）
    report = RunReport()
    for outcome in outcomes:
        report.results.append(pipeline.persist(outcome))

    # 4. 汇总 + 告警
    logger.info(report.summary_line())
    problems = report.failed + report.anomalies
    if problems:
        detail = "\n".join(f"- {r.name}（{r.slug}）：{r.status} {r.error or (r.health.reason if r.health else '')}"
                           for r in problems)
        pipeline.notifier.notify(
            "harvex 抓取告警",
            f"{report.summary_line()}\n{detail}",
            level="error" if report.failed else "warning",
        )
    return report


__all__ = ["run_sources", "RunReport"]
