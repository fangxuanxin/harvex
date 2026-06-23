"""HTTP 客户端模块（网络韧性层核心）。

对 httpx.Client 做薄封装，统一处理：
- 超时与连接池配置
- User-Agent 注入
- 自动重试（指数退避 + 抖动）
- 非 2xx 响应的异常包装（统一转为 FetchError）
- 上下文管理器支持（自动关闭底层连接）
"""

from __future__ import annotations

from typing import Any

import httpx

from fxharvest.core.errors import FetchError
from fxharvest.net.retry import DEFAULT_RETRY, RetryPolicy, build_retrying

# 默认 User-Agent：伪装为常见桌面浏览器，减少被反爬拦截的概率
_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class HttpClient:
    """基于 httpx 同步客户端的薄封装，提供统一的超时/重试/UA 策略。

    使用示例::

        # 作为上下文管理器（推荐，自动关闭连接）
        with HttpClient() as client:
            resp = client.get("https://example.com")
            data = client.get_json("https://api.example.com/data")

        # 手动管理生命周期
        client = HttpClient(timeout=30.0, retry=RetryPolicy(attempts=5))
        try:
            resp = client.get("https://example.com")
        finally:
            client.close()
    """

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        user_agent: str | None = None,
        headers: dict | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        """初始化 HttpClient。

        Args:
            timeout:    请求超时秒数（connect + read 共用同一数值）。
            user_agent: 自定义 User-Agent；为 None 则使用内置浏览器 UA。
            headers:    额外的默认请求头，与 User-Agent 合并。
            retry:      重试策略；为 None 则使用 DEFAULT_RETRY（3 次，指数退避）。
        """
        # 合并请求头：先设 UA，再叠加调用方传入的自定义头
        merged_headers: dict[str, str] = {
            "User-Agent": user_agent or _DEFAULT_UA,
        }
        if headers:
            merged_headers.update(headers)

        # 构造底层 httpx 同步客户端
        # limits 控制连接池大小，follow_redirects 默认跟随 3xx
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            headers=merged_headers,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30.0,
            ),
        )

        # 构造 tenacity Retrying 对象，供每次请求复用
        effective_policy = retry if retry is not None else DEFAULT_RETRY
        self._retrying = build_retrying(effective_policy)

    # ------------------------------------------------------------------
    # 核心请求方法
    # ------------------------------------------------------------------

    def get(self, url: str, **kw: Any) -> httpx.Response:
        """发送 GET 请求，带重试与异常包装。

        Args:
            url: 目标 URL。
            **kw: 透传给 httpx.Client.get 的额外参数（params、headers 等）。

        Returns:
            httpx.Response（状态码 2xx）。

        Raises:
            FetchError: 网络错误、超时、或响应状态码非 2xx。
        """
        return self._request("GET", url, **kw)

    def get_json(self, url: str, **kw: Any) -> Any:
        """发送 GET 请求并自动解析 JSON 响应体。

        Args:
            url: 目标 URL。
            **kw: 透传给 get() 的额外参数。

        Returns:
            解析后的 Python 对象（dict / list / ...）。

        Raises:
            FetchError: 网络错误或响应非 2xx。
            ValueError: 响应体不是合法 JSON（由 httpx 抛出）。
        """
        return self.get(url, **kw).json()

    def post(self, url: str, **kw: Any) -> httpx.Response:
        """发送 POST 请求，带重试与异常包装。

        Args:
            url: 目标 URL。
            **kw: 透传给 httpx.Client.post 的额外参数（json=、data=、content= 等）。

        Returns:
            httpx.Response（状态码 2xx）。

        Raises:
            FetchError: 网络错误、超时、或响应状态码非 2xx。
        """
        return self._request("POST", url, **kw)

    # ------------------------------------------------------------------
    # 生命周期管理
    # ------------------------------------------------------------------

    def close(self) -> None:
        """显式关闭底层 httpx.Client，释放连接池资源。"""
        self._client.close()

    def __enter__(self) -> "HttpClient":
        """进入上下文，返回自身。"""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """离开上下文时自动关闭连接。"""
        self.close()

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        """统一的请求执行入口，含重试与异常包装逻辑。

        重试触发条件（由 retry.py 的 _is_retryable 判定）：
        - httpx.TransportError（连接层故障、读超时等）
        - httpx.HTTPStatusError（5xx 服务端错误）
        - FetchError（框架层抓取失败）

        Args:
            method: HTTP 方法字符串（"GET" / "POST"）。
            url:    目标 URL。
            **kw:   透传给 httpx.Client.request 的参数。

        Returns:
            httpx.Response（已确认 2xx）。

        Raises:
            FetchError: 包装所有最终失败的异常。
        """
        try:
            # tenacity Retrying 作为上下文管理器驱动重试循环
            for attempt in self._retrying:
                with attempt:
                    resp = self._client.request(method, url, **kw)
                    # 非 2xx 抛出 HTTPStatusError，触发重试逻辑（5xx）或直接向上传播（4xx）
                    resp.raise_for_status()
            # 重试成功后，attempt.retry_state.outcome 持有最终结果
            # tenacity 会在 for 循环体正常退出后将 resp 保留在局部作用域
            return resp  # type: ignore[return-value]
        except httpx.HTTPStatusError as exc:
            # HTTP 错误（包括 4xx 和重试耗尽后的 5xx）包装为 FetchError
            raise FetchError(
                f"HTTP {exc.response.status_code} 请求失败：{method} {url}"
            ) from exc
        except httpx.TransportError as exc:
            # 网络层错误（超时、连接拒绝等）包装为 FetchError
            raise FetchError(
                f"网络传输错误（{type(exc).__name__}）：{method} {url}"
            ) from exc


__all__ = ["HttpClient"]
