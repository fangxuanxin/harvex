"""框架统一异常体系。

所有源（Source）在抓取/解析过程中抛出的异常，都应收敛成这里的类型，
以便 pipeline 统一捕获、登记流水、触发告警，并保证「一个源挂掉不炸整轮」。
"""

from __future__ import annotations


class FxHarvestError(Exception):
    """框架所有异常的基类。"""


class ConfigError(FxHarvestError):
    """配置缺失或非法（如必填项未填、schedule 表达式错误）。"""


class FetchError(FxHarvestError):
    """抓取阶段失败（网络、超时、对端 5xx、鉴权失败等）。"""


class ParseError(FxHarvestError):
    """解析阶段失败（页面结构变化、JSON 字段缺失等）。"""


class RecordValidationError(FxHarvestError):
    """记录校验失败（pydantic 校验未通过，字段缺失/类型错）。

    包装底层的 pydantic.ValidationError，附带源 slug 便于定位。
    """

    def __init__(self, message: str, *, source_slug: str | None = None, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.source_slug = source_slug
        self.__cause__ = cause


class SinkError(FxHarvestError):
    """写库/落地阶段失败。"""


__all__ = [
    "FxHarvestError",
    "ConfigError",
    "FetchError",
    "ParseError",
    "RecordValidationError",
    "SinkError",
]
