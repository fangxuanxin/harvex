"""配置层默认常量。

所有默认值集中在这里定义，settings.py 和业务代码统一从这里引用，
避免魔法字符串/数字散落各处。
"""

from __future__ import annotations

# ── HTTP 相关 ──────────────────────────────────────────────
# 默认单次请求超时（秒）
DEFAULT_HTTP_TIMEOUT: float = 15.0

# 默认重试次数（含首次，失败后最多再重试 N 次）
DEFAULT_RETRY_ATTEMPTS: int = 3

# 默认 User-Agent（None 表示由 http_client 自行决定）
DEFAULT_USER_AGENT: str | None = None

# ── 存储相关 ──────────────────────────────────────────────
# 默认主数据库文件名（相对 project_dir/database/）
DEFAULT_DB_FILENAME: str = "harvest.db"

# 默认元数据库文件名（记录抓取流水/状态）
DEFAULT_META_DB_FILENAME: str = "meta.db"

# 默认备份保留份数
DEFAULT_BACKUP_KEEP: int = 10

# 默认数据表名
DEFAULT_TABLE: str = "records"

# ── 目录名 ────────────────────────────────────────────────
# 日志输出目录（相对 project_dir）
DEFAULT_LOG_DIR: str = "logs"

# 数据库存放目录（相对 project_dir）
DEFAULT_DATABASE_DIR: str = "database"

# ── 数据质量 ──────────────────────────────────────────────
# 默认丢弃比例阈值：某批次空字段占比超过此值时触发警告/丢弃
DEFAULT_DROP_RATIO: float = 0.5

__all__ = [
    "DEFAULT_HTTP_TIMEOUT",
    "DEFAULT_RETRY_ATTEMPTS",
    "DEFAULT_USER_AGENT",
    "DEFAULT_DB_FILENAME",
    "DEFAULT_META_DB_FILENAME",
    "DEFAULT_BACKUP_KEEP",
    "DEFAULT_TABLE",
    "DEFAULT_LOG_DIR",
    "DEFAULT_DATABASE_DIR",
    "DEFAULT_DROP_RATIO",
]
