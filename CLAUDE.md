# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

harvex 是「AI 时代的数据采集基座」——一个发布到 PyPI 的框架库，定位是让 AI / vibecoding
只写「怎么抓、怎么解析」，其余工程（并发、去重、流水、重试、调度、可观测、扩展）由框架兜底。

> 代码注释用中文（沿用作者全局约定）；面向用户的文档（README/PyPI 描述）英文为主，
> 中(`README.zh-CN.md`)/日(`README.ja.md`)为备选。

## 常用命令

```bash
uv venv && uv pip install -e ".[dev]"     # 装开发环境（禁用系统 Python，一律 uv）
uv run pytest                              # 全量测试（零真实网络/OpenAI/浏览器）
uv run pytest tests/core/test_pipeline_runner.py::test_fault_isolation_and_dedup  # 跑单个用例
uv build                                  # 构建 sdist + wheel
uv run harvex --project <dir> run --all   # 在某项目目录跑一轮采集（冒烟）
```

发布（**不可逆，且需作者审核后才执行**）：
```bash
UV_PUBLISH_TOKEN='<token>' uv publish     # token 绝不写入文件或提交
git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z
```
PyPI 项目 `harvex` / GitHub `fangxuanxin/harvex`。**PyPI 版本号一经发布不可覆盖/复用**——
改动要发新版本号；发布前先在 PyPI 网页删除任何含错误元数据的旧 release。

## 架构大图

数据沿这条链流动，**职责严格分层**：

```
sources/*.py (下游项目/AI 写)   BaseSource 子类：只写 fetch() + parse()
   ↓ raw dict
core/pipeline                  校验(HarvestRecord) → 字段收口 → 写库 → 元数据流水 → 健康检查
   ↓
storage/sqlite_sink (Sink)     建表/补列 + upsert 去重 + 轮级备份
   ↓
SQLite 业务库 + 独立元信息库
```
编排：`core/runner.run_sources` 并发统筹；`cli/main.build_app` 把 config+registry+各层组装成 `App`。

### 必须理解的几个契约与不变量（改动前务必读懂）

- **字段收口是核心契约**（`core/record.py`）：下游用 `HarvestRecord` 子类声明标准字段；
  `from_raw()` 把未声明字段折叠进 `extra` 列（入库为 JSON），`dedup_keys` 决定 upsert 唯一键。
  这是「不让主表变稀疏矩阵」的纪律，别绕过它直接拼字典写库。

- **Source 只负责 fetch/parse**（`core/source.py`）：校验、收口、写库、流水、健康、并发、告警
  全在框架侧。给 Source 加“工程能力”是错的方向——那些属于框架层。

- **Pipeline 两阶段是为绕开 SQLite 跨线程**（`core/pipeline.py`）：`collect()`（fetch/parse，
  网络密集）在线程池并行；`persist()`（所有 DB 操作）只在主线程串行。`runner` 据此编排。
  **不要把写库挪进并发阶段。** 健康检查必须在 `finish_crawl` 之前取历史基准。

- **Web 读路径的线程安全**（`extras/web/`）：ThreadingHTTPServer 每请求一线程，故 `queries.py`
  每次开 `readonly_connect()` 独立只读连接，**不复用 sink 的主线程写连接**；meta 库用
  `check_same_thread=False`。新增 web 端点查库时照此办，别碰共享写连接。

- **核心零重依赖边界**（`pyproject.toml`）：core 只依赖 pydantic/httpx/tenacity。
  `playwright`/`openai`/`parsel` 等属 extras（`[browser]`/`[llm]`/`[parse]`），**必须惰性 import**
  （在函数内 try-import，未装时抛 `ConfigError` 带安装指引），保证未装 extras 时核心可正常 import。

- **源发现按模块归属**（`core/registry.py`）：`discover_dir` 只注册“定义在该模块内”的 BaseSource
  子类，不走全局 `__subclasses__()` 扫描（否则多次发现会 slug 误冲突）。

- **采集方式插件层**（`acquire/`）：`Acquirer` 契约 + `PluginRegistry` 从
  `acquire/assets/plugins/<kind>/`（`plugin.toml` + `acquirer.py` + 自带脚本）发现加载。
  自带三种（`http`/`playwright_headless`/`applescript_browser`）**是有意的铺垫骨架**——
  `acquire()` 抛 `NotImplementedError`，文档串写好实现指引，留给 AI 服务按目标接口补全。
  填实现时改对应插件的 `acquirer.py`，别动 `base.py` 契约。

- **非 .py 资源靠包内目录随 wheel 发布**：web 前端、acquire 插件脚本都放在 `src/harvex/` 下
  （hatchling 会打包包目录内的所有文件）。新增此类资源务必放在包目录内，否则装包后丢失；
  发版后用 `unzip -l dist/*.whl` 确认资源已打进去。

- **`__version__` 从已安装包元数据动态读取**（`__init__.py`）：版本号**只在 pyproject 改一处**，
  别在代码里再硬编码。

## 测试约定

`tests/` 按层镜像 `src/`。一律用临时 DB（`tmp_path`）+ `httpx.MockTransport`，
不打真实网络/OpenAI/浏览器。acquire 插件当前是骨架，测试只验证「发现/清单/加载」管线，
`acquire()` 抛 `NotImplementedError` 属预期。
