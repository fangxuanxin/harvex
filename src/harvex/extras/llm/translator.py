"""LLM 翻译器模块。

提供 Translator 类，封装 OpenAI Chat Completions API 调用，
支持结果缓存（避免重复花钱）、失败重试、无 key 时优雅降级。

openai 库为可选依赖（extras/llm），仅在函数内部惰性导入，
未安装或无 API key 时抛出 ConfigError，不影响框架其他模块。
"""

from __future__ import annotations

import os
import time
from typing import Any

from harvex.core.errors import ConfigError
from harvex.extras.llm.cache import TranslationCache


# 每次重试之间的基础等待秒数（指数退避：backoff * 2^n）
_BASE_BACKOFF: float = 0.5


def _build_translate_prompt(text: str, target: str) -> str:
    """构造单条翻译的 system prompt。"""
    return (
        f"你是专业翻译。将以下文本翻译为「{target}」语言，"
        "只输出译文，不加任何解释、引号或额外内容。"
    )


class Translator:
    """LLM 翻译器。

    支持：
    - 可注入假 client（便于单元测试，无需真实调用 OpenAI）
    - 结果缓存（TranslationCache），命中时直接返回，不调用 LLM
    - 失败自动重试（指数退避）
    - 无 openai 库或无 API key 时抛出 ConfigError

    示例（生产用法）::

        translator = Translator(api_key="sk-...")
        zh_text = translator.translate("Hello world", target="zh")

    示例（测试用法，注入假 client）::

        translator = Translator(client=fake_client)
        zh_text = translator.translate("Hello world", target="zh")
    """

    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        cache: TranslationCache | None = None,
        max_retries: int = 3,
        client: Any = None,
    ) -> None:
        """初始化翻译器。

        Args:
            model:       OpenAI 模型名称，默认 gpt-4o-mini。
            api_key:     OpenAI API key。为 None 时读取环境变量 OPENAI_API_KEY。
            cache:       翻译缓存实例。为 None 时不缓存（每次调用都走 LLM）。
            max_retries: LLM 调用失败时的最大重试次数（不含首次），默认 3。
            client:      可注入的 OpenAI 兼容 client（duck-typing）。
                         非 None 时跳过 openai 库初始化，便于测试。
        """
        self.model = model
        self.cache = cache
        self.max_retries = max_retries

        # 若外部注入了 client，直接使用，跳过 openai 库初始化
        if client is not None:
            self._client = client
            return

        # 惰性导入 openai，未安装时给出清晰错误信息
        try:
            import openai  # noqa: PLC0415
        except ImportError as exc:
            raise ConfigError(
                "openai 库未安装。请执行：uv add 'harvex[llm]' 或 uv add openai"
            ) from exc

        # 确认 API key 可用（优先参数，其次环境变量）
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not resolved_key:
            raise ConfigError(
                "缺少 OpenAI API key。请传入 api_key 参数，"
                "或设置环境变量 OPENAI_API_KEY。"
            )

        self._client = openai.OpenAI(api_key=resolved_key)

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def translate(self, text: str, *, target: str = "zh") -> str:
        """翻译单条文本。

        空字符串直接返回空字符串（不调用 LLM，不查缓存）。

        Args:
            text:   待翻译的源文本。
            target: 目标语言代码（如 "zh"、"en"、"ja"），默认中文。

        Returns:
            译文字符串。

        Raises:
            ConfigError: openai 未安装或未提供 API key 且未注入 client。
        """
        # 空串短路：零成本返回
        if not text:
            return ""

        # 查询缓存
        if self.cache is not None:
            cached = self.cache.get(text, target=target, model=self.model)
            if cached is not None:
                return cached

        # 调用 LLM（带重试）
        translation = self._call_with_retry(text, target=target)

        # 写入缓存
        if self.cache is not None:
            self.cache.put(text, translation, target=target, model=self.model)

        return translation

    def translate_batch(
        self, texts: list[str], *, target: str = "zh"
    ) -> list[str]:
        """批量翻译文本列表，缓存命中的条目跳过 LLM 调用。

        空字符串项同样直接短路返回空串。

        Args:
            texts:  待翻译的文本列表。
            target: 目标语言代码，默认中文。

        Returns:
            与输入列表等长的译文列表，顺序一一对应。
        """
        results: list[str] = []
        for text in texts:
            results.append(self.translate(text, target=target))
        return results

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _call_with_retry(self, text: str, *, target: str) -> str:
        """调用 LLM，失败时指数退避重试。

        Args:
            text:   待翻译文本。
            target: 目标语言代码。

        Returns:
            译文字符串。

        Raises:
            最后一次失败的异常（在所有重试耗尽后透传）。
        """
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return self._call_llm(text, target=target)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self.max_retries:
                    # 指数退避：0.5s → 1s → 2s → ...
                    wait = _BASE_BACKOFF * (2 ** attempt)
                    time.sleep(wait)

        # 所有重试耗尽，抛出最后一次异常
        raise last_exc  # type: ignore[misc]

    def _call_llm(self, text: str, *, target: str) -> str:
        """单次调用 LLM 的最小单元（无重试逻辑）。

        Args:
            text:   待翻译文本。
            target: 目标语言代码。

        Returns:
            LLM 返回的译文字符串（去除首尾空白）。
        """
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": _build_translate_prompt(text, target),
                },
                {
                    "role": "user",
                    "content": text,
                },
            ],
        )
        # 兼容真实 openai 对象与 duck-typing 假对象
        content = response.choices[0].message.content
        return (content or "").strip()


__all__ = ["Translator"]
