"""harvex：可本地复用的数据采集框架库。

公开 API —— 下游项目只需从这里导入：

    from harvex import BaseSource, SourceProfile, HarvestRecord, run_sources

核心契约（record/source/context/errors/sink）始终可用；
runner/pipeline 等编排能力在对应模块就绪后由本文件统一导出。
"""

from __future__ import annotations

from .core.context import SourceContext
from .core.errors import (
    ConfigError,
    FetchError,
    HarvexError,
    ParseError,
    RecordValidationError,
    SinkError,
)
from .core.pipeline import Pipeline, SourceResult
from .core.record import HarvestRecord
from .core.registry import SourceRegistry
from .core.runner import RunReport, run_sources
from .acquire.base import Acquirer, AcquireContext, AcquireResult
from .acquire.registry import PluginRegistry, load_acquirer
from .core.source import BaseSource, SourceProfile
from .storage.sink import Sink, WriteResult

# 版本号以已安装包的元数据为准（与 pyproject 单一来源同步，避免硬编码漂移）
try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("harvex")
except Exception:  # noqa: BLE001 源码树未安装时的兜底
    __version__ = "0.0.0+unknown"

__all__ = [
    "BaseSource",
    "SourceProfile",
    "SourceContext",
    "HarvestRecord",
    "SourceRegistry",
    "Pipeline",
    "SourceResult",
    "run_sources",
    "RunReport",
    "Sink",
    "WriteResult",
    "Acquirer",
    "AcquireContext",
    "AcquireResult",
    "PluginRegistry",
    "load_acquirer",
    "HarvexError",
    "ConfigError",
    "FetchError",
    "ParseError",
    "RecordValidationError",
    "SinkError",
    "__version__",
]
