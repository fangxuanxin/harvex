# harvex

[English](README.md) · **简体中文** · [日本語](README.ja.md)

**AI 时代的数据采集基座** —— 为 AI agent 与 vibecoding 打造的零样板数据采集框架。

让 AI（或你自己 vibecoding）只写它最擅长的一件事 —— *怎么抓、怎么解析* —— 其余全部交给框架：并发调度、字段收口、写库去重、运行流水、HTTP 重试、日志、告警、数据健康检查、定时调度、Web 浏览 UI、LLM 翻译增强、TUI 控制面板。

```bash
pip install harvex                              # 核心，零重依赖
pip install "harvex[web,llm,browser,tui]"       # 按需启用扩展
```

## 为什么是「AI 时代的采集基座」

让 LLM 写爬虫时，模型最擅长「这个页面/接口怎么解析成结构化数据」，最不擅长、也最容易写错的是周边工程：重试退避、并发隔离、增量去重、schema 漂移、调度、可观测。harvex 把后者全部沉淀成稳定基座，给 AI 留下一个**极窄、极稳的契约面**：

```python
from harvex import BaseSource, SourceProfile

class GithubTrending(BaseSource):
    profile = SourceProfile(slug="gh_trending", name="GitHub Trending")

    def fetch(self):
        return self.ctx.http.get_json("https://api.example.com/trending")

    def parse(self, raw):
        for item in raw["items"]:
            yield {"标题": item["name"], "star": item["stars"]}
```

AI 只要产出这样一个类，`harvex run` 就能跑通采集 → 校验 → 去重 → 入库 → 流水 → 健康检查全链路。新增字段不会撑爆主表（自动折叠进 `extra` 列），一个源挂掉不影响整轮，脏数据写库前被拦截。

## 设计原则

- **核心零重依赖**：core 只依赖 `pydantic` / `httpx` / `tenacity`。`playwright`、`openai`、Web、TUI 都是按需安装的 `extras`。
- **字段收口是框架契约**：用 `HarvestRecord`（pydantic v2）守住「不让主表变稀疏矩阵」的纪律，未声明字段自动折叠，脏数据写库前拦截。
- **故障隔离**：一个源挂掉不影响整轮抓取。
- **存储先 SQLite，签名预留 Sink 抽象**：开箱即用，又留好扩展接入点。
- **调度与 Web 解耦**：CLI + 系统 launchd/cron，不把定时寄生在 Web 进程里。

## 分层

```
sources/*.py (你/AI 写)      BaseSource 子类：fetch() + parse()
     ↓ raw → list[dict]
core/pipeline               校验(pydantic) → 收口(extra 折叠) → 写库 → 流水 → 健康检查
     ↓
storage/sqlite_sink         建表/补列 + upsert 去重 + 轮级备份
     ↓
SQLite 业务库 + 元信息库
     ↓ (extras)
extras/web  只读浏览    extras/llm  翻译润色    extras/tui  控制面板
统筹：core/runner（并发） + cli（harvex run / health / gen-launchd）
```

## 新项目骨架

```
my_project/
├── config.toml         # 数据源开关/调度/筛选/通知
├── .env.local          # 密钥（openai key、webhook url）
├── fields.py           # 你的 HarvestRecord 子类 —— 标准字段
├── sources/            # 一源一文件，只写 fetch/parse
└── database/  logs/
```

完整可跑模板见 [`templates/project/`](templates/project)。

## CLI

```bash
harvex list                 # 列出已发现的数据源
harvex run --all            # 跑一轮全部源
harvex run gh_trending      # 跑指定源
harvex health               # 数据健康检查（归零/骤降）
harvex gen-launchd          # 生成 macOS launchd 定时配置
harvex gen-cron             # 生成 crontab 行
harvex web                  # 启动只读浏览 UI（需 [web]）
harvex tui                  # 启动本地控制面板（需 [tui]）
```

## 开发

```bash
uv venv && uv pip install -e ".[dev]"
uv run pytest
```

## 许可证

MIT
