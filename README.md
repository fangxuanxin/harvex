# fxharvest

可本地复用的「**数据采集 → 收口 → SQLite → 浏览/增强**」框架库。

把多个相似的抓取项目（如「招聘信息」）里重复的基础设施——并发调度、写库去重、
元数据流水、HTTP 重试、日志、告警、健康检查、定时调度、Web 浏览、LLM 翻译、TUI
——统一上移到框架。新项目只写「**数据源类 + 字段模型 + 配置**」三样东西。

> 不发布到 PyPI。以共享本地目录 `~/Fxbox/fxharvest` 存在，下游项目用本地路径引用。

## 设计原则

- **核心零重依赖**：core 只依赖 `pydantic` / `httpx` / `tenacity`。`playwright`、`openai`、Web、TUI 都是按需安装的 `extras`。
- **字段收口是框架契约**：用 `HarvestRecord`（pydantic v2）守住「不让主表变稀疏矩阵」的纪律，脏数据写库前拦截。
- **故障隔离**：一个源挂掉不影响整轮抓取。
- **存储先 SQLite，签名预留 Sink 抽象**：不做多余抽象，但留接入点。
- **调度与 Web 解耦**：CLI + 系统 launchd/cron，不把定时寄生在 Web 进程里。

## 分层

```
sources/*.py (项目)         BaseSource 子类：fetch() + parse()
     ↓ raw → list[dict]
core/pipeline               校验(pydantic) → 收口(extra 折叠) → 写库 → 流水 → 健康检查
     ↓
storage/sqlite_sink         fxdb 基座：建表/补列 + upsert 去重 + 轮级备份
     ↓
SQLite 业务库 + 元信息库
     ↓ (extras)
extras/web  只读浏览    extras/llm  翻译润色    extras/tui  控制面板
统筹：core/runner（并发） + cli（fxharvest run / health / gen-launchd）
```

## 下游项目骨架

```
my_project/
├── pyproject.toml      # [tool.uv.sources] 本地路径引用 ../../fxharvest，按需 extras
├── config.toml         # 数据源开关/调度/筛选/通知
├── .env.local          # 密钥（openai key、webhook url）
├── fields.py           # JobRecord(HarvestRecord) —— 本项目标准字段
├── sources/            # 一源一文件，只写 fetch/parse
└── database/  logs/
```

## CLI

```bash
fxharvest list                 # 列出已发现的数据源
fxharvest run --all            # 跑一轮全部源
fxharvest run icbc apple       # 跑指定源
fxharvest health               # 数据健康检查（归零/骤降）
fxharvest gen-launchd          # 生成 macOS launchd plist
fxharvest web                  # 启动只读浏览 UI（需 [web]）
fxharvest tui                  # 启动本地控制面板（需 [tui]）
```

## 开发

```bash
uv venv && uv pip install -e ".[dev]"
uv run pytest
```
