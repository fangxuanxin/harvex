"""LLM 文本增强模块。

提供 summarize 函数，将长文本压缩为「一句话描述」。
同样使用惰性 openai 导入，支持注入假 client 进行测试。
"""

from __future__ import annotations

import os
from typing import Any


def _build_summarize_prompt(max_len: int) -> str:
    """构造摘要任务的 system prompt。"""
    return (
        f"你是文本摘要专家。用不超过 {max_len} 个字的一句话，"
        "概括用户提供文本的核心内容。"
        "只输出摘要，不加任何前缀、解释或标点以外的额外内容。"
    )


def summarize(
    text: str,
    *,
    client: Any = None,
    model: str = "gpt-4o-mini",
    max_len: int = 40,
) -> str:
    """将长文本压缩为一句话描述。

    支持注入假 client（duck-typing），便于单元测试不产生真实 API 调用。
    未注入 client 时，从环境变量 OPENAI_API_KEY 读取 key 并初始化 openai。

    Args:
        text:    待摘要的原始文本。
        client:  可注入的 OpenAI 兼容 client。为 None 时尝试自动初始化 openai。
        model:   模型名称，默认 gpt-4o-mini。
        max_len: 摘要最大字数，默认 40 字。

    Returns:
        一句话摘要字符串。

    Raises:
        ConfigError: openai 未安装或 OPENAI_API_KEY 未配置（且未注入 client）。
        ValueError:  text 为空。
    """
    from fxharvest.core.errors import ConfigError  # 避免循环导入，在函数内导入

    if not text or not text.strip():
        raise ValueError("summarize：输入文本不能为空")

    # 确定最终使用的 client
    resolved_client = client
    if resolved_client is None:
        try:
            import openai  # noqa: PLC0415
        except ImportError as exc:
            raise ConfigError(
                "openai 库未安装。请执行：uv add 'fxharvest[llm]' 或 uv add openai"
            ) from exc

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ConfigError(
                "缺少 OpenAI API key。请设置环境变量 OPENAI_API_KEY，"
                "或通过 client 参数注入已初始化的 client。"
            )
        resolved_client = openai.OpenAI(api_key=api_key)

    # 调用 LLM
    response = resolved_client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": _build_summarize_prompt(max_len),
            },
            {
                "role": "user",
                "content": text,
            },
        ],
    )

    content = response.choices[0].message.content
    return (content or "").strip()


__all__ = ["summarize"]
