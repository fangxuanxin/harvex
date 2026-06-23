"""东亚宽字符感知的文本宽度计算与对齐工具。

终端中 CJK（中文/日文/韩文）字符实际占用 2 个字符宽度，
若只用 len() 计算对齐会导致表格错位。
本模块用 unicodedata.east_asian_width 解决这个问题。

只用标准库，无第三方依赖。
"""

from __future__ import annotations

import unicodedata


def display_width(s: str) -> int:
    """计算字符串在终端中的显示宽度（东亚宽字符算 2）。

    Args:
        s: 任意字符串。

    Returns:
        该字符串在等宽字体终端中占用的列数。

    Examples:
        >>> display_width("ABC")
        3
        >>> display_width("中文")
        4
        >>> display_width("职位ABC")
        7
    """
    width = 0
    for ch in s:
        eaw = unicodedata.east_asian_width(ch)
        # W（Wide）和 F（Fullwidth）为宽字符，占 2 列
        if eaw in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def ljust_display(s: str, width: int, fill: str = " ") -> str:
    """按显示宽度左对齐，不足位数用 fill 字符补齐。

    Args:
        s:     要对齐的字符串。
        width: 目标显示宽度（列数）。
        fill:  填充字符，默认空格（必须是显示宽度为 1 的字符）。

    Returns:
        补齐后的字符串，display_width(result) == max(width, display_width(s))。

    Examples:
        >>> ljust_display("中文", 8)
        '中文    '
        >>> display_width(ljust_display("中文", 8))
        8
    """
    current = display_width(s)
    if current >= width:
        return s
    # 计算需要补多少个 fill 字符
    padding = width - current
    return s + fill * padding


def truncate_display(s: str, width: int) -> str:
    """按显示宽度截断字符串，避免超出列宽。

    若字符串显示宽度超过 width，截断并在末尾加 "…"（占 1 列）；
    否则原样返回。宽字符截断时确保不会"切半"，若最后一个宽字符
    恰好会超出，用空格补位而非截断到不完整。

    Args:
        s:     要截断的字符串。
        width: 最大显示宽度（列数）。

    Returns:
        截断后的字符串，display_width(result) <= width。

    Examples:
        >>> truncate_display("后端工程师招聘中", 10)
        '后端工程…'
        >>> truncate_display("ABC", 10)
        'ABC'
    """
    if display_width(s) <= width:
        return s

    # 留 1 列给省略号
    budget = width - 1
    result_chars: list[str] = []
    accumulated = 0

    for ch in s:
        ch_w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if accumulated + ch_w > budget:
            break
        result_chars.append(ch)
        accumulated += ch_w

    # 若还有剩余空间（宽字符刚好不够但空间有 1 列），用空格补位
    # 确保 display_width(result) + 1 (省略号) == width
    if accumulated < budget:
        result_chars.append(" " * (budget - accumulated))

    return "".join(result_chars) + "…"


__all__ = ["display_width", "ljust_display", "truncate_display"]
