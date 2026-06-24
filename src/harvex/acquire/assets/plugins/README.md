# harvex 采集方式插件（assets/plugins）

每种「数据采集方式」是一个自包含插件目录。框架自带的放在这里随包发布；
下游项目也可在自己的 `assets/plugins/` 放同构插件，由 `PluginRegistry.discover()` 一并发现。

> 设计立场：本目录是**铺垫**。每个插件的 `acquirer.py` 只搭好初始化与生命周期骨架，
> 具体取数逻辑（`acquire()`）刻意留空，交给将来的 AI 服务按目标接口补全。

## 目录约定

```
<kind>/
├── plugin.toml          # 清单（必需）
├── acquirer.py          # Acquirer 子类（必需）
└── assets/              # 自带脚本/模板（可选，自包含、不联网拉取）
```

## plugin.toml 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `kind` | ✓ | 类型唯一标识（如 `http`） |
| `name` | ✓ | 人类可读名称 |
| `version` | | 插件版本 |
| `description` | | 一句话说明 |
| `entry` | | Acquirer 所在文件，默认 `acquirer.py` |
| `class_name` | | Acquirer 子类名（留空则取模块内首个） |
| `requires` | | 额外 pip 依赖（空=仅核心） |
| `assets` | | 自带文件清单（相对插件目录） |
| `platforms` | | 适用平台：`any` / `macos` / `linux` … |

## 自带插件

| kind | 采集方式 | 依赖 | 平台 |
|---|---|---|---|
| `http` | 传统 HTTP（httpx，带重试） | 核心 | any |
| `playwright_headless` | 无头浏览器渲染 | `harvex[browser]` | any |
| `applescript_browser` | 操控 macOS 默认浏览器 + JS 注入 | 系统 osascript | macos |

## 写一个 Acquirer（契约）

```python
from harvex.acquire import Acquirer, AcquireResult

class MyAcquirer(Acquirer):
    kind = "my_kind"
    def setup(self): ...                 # 建连接/启浏览器/定位 assets
    def acquire(self) -> AcquireResult:  # 取回原始数据，交给 Source.parse()
        ...
    def teardown(self): ...              # 释放资源
```

## 加载与使用

```python
from harvex.acquire import PluginRegistry, AcquireContext

reg = PluginRegistry().discover()                 # 自带 + 可传项目插件目录
print(reg.kinds())                                # ['applescript_browser', 'http', 'playwright_headless']
acq = reg.create("http", AcquireContext(url="https://api.example.com", http=client))
with acq:
    result = acq.acquire()                        # → AcquireResult(raw=..., ...)
```
