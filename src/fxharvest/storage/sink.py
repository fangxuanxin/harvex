"""Sink：数据出口抽象接口。

存储策略「先 SQLite，签名预留抽象」——当前只有 SQLiteSink 一个实现，
但 pipeline 只依赖这里的抽象签名，将来要接其它出口（CSV / 远端）只需新增实现。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..core.record import HarvestRecord


@dataclass(frozen=True)
class WriteResult:
    """一次写库的结果统计。"""

    source_slug: str        # 本次写入对应的源
    received: int           # 收到的记录条数
    inserted: int           # 新插入条数
    updated: int            # upsert 命中更新条数
    total_after: int        # 写入后该业务库总记录数


class Sink(ABC):
    """数据出口抽象。实现需保证：写前备份策略、upsert 去重、字段收口落库。"""

    @abstractmethod
    def write(self, records: list[HarvestRecord], *, source_slug: str) -> WriteResult:
        """把一批已校验记录写入出口；按 record.dedup_keys 做 upsert 去重。"""

    @abstractmethod
    def total_count(self) -> int:
        """返回业务库当前总记录数。"""


__all__ = ["Sink", "WriteResult"]
