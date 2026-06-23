"""fxharvest 告警层——通知器抽象基类与空实现。

设计原则：
- Notifier 是抽象接口，任何具体推送渠道（webhook、邮件、企微等）都实现它。
- NullNotifier 是「什么都不做」的默认实现，用于未配置告警时占位，
  保证上层代码无需判空，直接调用 notify() 即可。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Notifier(ABC):
    """告警通知器抽象基类。

    所有实现必须保证 notify() 不抛出异常——告警失败只应降级为日志，
    绝不能反过来影响主采集流程。
    """

    @abstractmethod
    def notify(
        self,
        title: str,
        message: str,
        *,
        level: str = "info",
    ) -> None:
        """推送一条告警通知。

        Args:
            title:   告警标题，简短说明事件类型（如 "抓取失败"）。
            message: 告警正文，描述详细信息。
            level:   告警级别，语义提示，不同渠道可用来控制样式；
                     取值建议：``"info"`` / ``"warning"`` / ``"error"``。
        """


class NullNotifier(Notifier):
    """空实现通知器——未配置告警渠道时的默认占位。

    notify() 仅将调用记录为 debug 日志，不做任何实际推送。
    """

    def notify(
        self,
        title: str,
        message: str,
        *,
        level: str = "info",
    ) -> None:
        """记录 debug 日志，不推送任何外部渠道。"""
        logger.debug(
            "NullNotifier.notify 被调用（未配置推送渠道）: "
            "level=%s title=%r message=%r",
            level,
            title,
            message,
        )


__all__ = ["Notifier", "NullNotifier"]
