"""LLM 结构化输出 JSON Schema 定义与解析工具。

定义批量翻译 / 增强任务使用的 JSON Schema 常量，
以及对 LLM 返回结果的校验与解析辅助函数。
"""

from __future__ import annotations

from typing import Any


# ── 批量翻译 Schema ─────────────────────────────────────────────────────────
# 要求 LLM 返回形如 {"translations": ["译文1", "译文2", ...]} 的 JSON 对象。
# 可传入 openai client 的 response_format 参数（json_schema 模式）。
BATCH_TRANSLATION_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "batch_translation",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "translations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "按输入顺序排列的译文列表，与输入文本一一对应。",
                }
            },
            "required": ["translations"],
            "additionalProperties": False,
        },
    },
}

# ── 摘要 Schema ─────────────────────────────────────────────────────────────
# 要求 LLM 返回形如 {"summary": "一句话摘要"} 的 JSON 对象。
SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "text_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "不超过指定字数的一句话描述。",
                }
            },
            "required": ["summary"],
            "additionalProperties": False,
        },
    },
}


def parse_translations(data: dict[str, Any], expected_count: int) -> list[str]:
    """从 LLM 结构化返回中解析翻译列表。

    Args:
        data:           LLM 返回的已解析 dict（来自 json.loads 或 model.model_dump）。
        expected_count: 期望的译文数量，用于校验长度一致性。

    Returns:
        译文字符串列表。

    Raises:
        ValueError: 结构不符合预期或数量不匹配。
    """
    if not isinstance(data, dict):
        raise ValueError(f"期望 dict，实际收到 {type(data).__name__}")

    translations = data.get("translations")
    if not isinstance(translations, list):
        raise ValueError(f"'translations' 字段缺失或非列表：{data!r}")

    if len(translations) != expected_count:
        raise ValueError(
            f"译文数量不匹配：期望 {expected_count}，实际 {len(translations)}"
        )

    return [str(t) for t in translations]


def parse_summary(data: dict[str, Any]) -> str:
    """从 LLM 结构化返回中解析摘要字符串。

    Args:
        data: LLM 返回的已解析 dict。

    Returns:
        摘要字符串。

    Raises:
        ValueError: 结构不符合预期。
    """
    if not isinstance(data, dict):
        raise ValueError(f"期望 dict，实际收到 {type(data).__name__}")

    summary = data.get("summary")
    if not isinstance(summary, str):
        raise ValueError(f"'summary' 字段缺失或非字符串：{data!r}")

    return summary


__all__ = [
    "BATCH_TRANSLATION_SCHEMA",
    "SUMMARY_SCHEMA",
    "parse_translations",
    "parse_summary",
]
