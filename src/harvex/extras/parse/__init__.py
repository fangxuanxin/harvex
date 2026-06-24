"""harvex 解析扩展（[parse]）：基于 parsel 的 CSS/XPath 选择器小工具。

让 Source.parse() 写起来更顺。parsel 为可选依赖，惰性导入；未装时给安装指引。

    from harvex.extras.parse import selector

    def parse(self, html):
        sel = selector(html)
        for node in sel.css(".item"):
            yield {
                "title": node.css("h2::text").get(),
                "url": node.css("a::attr(href)").get(),
            }
"""

from __future__ import annotations

from typing import Any

from harvex.core.errors import ConfigError


def _require_parsel():
    try:
        import parsel  # noqa: PLC0415
    except ImportError as exc:
        raise ConfigError(
            "parsel 未安装。请执行：uv add 'harvex[parse]' 或 uv add parsel"
        ) from exc
    return parsel


def selector(text: str) -> Any:
    """用 HTML/XML 文本构造一个 parsel.Selector（支持 .css() / .xpath()）。"""
    parsel = _require_parsel()
    return parsel.Selector(text=text)


def css_all(text: str, query: str) -> list[str]:
    """便捷：按 CSS 选择器取所有匹配的文本/属性值列表。

    query 可带 parsel 的 ``::text`` / ``::attr(href)`` 伪元素。
    """
    return selector(text).css(query).getall()


def css_first(text: str, query: str, default: str | None = None) -> str | None:
    """便捷：按 CSS 选择器取首个匹配值，无则返回 default。"""
    return selector(text).css(query).get() or default


__all__ = ["selector", "css_all", "css_first"]
