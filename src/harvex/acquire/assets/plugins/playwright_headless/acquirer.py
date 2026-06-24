"""无头浏览器渲染采集插件（骨架铺垫）。

定位：用 Playwright 无头 Chromium 渲染 JS 重的页面，拿到渲染后的 HTML（或截图）。
与框架已有的 ``harvex.extras.browser`` 复用同一套 playwright 运行时思路，
但以「采集方式插件」的统一接口呈现。

⚠️ 铺垫骨架：``setup``/``acquire``/``teardown`` 仅留结构与指引，具体实现交由 AI 补全。
playwright 为可选依赖，import 延迟到运行时；未安装时给可读报错。
"""

from __future__ import annotations

from harvex.acquire.base import Acquirer, AcquireResult
from harvex.core.errors import ConfigError


class PlaywrightHeadlessAcquirer(Acquirer):
    """无头浏览器渲染获取器。

    实现指引（供 AI 补全）：
      setup():
        - 延迟 ``from playwright.sync_api import sync_playwright``；未装抛 ConfigError
          （提示：uv add 'harvex[browser]' 且 playwright install chromium）。
        - 启动 chromium（headless=self.ctx.config.get("headless", True)），建 context/page，
          句柄存 self._pw / self._browser / self._page。
      acquire():
        - ``page.goto(self.ctx.url, wait_until="networkidle", timeout=...)``。
        - 可选注入：读 self.ctx.assets_dir/"inject.js" 用 ``page.add_init_script`` 或
          ``page.evaluate`` 执行（滚动加载、去广告、抽数据等）。
        - 等待选择器/超时后取 ``html = page.content()``。
        - 返回 ``AcquireResult(raw=html, content_type="html", url=page.url,
          meta={"title": page.title()})``；可把截图路径塞进 meta。
        - 任何 playwright 异常包成 FetchError。
      teardown():
        - 关 page/browser/playwright，幂等。
    """

    kind = "playwright_headless"

    def setup(self) -> None:
        # 铺垫：真实实现在此启动浏览器。先占位标记就绪，便于 with 语法跑通。
        self._page = None
        self._browser = None
        self._pw = None
        super().setup()

    def acquire(self) -> AcquireResult:
        raise NotImplementedError(
            "PlaywrightHeadlessAcquirer.acquire 尚未实现——预留给 AI 服务补全。"
            "参见类文档串：goto → （可选注入 inject.js）→ page.content()。"
        )

    def teardown(self) -> None:
        # 铺垫：真实实现在此关闭 page/browser/playwright。
        super().teardown()

    @staticmethod
    def _require_playwright():
        """供实现期调用：确认 playwright 可用，否则给安装指引。"""
        try:
            import playwright.sync_api  # noqa: F401, PLC0415
        except ImportError as exc:
            raise ConfigError(
                "playwright 未安装。请执行：uv add 'harvex[browser]' 且 playwright install chromium"
            ) from exc


__all__ = ["PlaywrightHeadlessAcquirer"]
