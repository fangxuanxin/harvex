"""fxdb.py：数据基座（泛化自 fxdb 哲学）。

所有读写路径均经过 FxDatabase，职责：
1. 建立 WAL 模式 SQLite 连接（提升并发读性能）。
2. ensure_table：建表 + 缺列自动补列（幂等，支持字段扩充）。
3. upsert：按 dedup_keys 做 INSERT ... ON CONFLICT DO UPDATE；
           空 dedup_keys 时纯 INSERT；维护 created_at / updated_at。
4. count：快速获取表总行数。
5. backup：sqlite3 在线备份 API，保留最近 keep 份，多余删除。
6. query：通用只读查询入口。
7. readonly_connect：返回只读 URI 连接，供外部只读访问。
8. 所有异常统一包装为 SinkError。
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.errors import SinkError
from .schema import SchemaSpec


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串（精确到秒）。"""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FxDatabase:
    """SQLite 数据基座，提供建表、upsert、查询、备份等完整生命周期管理。

    上下文管理器示例::

        with FxDatabase("jobs.db") as db:
            db.ensure_table(spec)
            db.upsert(spec, rows)
    """

    def __init__(self, db_path: str | os.PathLike) -> None:
        """建立 SQLite 连接，启用 WAL 模式与 Row 工厂。

        Args:
            db_path: 数据库文件路径，不存在时自动创建。
        """
        self._path = Path(db_path).resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = sqlite3.connect(str(self._path))
            self._conn.row_factory = sqlite3.Row
            # WAL 模式：写不阻塞读，适合单进程多线程场景
            self._conn.execute("PRAGMA journal_mode=WAL;")
            # 外键约束开启（备用，当前建表无外键但保持良好实践）
            self._conn.execute("PRAGMA foreign_keys=ON;")
            self._conn.commit()
        except sqlite3.Error as e:
            raise SinkError(f"无法连接数据库 {self._path}：{e}") from e

    # ------------------------------------------------------------------
    # 建表 / 补列
    # ------------------------------------------------------------------

    def ensure_table(self, spec: SchemaSpec) -> None:
        """幂等建表 + 自动补列。

        流程：
        1. CREATE TABLE IF NOT EXISTS（首次建表）。
        2. 读取 PRAGMA table_info 获取已有列名。
        3. 对 spec.columns 中缺失的列执行 ALTER TABLE ADD COLUMN TEXT。
        4. 若 dedup_keys 非空，创建唯一索引（IF NOT EXISTS 幂等）。
        """
        from .schema import create_table_sql, unique_index_sql

        try:
            # 步骤 1：建表
            ddl = create_table_sql(spec)
            self._conn.execute(ddl)

            # 步骤 2：读现有列
            existing_cols = self._get_existing_columns(spec.table)

            # 步骤 3：补列（跳过 id，SQLite 禁止 ADD COLUMN 到自增主键列）
            for col in spec.columns:
                if col == "id":
                    continue
                if col not in existing_cols:
                    self._conn.execute(
                        f'ALTER TABLE "{spec.table}" ADD COLUMN "{col}" TEXT;'
                    )

            # 步骤 4：唯一索引
            idx_sql = unique_index_sql(spec)
            if idx_sql:
                self._conn.execute(idx_sql)

            self._conn.commit()
        except sqlite3.Error as e:
            self._conn.rollback()
            raise SinkError(f"ensure_table 失败（表={spec.table}）：{e}") from e

    def _get_existing_columns(self, table: str) -> set[str]:
        """通过 PRAGMA table_info 获取表已有列名集合。"""
        cursor = self._conn.execute(f'PRAGMA table_info("{table}");')
        rows = cursor.fetchall()
        return {row["name"] for row in rows}

    # ------------------------------------------------------------------
    # upsert
    # ------------------------------------------------------------------

    def upsert(
        self, spec: SchemaSpec, rows: list[dict[str, Any]]
    ) -> tuple[int, int]:
        """批量 upsert，返回 (inserted, updated)。

        - dedup_keys 非空：INSERT ... ON CONFLICT(...) DO UPDATE SET ...
          通过检测 updated_at 是否变化（INSERT 时 created_at=updated_at，
          UPDATE 时 updated_at > created_at）来区分插入与更新。
        - dedup_keys 为空：纯 INSERT（不做去重），全量追加。

        SQLite rowcount 对 upsert 语义：
          - 纯插入触发：rowcount=1，last_insert_rowid 为新 id。
          - 冲突触发 UPDATE：rowcount=1，但 changes() 仍为 1。
          因此采用「写前 count → 写后 count → 差值」方式计算 inserted，
          updated = received - inserted。
        """
        if not rows:
            return 0, 0

        now = _now_iso()

        # 写前总数（用于计算 inserted）
        before_count = self.count(spec.table)

        try:
            if spec.dedup_keys:
                self._upsert_with_dedup(spec, rows, now)
            else:
                self._insert_plain(spec, rows, now)
            self._conn.commit()
        except sqlite3.Error as e:
            self._conn.rollback()
            raise SinkError(f"upsert 失败（表={spec.table}）：{e}") from e

        after_count = self.count(spec.table)
        inserted = after_count - before_count
        updated = len(rows) - inserted
        return inserted, updated

    def _upsert_with_dedup(
        self, spec: SchemaSpec, rows: list[dict[str, Any]], now: str
    ) -> None:
        """有 dedup_keys 时的 upsert 实现。

        生成形如：
          INSERT INTO "t" (col1, col2, ..., created_at, updated_at)
          VALUES (?, ?, ..., ?, ?)
          ON CONFLICT(key1, key2) DO UPDATE SET
            col1 = excluded.col1, ..., updated_at = excluded.updated_at;

        注意：冲突时 created_at 保持原值不更新（保留首次入库时间）。
        """
        # 数据列：spec.columns 中去除 id（自增）和 created_at/updated_at（单独处理）
        data_cols = [
            c for c in spec.columns if c not in ("id", "created_at", "updated_at")
        ]
        all_cols = [*data_cols, "created_at", "updated_at"]
        placeholders = ", ".join("?" for _ in all_cols)
        col_list = ", ".join(f'"{c}"' for c in all_cols)

        # UPDATE SET：更新非去重键列 + updated_at；不更新 created_at
        update_targets = [
            c for c in data_cols if c not in spec.dedup_keys
        ]
        set_clause = ", ".join(
            f'"{c}" = excluded."{c}"' for c in update_targets
        )
        set_clause += ', "updated_at" = excluded."updated_at"'

        conflict_keys = ", ".join(f'"{k}"' for k in spec.dedup_keys)

        sql = (
            f'INSERT INTO "{spec.table}" ({col_list}) VALUES ({placeholders})\n'
            f"ON CONFLICT({conflict_keys}) DO UPDATE SET {set_clause};"
        )

        params_list: list[tuple] = []
        for row in rows:
            vals = [row.get(c) for c in data_cols]
            vals.extend([now, now])  # created_at, updated_at 首次均为 now
            params_list.append(tuple(vals))

        self._conn.executemany(sql, params_list)

    def _insert_plain(
        self, spec: SchemaSpec, rows: list[dict[str, Any]], now: str
    ) -> None:
        """无 dedup_keys 时的纯 INSERT。"""
        data_cols = [
            c for c in spec.columns if c not in ("id", "created_at", "updated_at")
        ]
        all_cols = [*data_cols, "created_at", "updated_at"]
        placeholders = ", ".join("?" for _ in all_cols)
        col_list = ", ".join(f'"{c}"' for c in all_cols)

        sql = f'INSERT INTO "{spec.table}" ({col_list}) VALUES ({placeholders});'

        params_list: list[tuple] = []
        for row in rows:
            vals = [row.get(c) for c in data_cols]
            vals.extend([now, now])
            params_list.append(tuple(vals))

        self._conn.executemany(sql, params_list)

    # ------------------------------------------------------------------
    # count / query / readonly_connect
    # ------------------------------------------------------------------

    def count(self, table: str) -> int:
        """返回指定表的当前行数（快速 COUNT(*) 查询）。"""
        try:
            cursor = self._conn.execute(f'SELECT COUNT(*) FROM "{table}";')
            return cursor.fetchone()[0]
        except sqlite3.Error as e:
            raise SinkError(f"count 查询失败（表={table}）：{e}") from e

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """通用只读查询入口，返回 sqlite3.Row 列表。

        Args:
            sql:    SELECT 语句（调用方负责安全性，禁止拼接外部输入）。
            params: 参数化绑定值。

        Returns:
            sqlite3.Row 列表，支持按列名或索引访问。
        """
        try:
            cursor = self._conn.execute(sql, params)
            return cursor.fetchall()
        except sqlite3.Error as e:
            raise SinkError(f"query 失败：{e}\nSQL: {sql}") from e

    def readonly_connect(self) -> sqlite3.Connection:
        """返回指向同一 db 文件的只读 URI 连接。

        只读连接不会持有写锁，适合数据导出、报表查询等场景。
        调用方负责关闭此连接。
        """
        try:
            uri = f"file:{self._path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            raise SinkError(f"只读连接失败：{e}") from e

    # ------------------------------------------------------------------
    # backup
    # ------------------------------------------------------------------

    def backup(self, keep: int = 10) -> Path:
        """在线备份到 <db_dir>/database_backup/<dbname>.<时间戳>.db。

        使用 sqlite3 Connection.backup() 在线 API，无需锁定主库。
        备份完成后，若备份文件数超过 keep，按时间戳升序删除最旧的文件。

        Args:
            keep: 保留最近备份份数，超出时删除最旧文件。默认 10。

        Returns:
            本次备份文件的 Path。
        """
        backup_dir = self._path.parent / "database_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{self._path.stem}.{timestamp}.db"
        backup_path = backup_dir / backup_name

        try:
            dest_conn = sqlite3.connect(str(backup_path))
            self._conn.backup(dest_conn)
            dest_conn.close()
        except sqlite3.Error as e:
            raise SinkError(f"备份失败：{e}") from e

        # 只保留最近 keep 份（按文件名中时间戳字典序排序，越早的越小）
        pattern = re.compile(
            rf'^{re.escape(self._path.stem)}\.\d{{8}}_\d{{6}}\.db$'
        )
        all_backups = sorted(
            (f for f in backup_dir.iterdir() if pattern.match(f.name)),
            key=lambda f: f.name,
        )
        # 删除超出 keep 数量的旧备份
        for old_file in all_backups[:-keep] if len(all_backups) > keep else []:
            old_file.unlink(missing_ok=True)

        return backup_path

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def close(self) -> None:
        """关闭数据库连接。"""
        try:
            self._conn.close()
        except sqlite3.Error:
            pass  # 关闭时忽略错误，避免遮蔽业务异常

    def __enter__(self) -> "FxDatabase":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"FxDatabase({self._path!r})"


__all__ = ["FxDatabase"]
