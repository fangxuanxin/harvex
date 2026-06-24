"""Pipeline：单源生命周期编排。

把一个源的一次抓取拆成两个阶段，以兼顾「并发」与「SQLite 单连接不可跨线程写」：

- 采集阶段 collect()：fetch → parse → 校验收口（HarvestRecord.from_raw）。
  只碰网络，不碰数据库，可安全地在线程池里并行跑。
- 落地阶段 persist()：start_crawl → 写库 → 健康检查 → finish_crawl → 异常告警。
  只在主线程串行执行，所有 DB 操作集中于此，彻底回避 sqlite 线程问题。

故障隔离：任一阶段抛错都被收敛成一条 status='failed' 的结果，绝不炸整轮。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..meta.health import HealthStatus, check_health
from ..meta.metadata_db import MetadataDatabase
from ..net.http_client import HttpClient
from ..notify.notifier import Notifier, NullNotifier
from ..obs.logging import get_logger
from ..storage.sink import Sink
from .context import SourceContext
from .source import BaseSource


@dataclass
class CollectOutcome:
    """采集阶段产物：要么有记录，要么有异常（供落地阶段登记）。"""

    source_cls: type[BaseSource]
    records: list = None  # type: ignore[assignment]
    error: Exception | None = None


@dataclass
class SourceResult:
    """单源一次抓取的最终结果。"""

    slug: str
    name: str
    status: str  # success / failed / anomaly
    received: int = 0
    inserted: int = 0
    updated: int = 0
    total_after: int = 0
    error: str | None = None
    health: HealthStatus | None = None


class Pipeline:
    """编排单个源的采集与落地。sink/meta 为共享单连接，落地阶段须串行调用。"""

    def __init__(
        self,
        *,
        sink: Sink,
        meta: MetadataDatabase,
        http: HttpClient,
        drop_ratio: float = 0.5,
        notifier: Notifier | None = None,
        source_config: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.sink = sink
        self.meta = meta
        self.http = http
        self.drop_ratio = drop_ratio
        self.notifier = notifier or NullNotifier()
        self.source_config = source_config or {}

    # ---- 阶段一：采集（线程安全，可并行） ----
    def collect(self, source_cls: type[BaseSource]) -> CollectOutcome:
        profile = source_cls.profile
        logger = get_logger(source=profile.slug)
        try:
            cfg = self.source_config.get(profile.slug, {})
            ctx = SourceContext(profile=profile, http=self.http, logger=logger, config=cfg)
            source = source_cls(ctx)
            logger.info("开始采集")
            records = source.collect()
            logger.info("采集完成，记录数 %d", len(records))
            return CollectOutcome(source_cls=source_cls, records=records)
        except Exception as error:  # noqa: BLE001 故障隔离：任何异常都收敛
            logger.error("采集失败：%s", error)
            return CollectOutcome(source_cls=source_cls, error=error)

    # ---- 阶段二：落地（仅主线程串行调用） ----
    def persist(self, outcome: CollectOutcome) -> SourceResult:
        profile = outcome.source_cls.profile
        module_path = outcome.source_cls.__module__
        run_id = self.meta.start_crawl(profile, module_path=module_path)
        logger = get_logger(run_id=run_id, source=profile.slug)

        # 采集阶段已失败：登记 failed 并返回
        if outcome.error is not None:
            msg = str(outcome.error)
            self.meta.finish_crawl(run_id, status="failed", error_message=msg)
            logger.error("落地跳过（采集已失败）：%s", msg)
            return SourceResult(slug=profile.slug, name=profile.name, status="failed", error=msg)

        records = outcome.records
        try:
            # 健康检查须在 finish_crawl 之前取历史基准
            health = check_health(self.meta, profile.slug, len(records), drop_ratio=self.drop_ratio)
            result = self.sink.write(records, source_slug=profile.slug)
            status = "anomaly" if health.status == "anomaly" else "success"
            self.meta.finish_crawl(
                run_id,
                status=status,
                job_count=result.received,
                total_job_count=result.total_after,
            )
            if status == "anomaly":
                logger.warning("数据健康异常：%s", health.reason)
                self.notifier.notify(
                    "harvex 数据异常",
                    f"{profile.name}（{profile.slug}）：{health.reason}",
                    level="warning",
                )
            else:
                logger.info("落地成功：新增 %d 更新 %d 总计 %d",
                            result.inserted, result.updated, result.total_after)
            return SourceResult(
                slug=profile.slug, name=profile.name, status=status,
                received=result.received, inserted=result.inserted, updated=result.updated,
                total_after=result.total_after, health=health,
            )
        except Exception as error:  # noqa: BLE001
            msg = str(error)
            self.meta.finish_crawl(run_id, status="failed", job_count=len(records), error_message=msg)
            logger.error("落地失败：%s", msg)
            return SourceResult(slug=profile.slug, name=profile.name, status="failed", error=msg)


__all__ = ["Pipeline", "SourceResult", "CollectOutcome"]
