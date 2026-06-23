"""元信息数据库：记录抓取流水（crawl_runs）和数据源汇总（source_summary）。

设计原则：
- 与业务库完全独立，仅用 sqlite3 标准库，不依赖 storage 层。
- WAL 模式保证写入不阻塞读取，适合多进程同时抓取的场景。
- source_summary 做热缓存，避免每次健康检查都全表扫 crawl_runs。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ..core.source import SourceProfile


# --------------------------------------------------------------------------- #
#  工具函数
# --------------------------------------------------------------------------- #

def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO-8601 字符串，精确到秒。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
#  DDL：两张表的建表语句
# --------------------------------------------------------------------------- #

_DDL_CRAWL_RUNS = """
CREATE TABLE IF NOT EXISTS crawl_runs (
    id                INTEGER  PRIMARY KEY AUTOINCREMENT,
    source_slug       TEXT     NOT NULL,
    source_name       TEXT     NOT NULL DEFAULT '',
    status            TEXT     NOT NULL DEFAULT 'running',  -- running/success/failed/anomaly
    job_count         INTEGER  NOT NULL DEFAULT 0,          -- 本轮抓到的条数
    total_job_count   INTEGER  NOT NULL DEFAULT 0,          -- 写后库内总数
    error_message     TEXT,
    started_at        TEXT     NOT NULL,
    finished_at       TEXT,
    module_path       TEXT,
    extra_info        TEXT                                   -- JSON 字符串
);
"""

_DDL_SOURCE_SUMMARY = """
CREATE TABLE IF NOT EXISTS source_summary (
    source_slug          TEXT    PRIMARY KEY,
    last_status          TEXT    NOT NULL DEFAULT '',
    last_job_count       INTEGER NOT NULL DEFAULT 0,
    last_run_at          TEXT,
    last_total           INTEGER NOT NULL DEFAULT 0,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    updated_at           TEXT    NOT NULL
);
"""

_DDL_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_crawl_runs_slug ON crawl_runs(source_slug);",
    "CREATE INDEX IF NOT EXISTS idx_crawl_runs_started ON crawl_runs(started_at DESC);",
]


# --------------------------------------------------------------------------- #
#  MetadataDatabase
# --------------------------------------------------------------------------- #

class MetadataDatabase:
    """元信息数据库，管理抓取流水与数据源健康汇总。

    典型用法::

        with MetadataDatabase("/data/meta.db") as meta:
            run_id = meta.start_crawl(profile, module_path="sources.icbc")
            # ... 抓取 ...
            meta.finish_crawl(run_id, status="success", job_count=120, total_job_count=3500)
    """

    def __init__(self, db_path: str) -> None:
        """初始化并建表。

        Args:
            db_path: SQLite 文件路径，传 ":memory:" 可用于测试。
        """
        self._db_path = db_path
        self._conn: sqlite3.Connection = sqlite3.connect(
            db_path,
            check_same_thread=False,  # 允许跨线程（由调用方负责并发安全）
        )
        self._conn.row_factory = sqlite3.Row  # 支持按列名访问
        self._init_db()

    # ---------------------------------------------------------------------- #
    #  初始化
    # ---------------------------------------------------------------------- #

    def _init_db(self) -> None:
        """建表、建索引、开启 WAL 模式。"""
        cur = self._conn.cursor()
        # WAL 模式：写不阻塞读
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute(_DDL_CRAWL_RUNS)
        cur.execute(_DDL_SOURCE_SUMMARY)
        for idx_sql in _DDL_INDEXES:
            cur.execute(idx_sql)
        self._conn.commit()

    # ---------------------------------------------------------------------- #
    #  公开 API
    # ---------------------------------------------------------------------- #

    def start_crawl(
        self,
        profile: SourceProfile,
        *,
        module_path: str | None = None,
        extra_info: dict[str, Any] | None = None,
    ) -> int:
        """登记一次新的抓取任务，状态初始为 'running'，返回 run_id。

        Args:
            profile:     数据源静态元信息（slug / name 等）。
            module_path: 数据源模块路径，便于定位代码（可选）。
            extra_info:  附加信息字典，序列化为 JSON 存储（可选）。

        Returns:
            新插入行的 run_id（INTEGER PRIMARY KEY）。
        """
        extra_json = json.dumps(extra_info, ensure_ascii=False) if extra_info else None
        cur = self._conn.execute(
            """
            INSERT INTO crawl_runs
                (source_slug, source_name, status, started_at, module_path, extra_info)
            VALUES (?, ?, 'running', ?, ?, ?)
            """,
            (profile.slug, profile.name, _now_iso(), module_path, extra_json),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def finish_crawl(
        self,
        run_id: int,
        *,
        status: str,
        job_count: int = 0,
        total_job_count: int = 0,
        error_message: str | None = None,
    ) -> None:
        """结束一次抓取任务，更新状态并同步刷新 source_summary。

        Args:
            run_id:          start_crawl 返回的 run_id。
            status:          终态：'success' / 'failed' / 'anomaly'。
            job_count:       本轮实际抓到的记录条数。
            total_job_count: 落库后该源的累计总条数。
            error_message:   错误信息（status 为 failed 时填写）。

        Raises:
            ValueError: run_id 不存在时。
        """
        now = _now_iso()

        # 1. 更新流水记录
        affected = self._conn.execute(
            """
            UPDATE crawl_runs
            SET status = ?, job_count = ?, total_job_count = ?,
                error_message = ?, finished_at = ?
            WHERE id = ?
            """,
            (status, job_count, total_job_count, error_message, now, run_id),
        ).rowcount

        if affected == 0:
            raise ValueError(f"run_id={run_id} 不存在，无法完成流水更新")

        # 2. 查出 source_slug（finish 时只知道 run_id，需要反查）
        row = self._conn.execute(
            "SELECT source_slug, source_name FROM crawl_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        source_slug: str = row["source_slug"]
        source_name: str = row["source_name"]

        # 3. 刷新 source_summary（UPSERT）
        #    consecutive_failures：success/anomaly 清零，failed 累加 1
        if status == "failed":
            # failed 时累加连续失败计数
            self._conn.execute(
                """
                INSERT INTO source_summary
                    (source_slug, last_status, last_job_count, last_run_at,
                     last_total, consecutive_failures, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(source_slug) DO UPDATE SET
                    last_status          = excluded.last_status,
                    last_job_count       = excluded.last_job_count,
                    last_run_at          = excluded.last_run_at,
                    last_total           = excluded.last_total,
                    consecutive_failures = source_summary.consecutive_failures + 1,
                    updated_at           = excluded.updated_at
                """,
                (source_slug, status, job_count, now, total_job_count, now),
            )
        else:
            # success / anomaly：连续失败清零
            self._conn.execute(
                """
                INSERT INTO source_summary
                    (source_slug, last_status, last_job_count, last_run_at,
                     last_total, consecutive_failures, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(source_slug) DO UPDATE SET
                    last_status          = excluded.last_status,
                    last_job_count       = excluded.last_job_count,
                    last_run_at          = excluded.last_run_at,
                    last_total           = excluded.last_total,
                    consecutive_failures = 0,
                    updated_at           = excluded.updated_at
                """,
                (source_slug, status, job_count, now, total_job_count, now),
            )

        self._conn.commit()

    def last_count(self, source_slug: str) -> int | None:
        """返回该源上一轮成功（status='success'）的 job_count，用于健康环比。

        若从未有成功记录，返回 None（视为首轮，不触发异常告警）。

        Args:
            source_slug: 数据源唯一标识。

        Returns:
            上一轮成功的 job_count，或 None。
        """
        row = self._conn.execute(
            """
            SELECT job_count FROM crawl_runs
            WHERE source_slug = ? AND status = 'success'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (source_slug,),
        ).fetchone()
        return int(row["job_count"]) if row else None

    def recent_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        """返回最近 N 条流水记录（按开始时间倒序）。

        Args:
            limit: 最多返回条数，默认 50。

        Returns:
            dict 列表，每条对应 crawl_runs 一行。
        """
        rows = self._conn.execute(
            """
            SELECT * FROM crawl_runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def summaries(self) -> list[dict[str, Any]]:
        """返回所有数据源的最新汇总（source_summary 全表）。

        Returns:
            dict 列表，每条对应 source_summary 一行。
        """
        rows = self._conn.execute(
            "SELECT * FROM source_summary ORDER BY last_run_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------------- #
    #  生命周期
    # ---------------------------------------------------------------------- #

    def close(self) -> None:
        """关闭数据库连接。"""
        self._conn.close()

    def __enter__(self) -> "MetadataDatabase":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


__all__ = ["MetadataDatabase"]
