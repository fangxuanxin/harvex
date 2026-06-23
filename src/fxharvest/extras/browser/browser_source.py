"""浏览器渲染型数据源基类（extras/browser/browser_source.py）。

BrowserSource 是 BaseSource 的渲染型子类，适用于需要 JavaScript 渲染的页面。
子类只需：
  1. 声明 profile / record_model（继承自 BaseSource 契约）
  2. 设置 start_url（起始 URL）
  3. 实现 parse(self, raw) —— 从 HTML 字符串解析出 dict 序列

可选覆盖：
  - render(self, page) —— 在页面加载后执行点击/滚动/登录等交互

用法示例::

    class JobSource(BrowserSource):
        profile = SourceProfile(slug="demo", name="示例源")
        record_model = JobRecord
        start_url = "https://jobs.example.com"

        def parse(self, raw: str):
            import re
            for title in re.findall(r"<h2>(.*?)</h2>", raw):
                yield {"职位名称": title}

playwright 未安装时，import 本模块不报错；
只有调用 fetch() / collect() 时才抛 ConfigError（含安装提示）。
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, ClassVar

from fxharvest.core.errors import ConfigError, FetchError
from fxharvest.core.source import BaseSource

if TYPE_CHECKING:
    # 仅类型检查时引入，运行时不触发 playwright 依赖
    pass


class BrowserSource(BaseSource):
    """渲染型数据源抽象基类。

    继承自 BaseSource，通过 Playwright 启动 Chromium 渲染目标页面，
    再将完整 HTML 交给子类的 parse() 处理。

    Class Variables:
        start_url: 子类必须设置，作为 fetch() 的导航目标 URL。

    Config Keys（从 self.ctx.config 读取）:
        headless (bool): 是否无头模式，默认 True
        timeout (int): 导航超时毫秒，默认 30000
    """

    # 子类必须设置此 ClassVar
    start_url: ClassVar[str]

    def fetch(self) -> str:
        """使用 Playwright Chromium 渲染 start_url，返回完整 HTML 字符串。

        流程：
          1. 从 ctx.config 读取 headless / timeout 配置
          2. 启动 BrowserRuntime，导航到 start_url
          3. 等待网络空闲（networkidle）
          4. 调用 self.render(page) 钩子（子类可覆盖）
          5. 返回 page.content() HTML 字符串

        Returns:
            完整渲染后的 HTML 字符串

        Raises:
            ConfigError: playwright 未安装
            FetchError: 导航失败、超时或其他 playwright 异常
        """
        # 从上下文配置读取浏览器参数，提供合理默认值
        headless: bool = self.ctx.config.get("headless", True)
        timeout: int = self.ctx.config.get("timeout", 30_000)

        # 延迟导入 runtime（runtime 内部延迟导入 playwright），
        # 确保模块级 import 不触发 playwright 依赖
        from .runtime import launch_chromium  # noqa: PLC0415

        try:
            # launch_chromium 在 playwright 未安装时立即抛 ConfigError
            runtime = launch_chromium(headless=headless, timeout=timeout)
        except ConfigError:
            raise  # ConfigError 原样上浮，不包成 FetchError

        try:
            with runtime as page:
                # 导航到目标 URL，等待网络空闲以确保 JS 渲染完成
                page.goto(self.start_url, wait_until="networkidle")
                # 子类交互钩子（点击/滚动/登录等），默认无操作
                self.render(page)
                # 返回完整 HTML 字符串
                return page.content()
        except ConfigError:
            raise  # ConfigError 不包装
        except Exception as exc:
            # 所有 playwright 运行时异常统一包成 FetchError
            raise FetchError(
                f"[{self.slug}] 浏览器渲染失败 ({self.start_url}): {exc}"
            ) from exc

    def render(self, page: Any) -> None:  # noqa: ANN401
        """页面交互钩子：在页面加载完成后、抓取 HTML 前执行。

        默认为空操作（no-op）。子类可覆盖以实现：
          - 滚动到底部加载更多内容
          - 点击「加载更多」按钮
          - 处理登录弹窗
          - 等待特定元素出现

        Args:
            page: Playwright Page 对象（未装 playwright 时此方法不会被调用）
        """

    @abstractmethod
    def parse(self, raw: Any) -> Iterable[Mapping[str, Any]]:
        """从渲染后的 HTML 字符串解析出记录 dict 序列。

        子类必须实现此方法。raw 为 fetch() 返回的 HTML 字符串，
        但也可以是子类在 render() 中提取的任何中间数据。

        Args:
            raw: 通常为 HTML 字符串（fetch 返回值）

        Yields:
            每条记录对应一个 dict，键名与 record_model 字段对应
        """


__all__ = ["BrowserSource"]
