# Changelog

This project follows [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-06-24

### Added

- **采集方式插件层 `harvex.acquire`**：可插拔的「怎么取回原始数据」策略，与 Source 的「解析」解耦。
  - `Acquirer` 基类（生命周期 setup→acquire→teardown）+ `AcquireContext` / `AcquireResult`。
  - `PluginRegistry` 从 `assets/plugins/` 发现、加载、实例化插件；`plugin.toml` 清单。
  - 自带三种采集方式插件（**铺垫骨架**，`acquire()` 留待按目标接口补全）：
    `http`（传统 httpx）、`playwright_headless`（无头浏览器）、`applescript_browser`（macOS 操控默认浏览器 + JS 注入，自带 .applescript / inject.js 模板）。
- **解析扩展 `harvex[parse]`**：基于 parsel 的 CSS/XPath 选择器助手（`selector` / `css_all` / `css_first`）。

### Fixed

- Web 浏览 UI 品牌残留 `fxharvest` → `harvex`。

### Changed

- `__version__` 改为从已安装包元数据动态读取，与 pyproject 单一来源同步。

## [0.1.1] - 2026-06-24

### Changed

- Docs are now English-first, with Simplified Chinese (`README.zh-CN.md`) and Japanese (`README.ja.md`) as alternates.
- Package description switched to English.

### Removed

- Removed personal contact details (author email) from package metadata.

## [0.1.0] - 2026-06-24

首个公开发布。AI 时代的数据采集基座，为 AI agent 与 vibecoding 设计。

### 核心

- `HarvestRecord`（pydantic v2）字段收口契约：未声明字段自动折叠进 extra 列，脏数据写库前拦截。
- `BaseSource` + `SourceProfile` 类契约，`SourceRegistry` 扫描 `sources/` 自动发现。
- `Pipeline` 两阶段编排（并行采集 / 主线程串行落地，规避 SQLite 跨线程问题）。
- `run_sources` 并发统筹：故障隔离、轮级备份、汇总、失败/异常告警。

### 存储 / 元数据 / 韧性

- SQLite Sink：建表/自动补列 + upsert 去重 + 轮级备份；`Sink` 抽象预留多出口扩展。
- 元数据流水库 + 数据健康检查（归零 / 骤降识别）。
- `httpx` 统一客户端 + `tenacity` 指数退避重试；stdlib 结构化日志；webhook 告警（Bark/飞书/Server酱）。

### CLI / 调度

- `harvex` CLI：`list / run / health / gen-launchd / gen-cron / web / tui`。
- 生成 macOS launchd plist 与 crontab，调度与 Web 解耦。

### 可选扩展（extras）

- `[web]`：stdlib http.server 只读浏览 UI（零第三方依赖）。
- `[llm]`：OpenAI 翻译 + 缓存 + 重试、一句话增强。
- `[tui]`：本地终端控制面板。
- `[browser]`：playwright 渲染型源基类。

### 工程

- 42 个测试（零真实网络 / OpenAI / 浏览器）。
- `py.typed` 类型标记，核心零重依赖。

[0.1.0]: https://github.com/fangxuanxin/harvex/releases/tag/v0.1.0
[0.1.1]: https://github.com/fangxuanxin/harvex/releases/tag/v0.1.1
[0.2.0]: https://github.com/fangxuanxin/harvex/releases/tag/v0.2.0
