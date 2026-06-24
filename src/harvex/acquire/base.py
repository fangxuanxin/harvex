"""采集方式（Acquirer）抽象层 —— 「怎么把原始数据取回来」的可插拔策略。

设计定位（重要）：
- Source 负责「抓什么 + 怎么解析」（fetch/parse）；Acquirer 负责「用哪种方式取回原始数据」。
- 本层是**铺垫层**：基类只定义契约与初始化骨架（生命周期 setup→acquire→teardown），
  各采集方式的**具体取数逻辑刻意不在此实现**，留给将来的 AI 服务在对应插件的
  `acquire()` 里填写。这样既统一了接口，又不锁死实现细节。

采集方式以「插件」形式存在于 `acquire/assets/plugins/<kind>/`，每个插件自包含
（manifest + acquirer 骨架 + 自带脚本资源），由 registry 在运行时发现与加载。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar


@dataclass
class AcquireContext:
    """采集运行期上下文，由框架（或调用方）注入给 Acquirer。

    不同采集方式按需取用其中字段：http 类用 ``http``；浏览器/AppleScript 类
    用 ``url`` + ``assets_dir``（定位自带脚本）；``config`` 透传源级别参数。
    """

    url: str | None = None                       # 目标地址（页面型采集的导航目标）
    config: Mapping[str, Any] = field(default_factory=dict)  # 源/插件级配置
    http: Any = None                             # HttpClient（http 类采集复用框架客户端）
    logger: Any = None                           # 日志器
    assets_dir: Path | None = None               # 该插件的本地 assets 目录（脚本/模板）
    extra: dict[str, Any] = field(default_factory=dict)      # 预留扩展位


@dataclass
class AcquireResult:
    """采集产物：原始数据 + 元信息。直接交给 Source.parse() 继续解析。"""

    raw: Any                                      # 原始数据：HTML / JSON / bytes / 中间结构
    content_type: str | None = None              # 形态提示，便于 parse 分流（html/json/...）
    url: str | None = None                       # 实际取数的最终 URL（含重定向后）
    meta: dict[str, Any] = field(default_factory=dict)       # 状态码、耗时、截图路径等


class Acquirer(ABC):
    """采集方式插件的基类。

    生命周期：``setup() → acquire() → teardown()``，亦支持 ``with`` 上下文。
    子类**必须**声明 ``kind``（与 plugin.toml 对应）并实现 ``acquire()``；
    ``setup``/``teardown`` 视资源（连接/浏览器进程）需要覆盖。

    注意：这是铺垫骨架。框架自带插件的 ``acquire()`` 默认抛 NotImplementedError，
    并在文档串里写明该如何实现——交由后续 AI 服务补全。
    """

    #: 插件类型标识，必须与 plugin.toml 的 ``kind`` 一致（如 "http"）。
    kind: ClassVar[str] = ""

    def __init__(self, context: AcquireContext) -> None:
        self.ctx = context
        self._ready = False

    # ---- 生命周期（初始化铺垫，子类按需覆盖）----
    def setup(self) -> None:
        """初始化资源（建连接 / 启浏览器 / 定位脚本资源）。默认仅置就绪标记。"""
        self._ready = True

    @abstractmethod
    def acquire(self) -> AcquireResult:
        """执行采集并返回 AcquireResult。**由具体插件实现。**"""

    def teardown(self) -> None:
        """释放资源（关连接 / 退出浏览器）。默认 no-op。"""
        self._ready = False

    # ---- 上下文管理器糖 ----
    def __enter__(self) -> "Acquirer":
        self.setup()
        return self

    def __exit__(self, *exc: object) -> None:
        self.teardown()


__all__ = ["Acquirer", "AcquireContext", "AcquireResult"]
