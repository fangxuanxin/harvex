"""harvex 配置层公开接口。

外部代码统一从这里导入，不依赖内部子模块路径：

    from harvex.config import load_settings, Settings, source_enabled
"""

from harvex.config.defaults import (
    DEFAULT_BACKUP_KEEP,
    DEFAULT_DATABASE_DIR,
    DEFAULT_DB_FILENAME,
    DEFAULT_DROP_RATIO,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_LOG_DIR,
    DEFAULT_META_DB_FILENAME,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_TABLE,
    DEFAULT_USER_AGENT,
)
from harvex.config.settings import (
    HttpConfig,
    NotifyConfig,
    Settings,
    SourceConfig,
    StorageConfig,
    load_settings,
    source_enabled,
)

__all__ = [
    # 加载函数
    "load_settings",
    "source_enabled",
    # 配置模型
    "Settings",
    "SourceConfig",
    "NotifyConfig",
    "HttpConfig",
    "StorageConfig",
    # 默认常量
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
