-- 操控 macOS 浏览器：导航到目标 URL 并注入 JS 取数（模板 / 铺垫）。
-- 由 AppleScriptBrowserAcquirer 用占位符替换后通过 osascript 执行。
-- 占位符：{{APP}} 浏览器应用名（"Safari" / "Google Chrome" ...）、{{URL}} 目标地址、{{JS}} 注入脚本。
--
-- 注意权限：
--   Safari  ：开发菜单 →「允许 Apple 事件中的 JavaScript」
--   Chrome 系：显示 → 开发者 →「允许来自 Apple 事件的 JavaScript」
--
-- 两类浏览器注入 API 不同，AI 实现时按 {{APP}} 分支选择：
--   Safari ：do JavaScript "<js>" in front document
--   Chrome ：execute front window's active tab javascript "<js>"

on run
	-- 铺垫占位：以下为参考骨架，具体由 AI 服务按 {{APP}} 完整实现。
	set targetApp to "{{APP}}"
	set targetURL to "{{URL}}"

	tell application targetApp
		activate
		-- TODO(AI)：新建/复用标签页并 set URL 为 targetURL；轮询等待加载完成。
		-- TODO(AI)：按 Safari / Chrome 分支执行 {{JS}} 注入，return 其 JSON.stringify 结果。
	end tell

	return "{}" -- 占位返回（空 JSON）；实现后应返回注入脚本的真实结果
end run
