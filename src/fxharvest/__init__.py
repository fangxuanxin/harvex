"""fxharvest：可本地复用的数据采集框架库。

公开 API —— 下游项目只需从这里导入：

    from fxharvest import BaseSource, SourceProfile, HarvestRecord, run_sources

核心契约（record/source/context/errors/sink）始终可用；
runner/pipeline 等编排能力在对应模块就绪后由本文件统一导出。
"""

from __future__ import annotations

from .core.context import SourceContext
from .core.errors import (
    ConfigError,
    FetchError,
    FxHarvestError,
    ParseError,
    RecordValidationError,
    SinkError,
)
from .core.record import HarvestRecord
from .core.source import BaseSource, SourceProfile
from .storage.sink import Sink, WriteResult

__version__ = "0.1.0"

__all__ = [
    "BaseSource",
    "SourceProfile",
    "SourceContext",
    "HarvestRecord",
    "Sink",
    "WriteResult",
    "FxHarvestError",
    "ConfigError",
    "FetchError",
    "ParseError",
    "RecordValidationError",
    "SinkError",
    "__version__",
]
