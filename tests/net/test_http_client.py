"""net 层测试：HttpClient 重试与异常包装（全程 MockTransport，不发真实请求）。"""

from __future__ import annotations

import httpx
import pytest

from fxharvest.core.errors import FetchError
from fxharvest.net.http_client import HttpClient
from fxharvest.net.retry import RetryPolicy, build_retrying


def _client_with(handler, *, attempts=3) -> HttpClient:
    """用给定 handler 构造一个走 MockTransport 的 HttpClient。"""
    client = HttpClient.__new__(HttpClient)
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    client._retrying = build_retrying(RetryPolicy(attempts=attempts, backoff=0.0, jitter=False))
    return client


def test_retry_then_success():
    """先两次 500 后 200：重试最终成功。"""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500)
        return httpx.Response(200, json={"ok": True})

    c = _client_with(handler, attempts=3)
    resp = c.get("http://fake/api")
    assert resp.status_code == 200
    assert calls["n"] == 3
    c.close()


def test_persistent_500_raises_fetcherror():
    """持续 500：重试耗尽后抛 FetchError。"""
    def handler(request):
        return httpx.Response(500)

    c = _client_with(handler, attempts=3)
    with pytest.raises(FetchError):
        c.get("http://fake/api")
    c.close()


def test_4xx_does_not_retry():
    """4xx 不应重试，直接抛 FetchError。"""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404)

    c = _client_with(handler, attempts=3)
    with pytest.raises(FetchError):
        c.get("http://fake/api")
    assert calls["n"] == 1  # 仅一次，未浪费重试
    c.close()


def test_get_json_parses_body():
    def handler(request):
        return httpx.Response(200, json={"k": "v", "num": 42})

    c = _client_with(handler)
    assert c.get_json("http://fake/api") == {"k": "v", "num": 42}
    c.close()
