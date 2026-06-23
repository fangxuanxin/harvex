"""SourceContext：注入给每个 Source 实例的运行期上下文。

把「源不该自己创建」的横切设施（HTTP 客户端、日志器、时钟、配置、run_id）
集中注入，便于测试替身、统一超时/重试/UA，并让源代码保持纯粹。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # 仅类型，避免运行时强依赖 net 层
    import logging

    from ..net.http_client import HttpClient


def _default_clock() -> datetime:
    """默认时钟：返回带时区的当前时间（便于测试注入固定时钟）。"""
    return datetime.now(timezone.utc)


@dataclass
class SourceContext:
    """单个源在一轮抓取中的上下文。由 pipeline 为每个源构造。"""

    profile: Any                                   # SourceProfile（避免循环导入用 Any）
    http: "HttpClient"                             # 统一 HTTP 客户端（net.http_client）
    logger: "logging.Logger"                       # 已绑定 source/run_id tag 的日志器
    config: Mapping[str, Any] = field(default_factory=dict)  # 合并后的源配置
    run_id: int | None = None                      # 本轮 crawl_runs 的 run_id
    clock: Callable[[], datetime] = _default_clock

    def now(self) -> datetime:
        """当前时间（走可注入时钟，测试可冻结）。"""
        return self.clock()


__all__ = ["SourceContext"]
