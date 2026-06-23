"""共享 fixture 定义。

包含：
- tmp_db：基于 tmp_path 的临时 SQLite 路径（字符串）
- job_record_cls：一个具体的 JobRecord(HarvestRecord) 子类，
  包含「职位名称」「公司」两个去重键，extra_column='扩展信息'
- mock_http：注入 httpx.MockTransport 的 HttpClient，不发真实请求
"""
from __future__ import annotations

import httpx
import pytest

from fxharvest.core.record import HarvestRecord
from fxharvest.net.http_client import HttpClient
from fxharvest.net.retry import RetryPolicy


@pytest.fixture()
def tmp_db(tmp_path):
    """返回临时数据库文件路径字符串（调用方可直接传给 FxDatabase 或 SQLiteSink）。"""
    return str(tmp_path / "test.db")


@pytest.fixture()
def job_record_cls():
    """返回一个 JobRecord 类（每次调用返回同一个类定义，可安全重复使用）。

    dedup_keys = ('职位名称', '公司')
    extra_column = '扩展信息'
    """
    class JobRecord(HarvestRecord):
        """用于测试的招聘记录模型。"""
        职位名称: str
        公司: str
        地点: str = ""

        # 去重键：职位名称 + 公司 组合唯一
        dedup_keys = ("职位名称", "公司")
        # extra 列名
        extra_column = "扩展信息"

    return JobRecord


@pytest.fixture()
def mock_http():
    """返回使用 httpx.MockTransport 构造的 HttpClient，不发出真实网络请求。

    默认 transport 始终返回 200 OK（携带空 JSON body）。
    若需要自定义响应序列，在测试内直接构造带 MockTransport 的 HttpClient。
    """
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(_handler)
    # 无重试、快速超时，测试快跑
    policy = RetryPolicy(attempts=1, backoff=0.0, jitter=False)
    # httpx.Client 可以直接接收 transport 参数
    client = HttpClient.__new__(HttpClient)
    client._client = httpx.Client(transport=transport)
    from fxharvest.net.retry import build_retrying
    client._retrying = build_retrying(policy)
    yield client
    client.close()
