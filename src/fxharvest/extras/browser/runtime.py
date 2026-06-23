"""浏览器运行时封装模块（extras/browser/runtime.py）。

提供 BrowserRuntime 上下文管理器与 launch_chromium 工厂函数。
所有对 playwright 的 import 均在运行时延迟执行，确保
在 playwright 未安装时本模块仍可被 import，只有实际使用时才报错。
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

from fxharvest.core.errors import ConfigError


# 安装提示：未装 playwright 时的统一错误消息
_INSTALL_HINT = (
    "playwright 未安装，请先执行：\n"
    "    uv add playwright\n"
    "    uv run playwright install chromium\n"
    "或使用 pip：\n"
    "    pip install playwright && playwright install chromium"
)


def _require_playwright() -> Any:
    """延迟导入 playwright.sync_api，未安装时抛出 ConfigError。

    Returns:
        playwright.sync_api 模块对象

    Raises:
        ConfigError: playwright 未安装时抛出，消息含安装提示
    """
    try:
        import playwright.sync_api as pw_sync  # 延迟导入，确保未装时不在模块级失败
        return pw_sync
    except ImportError as exc:
        raise ConfigError(_INSTALL_HINT) from exc


class BrowserRuntime:
    """Playwright Chromium 浏览器运行时上下文管理器。

    封装 playwright/browser/context/page 的完整生命周期，
    __enter__ 返回一个新建的 Page 实例，__exit__ 自动清理所有资源。

    用法示例::

        with BrowserRuntime(headless=True, timeout=30000) as page:
            page.goto("https://example.com")
            html = page.content()

    Args:
        headless: 是否以无头模式启动，默认 True
        timeout: 默认导航/等待超时（毫秒），默认 30000
    """

    def __init__(self, *, headless: bool = True, timeout: int = 30000) -> None:
        self._headless = headless
        self._timeout = timeout
        # 以下字段在 __enter__ 中赋值，确保 __exit__ 可安全清理
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    def __enter__(self) -> Any:
        """启动 Playwright、Chromium、浏览器上下文与页面，返回 Page 对象。

        Raises:
            ConfigError: playwright 未安装
        """
        pw_sync = _require_playwright()
        # 启动 playwright 同步运行时
        self._playwright = pw_sync.sync_playwright().start()
        # 启动 Chromium 浏览器
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        # 创建独立浏览器上下文（隔离 cookie/session）
        self._context = self._browser.new_context()
        # 设置默认导航超时
        self._context.set_default_navigation_timeout(self._timeout)
        self._context.set_default_timeout(self._timeout)
        # 创建新页面
        self._page = self._context.new_page()
        return self._page

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        """按 page → context → browser → playwright 顺序释放所有资源。

        不吞异常（返回 False），让调用方继续处理原始异常。
        """
        # 逐层关闭，任一步骤失败不阻断后续清理
        for obj in (self._page, self._context, self._browser, self._playwright):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass  # 清理阶段静默失败，不掩盖原始异常
        return False  # 不吞异常


def launch_chromium(*, headless: bool = True, timeout: int = 30000) -> BrowserRuntime:
    """工厂函数：返回一个配置好的 BrowserRuntime 上下文管理器。

    playwright 未安装时立即抛出 ConfigError（含安装提示），
    而不是等到 __enter__ 时才报错，让问题更早暴露。

    Args:
        headless: 是否无头模式，默认 True
        timeout: 默认超时毫秒，默认 30000

    Returns:
        BrowserRuntime 实例（上下文管理器）

    Raises:
        ConfigError: playwright 未安装
    """
    # 提前探测 playwright 是否可用，让错误在工厂函数阶段就暴露
    _require_playwright()
    return BrowserRuntime(headless=headless, timeout=timeout)


__all__ = ["BrowserRuntime", "launch_chromium"]
