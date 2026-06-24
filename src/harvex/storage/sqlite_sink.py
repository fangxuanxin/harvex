"""sqlite_sink.py：SQLite 落地实现，满足 Sink 抽象契约。

核心职责：
1. 初始化时建立 HarvexDatabase，推导 SchemaSpec，ensure_table（幂等）。
2. write()：to_row() 转行 → upsert → 可选 backup → 返回 WriteResult。
3. backup 开关：backup=True 时每次 write 后备份；
   backup=False 走快路径（runner 可在轮次前统一备份一次）。
4. total_count()：委托给 HarvexDatabase.count()。
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ..core.errors import SinkError
from ..core.record import HarvestRecord
from .database import HarvexDatabase
from .schema import SchemaSpec, build_schema
from .sink import Sink, WriteResult


class SQLiteSink(Sink):
    """SQLite 数据出口，实现 Sink 抽象。

    示例::

        sink = SQLiteSink("jobs.db", JobRecord, table="jobs")
        result = sink.write(records, source_slug="boss")
        print(result.inserted, result.updated)
    """

    def __init__(
        self,
        db_path: str | os.PathLike,
        record_model: type[HarvestRecord],
        *,
        table: str = "records",
        backup: bool = True,
        backup_keep: int = 10,
    ) -> None:
        """初始化 SQLite 出口。

        Args:
            db_path:      SQLite 文件路径，不存在时自动创建。
            record_model: HarvestRecord 子类，用于推导表结构。
            table:        业务表名，默认 "records"。
            backup:       write() 后是否自动备份，默认 True。
            backup_keep:  保留备份份数，默认 10。
        """
        self._record_model = record_model
        self._table = table
        self._do_backup = backup
        self._backup_keep = backup_keep

        # 建立数据库连接
        self._db = HarvexDatabase(db_path)

        # 推导表结构规格
        self._spec: SchemaSpec = build_schema(record_model, table)

        # 幂等建表 + 补列 + 建唯一索引
        self._db.ensure_table(self._spec)

    # ------------------------------------------------------------------
    # Sink 抽象实现
    # ------------------------------------------------------------------

    def write(
        self,
        records: list[HarvestRecord],
        *,
        source_slug: str,
    ) -> WriteResult:
        """把一批已校验记录写入 SQLite，按 dedup_keys 做 upsert 去重。

        流程：
        1. 每条 record 调用 to_row()，其中 extra 已序列化为 JSON 字符串，
           extra 列名取 record_model.extra_column（子类可覆盖）。
        2. 批量调用 HarvexDatabase.upsert()，返回 (inserted, updated)。
        3. backup=True 时调用 HarvexDatabase.backup()（轮级备份时可关闭此开关）。
        4. 构建并返回 WriteResult。

        Args:
            records:     已通过 from_raw 校验的 HarvestRecord 列表。
            source_slug: 本次写入对应的源标识符，记录到 WriteResult。

        Returns:
            WriteResult，含 received / inserted / updated / total_after。
        """
        received = len(records)

        if received == 0:
            return WriteResult(
                source_slug=source_slug,
                received=0,
                inserted=0,
                updated=0,
                total_after=self._db.count(self._spec.table),
            )

        # to_row() 已将 extra 折叠为 JSON 字符串，列名为 extra_column
        rows = [r.to_row() for r in records]

        # 批量 upsert
        inserted, updated = self._db.upsert(self._spec, rows)

        # 可选备份（写后备份，保证备份包含最新数据）
        if self._do_backup:
            self._db.backup(keep=self._backup_keep)

        total_after = self._db.count(self._spec.table)

        return WriteResult(
            source_slug=source_slug,
            received=received,
            inserted=inserted,
            updated=updated,
            total_after=total_after,
        )

    def total_count(self) -> int:
        """返回业务表当前总记录数。"""
        return self._db.count(self._spec.table)

    # ------------------------------------------------------------------
    # 额外暴露的实用接口（非 Sink 契约，但方便直接使用）
    # ------------------------------------------------------------------

    def backup_now(self) -> None:
        """立即执行一次备份（供 runner 在轮次前统一调用）。"""
        self._db.backup(keep=self._backup_keep)

    @property
    def db(self) -> HarvexDatabase:
        """暴露底层 HarvexDatabase，供高级用法（如 query / readonly_connect）。"""
        return self._db

    @property
    def spec(self) -> SchemaSpec:
        """暴露表结构规格，供调试/迁移用。"""
        return self._spec

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def close(self) -> None:
        """关闭底层数据库连接。"""
        self._db.close()

    def __enter__(self) -> "SQLiteSink":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"SQLiteSink(table={self._table!r}, "
            f"model={self._record_model.__name__}, "
            f"db={self._db!r})"
        )


__all__ = ["SQLiteSink"]
