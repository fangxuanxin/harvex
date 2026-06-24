"""harvex [browser] 扩展包。

需要额外安装：
    uv add "harvex[browser]"
    uv run playwright install chromium

本包的所有对 playwright 的 import 均延迟到方法内部，
确保在未安装 playwright 时本包仍可被正常 import。
"""

from .browser_source import BrowserSource
from .runtime import BrowserRuntime, launch_chromium

__all__ = ["BrowserRuntime", "BrowserSource", "launch_chromium"]
