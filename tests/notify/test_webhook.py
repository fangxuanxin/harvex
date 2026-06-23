"""notify 层测试：WebhookNotifier 构造与降级。"""

from __future__ import annotations

import json

import httpx

from fxharvest.notify.notifier import NullNotifier
from fxharvest.notify.webhook import WebhookNotifier


def test_feishu_body_构造():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"code": 0})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    n = WebhookNotifier("https://feishu/hook", kind="feishu", client=client)
    n.notify("标题", "正文内容", level="error")

    body = captured["body"]
    assert body["msg_type"] == "text"
    assert "正文内容" in body["content"]["text"]
    client.close()


def test_network_error_does_not_raise():
    def handler(request):
        raise httpx.ConnectError("boom")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    n = WebhookNotifier("https://x", kind="bark", client=client)
    # 告警失败绝不能反过来炸主流程
    n.notify("t", "m")
    client.close()


def test_from_config_degrades_to_null():
    assert isinstance(WebhookNotifier.from_config({}), NullNotifier)
    assert isinstance(WebhookNotifier.from_config({"url": ""}), NullNotifier)
    assert isinstance(WebhookNotifier.from_config({"url": "https://x", "kind": "bark"}), WebhookNotifier)
