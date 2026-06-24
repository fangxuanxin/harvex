"""网络重试策略模块。

提供 RetryPolicy dataclass 与 build_retrying 工厂函数，
基于 tenacity 实现指数退避 + 抖动的重试逻辑，
只对可重试的网络异常（TransportError、5xx、FetchError）触发重试。
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import httpx
import tenacity

from harvex.core.errors import FetchError


@dataclass
class RetryPolicy:
    """HTTP 重试策略配置。

    Attributes:
        attempts:    最大重试次数（含第一次请求）。
        backoff:     指数退避的基础等待秒数。
        max_backoff: 单次等待的上限秒数，防止退避时间无限增长。
        jitter:      是否在退避时间上叠加随机抖动，避免惊群效应。
    """

    attempts: int = 3
    backoff: float = 0.5
    max_backoff: float = 8.0
    jitter: bool = True


def _is_retryable(exc: BaseException) -> bool:
    """判断异常是否属于可重试类型。

    可重试条件：
    - httpx.TransportError：连接层错误（超时、连接拒绝等）
    - httpx.HTTPStatusError：HTTP 5xx 服务端错误
    - FetchError：框架层抓取失败
    """
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        # 只有 5xx 才值得重试；4xx 是客户端问题，重试无意义
        return exc.response.status_code >= 500
    if isinstance(exc, FetchError):
        return True
    return False


def build_retrying(policy: RetryPolicy) -> tenacity.Retrying:
    """根据 RetryPolicy 构造 tenacity.Retrying 对象。

    使用指数退避策略：第 n 次重试等待 backoff * 2^(n-1) 秒，
    并可叠加 [0, backoff] 范围内的均匀随机抖动。
    最终等待时间被 max_backoff 截断。

    Args:
        policy: 重试策略配置实例。

    Returns:
        可直接用于 `with retrying: ...` 或 `for attempt in retrying:` 的 Retrying 对象。
    """
    # 指数退避：wait = backoff * 2^(retry_number - 1)
    wait_strategy: tenacity.wait.wait_base = tenacity.wait_exponential(
        multiplier=policy.backoff,
        min=policy.backoff,
        max=policy.max_backoff,
    )

    # 可选叠加随机抖动，降低并发请求的"惊群"效应
    if policy.jitter:
        wait_strategy = tenacity.wait_combine(
            wait_strategy,
            tenacity.wait_random(min=0, max=policy.backoff),
        )

    return tenacity.Retrying(
        # 最多尝试 attempts 次（含第一次）
        stop=tenacity.stop_after_attempt(policy.attempts),
        # 等待策略
        wait=wait_strategy,
        # 只对可重试异常触发重试，其余异常立即透传
        retry=tenacity.retry_if_exception(_is_retryable),
        # 重试耗尽后重新抛出最后一个异常，而非包装成 RetryError
        reraise=True,
    )


# 开箱即用的默认重试策略实例
DEFAULT_RETRY = RetryPolicy()


__all__ = [
    "RetryPolicy",
    "DEFAULT_RETRY",
    "build_retrying",
]
