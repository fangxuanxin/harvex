"""fxharvest 告警层——通用 Webhook 通知器。

支持三种推送协议：
- ``"bark"``：iOS Bark App，拼接 URL 路径方式推送。
- ``"feishu"``：飞书自定义机器人，JSON body。
- ``"serverchan"``：Server 酱（方糖），POST title/desp 参数。

网络异常全部降级为日志，绝不向调用方抛出异常。
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import httpx

from fxharvest.notify.notifier import NullNotifier, Notifier

logger = logging.getLogger(__name__)

# 支持的 webhook 类型白名单
_SUPPORTED_KINDS = {"bark", "feishu", "serverchan"}


class WebhookNotifier(Notifier):
    """通用 Webhook 通知器，支持 bark / feishu / serverchan 三种协议。

    Args:
        url:     Webhook 完整 URL。
                 - bark：``https://api.day.app/<key>``（不含 title/body 路径段）
                 - feishu：机器人 Webhook 完整地址
                 - serverchan：``https://sctapi.ftqq.com/<key>.send``
        kind:    推送协议，取值 ``"bark"`` / ``"feishu"`` / ``"serverchan"``，默认 ``"bark"``。
        timeout: HTTP 请求超时秒数，默认 10.0。
        client:  可注入自定义 httpx.Client（主要用于单元测试 mock）。
                 为 None 时自动创建默认客户端。
    """

    def __init__(
        self,
        url: str,
        *,
        kind: str = "bark",
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        if kind not in _SUPPORTED_KINDS:
            raise ValueError(
                f"不支持的 webhook kind: {kind!r}，"
                f"可选值：{sorted(_SUPPORTED_KINDS)}"
            )
        self._url = url
        self._kind = kind
        self._timeout = timeout
        # 若外部注入了 client（测试用途），则使用注入的，否则创建默认客户端
        self._client = client or httpx.Client(timeout=timeout)
        # 标记 client 是否由我们自己创建（用于 __del__ 时决定是否关闭）
        self._owns_client = client is None

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def notify(
        self,
        title: str,
        message: str,
        *,
        level: str = "info",
    ) -> None:
        """推送 Webhook 通知。网络异常降级为 ERROR 日志，不向外抛出。

        Args:
            title:   告警标题。
            message: 告警正文。
            level:   告警级别（bark 会作为图标/声音提示参考，其他渠道忽略）。
        """
        try:
            dispatch = {
                "bark": self._send_bark,
                "feishu": self._send_feishu,
                "serverchan": self._send_serverchan,
            }[self._kind]
            dispatch(title, message, level=level)
        except httpx.HTTPError as exc:
            # 网络/HTTP 层面的异常：降级为日志，主流程不受影响
            logger.error(
                "WebhookNotifier[%s] 推送失败（HTTP 异常）: %s  title=%r",
                self._kind,
                exc,
                title,
            )
        except Exception as exc:  # noqa: BLE001
            # 其余意外异常同样吞掉，保护主流程
            logger.error(
                "WebhookNotifier[%s] 推送失败（未知异常）: %s  title=%r",
                self._kind,
                exc,
                title,
            )

    def __del__(self) -> None:
        """析构时关闭自己创建的 httpx.Client。"""
        if self._owns_client:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # 各渠道私有发送方法
    # ------------------------------------------------------------------

    def _send_bark(self, title: str, message: str, *, level: str) -> None:
        """Bark 推送：拼接 URL 路径 ``<base_url>/<title>/<body>``。

        参考：https://bark.day.app/#/
        """
        # URL 编码标题和正文，避免特殊字符导致路径解析错误
        encoded_title = urllib.parse.quote(title, safe="")
        encoded_body = urllib.parse.quote(message, safe="")
        url = f"{self._url.rstrip('/')}/{encoded_title}/{encoded_body}"
        resp = self._client.get(url)
        resp.raise_for_status()
        logger.debug("Bark 推送成功: status=%d title=%r", resp.status_code, title)

    def _send_feishu(self, title: str, message: str, *, level: str) -> None:
        """飞书机器人推送：text 消息类型，body 含完整上下文。

        协议文档：https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
        Body 格式::

            {
                "msg_type": "text",
                "content": {"text": "..."}
            }
        """
        body: dict[str, Any] = {
            "msg_type": "text",
            "content": {
                "text": f"[{level.upper()}] {title}\n{message}",
            },
        }
        resp = self._client.post(self._url, json=body)
        resp.raise_for_status()
        logger.debug("飞书推送成功: status=%d title=%r", resp.status_code, title)

    def _send_serverchan(self, title: str, message: str, *, level: str) -> None:
        """Server 酱推送：POST title / desp 两个参数。

        协议文档：https://sct.ftqq.com/
        """
        body: dict[str, str] = {
            "title": f"[{level.upper()}] {title}",
            "desp": message,
        }
        resp = self._client.post(self._url, data=body)
        resp.raise_for_status()
        logger.debug("Server 酱推送成功: status=%d title=%r", resp.status_code, title)

    # ------------------------------------------------------------------
    # 工厂方法
    # ------------------------------------------------------------------

    @staticmethod
    def from_config(cfg: dict[str, Any]) -> Notifier:
        """从配置字典构造 Notifier。

        若 ``cfg`` 中缺少 ``url`` 键或 url 为空字符串，
        则返回 NullNotifier（静默降级，不抛出异常）。

        Args:
            cfg: 配置字典，支持的键：
                 - ``url``（必填，缺失则返回 NullNotifier）
                 - ``kind``（可选，默认 ``"bark"``）
                 - ``timeout``（可选，默认 ``10.0``）

        Returns:
            WebhookNotifier 或 NullNotifier。

        Example::

            notifier = WebhookNotifier.from_config({
                "url": "https://api.day.app/mykey",
                "kind": "bark",
            })
        """
        url: str = cfg.get("url", "")
        if not url:
            logger.debug("webhook.from_config: url 为空，返回 NullNotifier")
            return NullNotifier()

        kind: str = cfg.get("kind", "bark")
        timeout: float = float(cfg.get("timeout", 10.0))
        return WebhookNotifier(url, kind=kind, timeout=timeout)


__all__ = ["WebhookNotifier"]
