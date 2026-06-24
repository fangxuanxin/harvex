# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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
