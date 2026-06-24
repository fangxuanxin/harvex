"""harvex 采集方式（Acquirer）插件层。

公开：Acquirer 契约 + 上下文/结果数据类 + 插件注册表。
具体采集方式以插件形式位于 ``assets/plugins/``（http / playwright_headless /
applescript_browser …），骨架已铺好，具体实现留待补全。
"""

from __future__ import annotations

from .base import Acquirer, AcquireContext, AcquireResult
from .manifest import PluginManifest
from .registry import BUNDLED_PLUGINS_DIR, PluginRegistry, load_acquirer

__all__ = [
    "Acquirer",
    "AcquireContext",
    "AcquireResult",
    "PluginManifest",
    "PluginRegistry",
    "load_acquirer",
    "BUNDLED_PLUGINS_DIR",
]
