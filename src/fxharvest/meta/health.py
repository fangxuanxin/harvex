"""数据健康检查：识别「静默归零 / 骤降」这类假成功场景。

设计原则：
- 纯函数逻辑，不依赖任何 I/O；MetadataDatabase 作为参数注入。
- drop_ratio 可配置，默认 0.5（环比下降超过 50% 即告警）。
- 首轮（无历史记录）不触发告警，避免误报。
"""

from __future__ import annotations

from dataclasses import dataclass

from .metadata_db import MetadataDatabase


# --------------------------------------------------------------------------- #
#  数据结构
# --------------------------------------------------------------------------- #

@dataclass
class HealthStatus:
    """单次健康检查的结果。

    Attributes:
        source_slug: 数据源唯一标识。
        status:      检查结果：'ok' 或 'anomaly'。
        reason:      人类可读的原因说明（ok 时为空字符串）。
        current:     本轮 job_count（当前值）。
        previous:    上一轮成功的 job_count；首轮时为 None。
    """

    source_slug: str
    status: str           # 'ok' | 'anomaly'
    reason: str
    current: int
    previous: int | None


# --------------------------------------------------------------------------- #
#  核心检查函数
# --------------------------------------------------------------------------- #

def check_health(
    meta: MetadataDatabase,
    source_slug: str,
    current_count: int,
    *,
    drop_ratio: float = 0.5,
) -> HealthStatus:
    """对单个数据源做一次实时健康检查。

    规则（按优先级）：
    1. previous 为 None（首轮）→ ok，不告警。
    2. current == 0 且 previous > 0 → anomaly（数据归零）。
    3. current < previous * (1 - drop_ratio) → anomaly（骤降）。
    4. 其余情况 → ok。

    Args:
        meta:          MetadataDatabase 实例，用于查询历史。
        source_slug:   数据源唯一标识。
        current_count: 本轮实际抓到的条数。
        drop_ratio:    骤降阈值，默认 0.5（环比降幅超过 50% 触发）。

    Returns:
        HealthStatus 实例。
    """
    previous = meta.last_count(source_slug)

    # 首轮：无历史基准，不告警
    if previous is None:
        return HealthStatus(
            source_slug=source_slug,
            status="ok",
            reason="首轮抓取，无历史基准",
            current=current_count,
            previous=None,
        )

    # 归零：当前为 0 但上轮有数据
    if current_count == 0 and previous > 0:
        return HealthStatus(
            source_slug=source_slug,
            status="anomaly",
            reason=f"数据归零（上轮={previous}，本轮=0）",
            current=current_count,
            previous=previous,
        )

    # 骤降：环比降幅超过 drop_ratio
    threshold = previous * (1.0 - drop_ratio)
    if current_count < threshold:
        drop_pct = (1.0 - current_count / previous) * 100
        return HealthStatus(
            source_slug=source_slug,
            status="anomaly",
            reason=(
                f"数据骤降 {drop_pct:.1f}%"
                f"（上轮={previous}，本轮={current_count}，阈值={drop_ratio:.0%}）"
            ),
            current=current_count,
            previous=previous,
        )

    # 正常
    return HealthStatus(
        source_slug=source_slug,
        status="ok",
        reason="",
        current=current_count,
        previous=previous,
    )


def scan_health(
    meta: MetadataDatabase,
    drop_ratio: float = 0.5,
) -> list[HealthStatus]:
    """对所有已知数据源做一次离线批量体检（供 `fxharvest health` 命令使用）。

    以 source_summary.last_job_count 作为"当前值"，与历史成功记录环比。
    注意：此函数反映的是「最近一轮落库状态」，不代表实时抓取结果。

    Args:
        meta:       MetadataDatabase 实例。
        drop_ratio: 骤降阈值，默认 0.5。

    Returns:
        所有数据源的 HealthStatus 列表。
    """
    results: list[HealthStatus] = []
    for summary in meta.summaries():
        slug: str = summary["source_slug"]
        current: int = int(summary["last_job_count"])
        results.append(check_health(meta, slug, current, drop_ratio=drop_ratio))
    return results


__all__ = ["HealthStatus", "check_health", "scan_health"]
