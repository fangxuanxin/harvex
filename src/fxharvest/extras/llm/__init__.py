"""fxharvest extras/llm：LLM 翻译与文本增强扩展。

可选依赖（extras）：安装时执行 uv add 'fxharvest[llm]' 或 uv add openai。
未安装 openai 库时，导入本包不会报错；仅在实际调用时抛出 ConfigError。

公开 API::

    from fxharvest.extras.llm import Translator, TranslationCache, summarize
"""

from fxharvest.extras.llm.cache import TranslationCache
from fxharvest.extras.llm.enrich import summarize
from fxharvest.extras.llm.translator import Translator

__all__ = [
    "TranslationCache",
    "Translator",
    "summarize",
]
