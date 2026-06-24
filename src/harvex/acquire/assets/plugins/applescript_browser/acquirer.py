"""macOS 默认浏览器操控注入采集插件（骨架铺垫）。

定位（最具特色的一种）：不自己起浏览器，而是用 AppleScript（osascript）操控用户
**当前正在用的真实浏览器**（Safari / Chrome / Edge / Brave 等），导航到目标页并注入
JS 取数。好处：复用用户已登录的真实会话与指纹，天然绕过大量反爬与登录墙。

关键事实（已据官方/社区资料核对，写进指引供 AI 实现）：
  - Safari：``tell application "Safari" to do JavaScript "<js>" in front document``。
    需用户在 Safari「开发」菜单勾选「允许 Apple Events 中的 JavaScript」。
  - Chrome 系：``tell application "Google Chrome" to execute front window's active tab
    javascript "<js>"``。需在「显示」>「开发者」>「允许来自 Apple 事件的 JavaScript」开启。
  - 默认浏览器可经 LaunchServices 查询；也可由 config 显式指定 app 名。
  - osascript 调用经 ``subprocess``；注入 JS 应让其 ``JSON.stringify`` 结果，Python 侧再解析。

⚠️ 铺垫骨架：``acquire()`` 未实现。AppleScript / inject.js 模板已自带在 assets/，
具体编排与权限处理留给后续 AI 服务补全。仅在 macOS 可用。
"""

from __future__ import annotations

import sys

from harvex.acquire.base import Acquirer, AcquireResult
from harvex.core.errors import ConfigError


class AppleScriptBrowserAcquirer(Acquirer):
    """通过 AppleScript 操控 macOS 浏览器并注入 JS 取数。

    实现指引（供 AI 补全 acquire）：
      1. 平台校验：非 macOS 抛 ConfigError（见 _require_macos）。
      2. 决定目标浏览器：self.ctx.config.get("browser") 或查默认浏览器。
      3. 读 assets：
         - self.ctx.assets_dir/"control_browser.applescript" —— 导航 + 注入的 osascript 模板，
           用占位符（{{APP}} / {{URL}} / {{JS}}）替换后交给 ``osascript -e`` 或 ``osascript <file>``。
         - self.ctx.assets_dir/"inject.js" —— 页内取数脚本，需 JSON.stringify 返回。
      4. subprocess 调 osascript：先导航 self.ctx.url、等待 document.readyState=="complete"、
         再注入 inject.js，拿回 stdout（JSON 字符串）。
      5. 返回 ``AcquireResult(raw=<解析后的对象或原始JSON字符串>, content_type="json"|"html",
         url=self.ctx.url, meta={"browser": app})``。
      6. 失败（osascript 非零退出 / 权限未开）包成 FetchError，并提示开启「允许 Apple 事件中的
         JavaScript」。
    """

    kind = "applescript_browser"

    def setup(self) -> None:
        self._require_macos()
        super().setup()

    def acquire(self) -> AcquireResult:
        raise NotImplementedError(
            "AppleScriptBrowserAcquirer.acquire 尚未实现——预留给 AI 服务补全。"
            "assets/ 内已备 control_browser.applescript 与 inject.js 模板；"
            "参见类文档串的实现指引与浏览器权限要求。"
        )

    @staticmethod
    def _require_macos() -> None:
        """仅 macOS 可用。"""
        if sys.platform != "darwin":
            raise ConfigError("applescript_browser 采集方式仅支持 macOS（依赖 osascript/AppleScript）。")


__all__ = ["AppleScriptBrowserAcquirer"]
