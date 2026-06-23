"""LLM 翻译结果缓存模块。

使用 SQLite 存储翻译结果，避免对相同内容重复调用 LLM 接口产生费用。
缓存键由（源文本哈希、目标语言、模型名称）三元组构成。
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path


# 缓存数据库默认文件名
_DEFAULT_DB_NAME = "llm_cache.db"


def _text_hash(text: str) -> str:
    """计算文本的 SHA-256 哈希值（十六进制字符串）。

    使用哈希而非原文作为主键，避免超长文本导致索引效率下降。
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TranslationCache:
    """SQLite 翻译结果缓存。

    以（源文本哈希、目标语言、模型）为联合主键存储译文，
    支持命中查询（get）和写入（put）。

    示例::

        cache = TranslationCache()
        cache.put("Hello", "你好", target="zh", model="gpt-4o-mini")
        result = cache.get("Hello", target="zh", model="gpt-4o-mini")
        # result == "你好"
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        """初始化缓存，建立 SQLite 连接并确保表存在。

        Args:
            db_path: 缓存数据库路径。为 None 时，默认使用
                     当前工作目录下的 database/llm_cache.db。
        """
        if db_path is None:
            # 默认放到 database/ 目录下，与项目其他 db 文件保持一致
            db_path = Path.cwd() / "database" / _DEFAULT_DB_NAME

        self._path = Path(db_path).resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._ensure_table()

    def _ensure_table(self) -> None:
        """幂等建表：translation_cache。"""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS translation_cache (
                text_hash   TEXT    NOT NULL,
                target_lang TEXT    NOT NULL,
                model       TEXT    NOT NULL,
                translation TEXT    NOT NULL,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now','utc')),
                PRIMARY KEY (text_hash, target_lang, model)
            );
            """
        )
        self._conn.commit()

    def get(self, text: str, *, target: str, model: str) -> str | None:
        """查询缓存。

        Args:
            text:   源文本（原文，非哈希）。
            target: 目标语言代码（如 "zh"、"en"）。
            model:  模型名称（如 "gpt-4o-mini"）。

        Returns:
            命中时返回缓存译文字符串；未命中返回 None。
        """
        h = _text_hash(text)
        cursor = self._conn.execute(
            "SELECT translation FROM translation_cache "
            "WHERE text_hash=? AND target_lang=? AND model=?;",
            (h, target, model),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def put(self, text: str, translation: str, *, target: str, model: str) -> None:
        """写入缓存（已存在时覆盖）。

        Args:
            text:        源文本（原文）。
            translation: 翻译结果。
            target:      目标语言代码。
            model:       模型名称。
        """
        h = _text_hash(text)
        self._conn.execute(
            """
            INSERT INTO translation_cache (text_hash, target_lang, model, translation)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(text_hash, target_lang, model)
            DO UPDATE SET translation=excluded.translation;
            """,
            (h, target, model, translation),
        )
        self._conn.commit()

    def close(self) -> None:
        """关闭数据库连接。"""
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    def __enter__(self) -> "TranslationCache":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"TranslationCache({self._path!r})"


__all__ = ["TranslationCache"]
