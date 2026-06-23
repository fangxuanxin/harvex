"""HarvestRecord：框架的「字段收口」契约（皇冠明珠）。

设计意图（从招聘项目的 STANDARD_JOB_COLUMNS + normalize 纪律泛化而来）：

1. 每个项目用子类声明自己的「标准字段」（如 JobRecord 声明 职位名称/公司/地点 ...）。
2. 源（Source）解析出的 raw dict 在进入写库前，必须先过 ``from_raw`` 这道关：
   - 已声明字段 → 走 pydantic v2 校验（缺失/类型错当场抛 RecordValidationError）；
   - 未声明的稀有字段 → 自动「折叠」进 ``extra`` 容器，避免主表无限长列。
3. 入库时 ``extra`` 序列化为 JSON 字符串，业务主表只保留声明字段 + 一个 extra 列。

这样既守住「字段收口、不让主表变稀疏矩阵」的纪律，又不丢任何原始信息。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .errors import RecordValidationError


class HarvestRecord(BaseModel):
    """所有采集记录模型的基类。项目通过继承它声明标准字段。"""

    # extra="ignore"：未声明字段不会进入模型本身（由 from_raw 显式折叠进 extra），
    # 防止脏字段悄悄混入；populate_by_name 允许用字段名或别名填充。
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    # 折叠未声明字段的容器；入库时转成 JSON 字符串落到单独一列。
    extra: dict[str, Any] = Field(default_factory=dict)

    # 子类声明去重主键字段名（用于 upsert 唯一索引），如 ("source", "job_id")。
    # 为空时表示不做唯一去重（全部 append）。
    dedup_keys: ClassVar[tuple[str, ...]] = ()

    # 入库时 extra 列的列名，子类可覆盖（如招聘项目用「扩展信息」）。
    extra_column: ClassVar[str] = "extra"

    @classmethod
    def declared_fields(cls) -> set[str]:
        """本模型声明的标准字段名集合（不含 extra 容器本身）。"""
        return set(cls.model_fields) - {"extra"}

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any], *, source_slug: str | None = None) -> "HarvestRecord":
        """把源解析出的 raw dict 收口成一条校验过的记录。

        已声明字段交给 pydantic 校验；未声明字段折叠进 extra。
        校验失败抛 RecordValidationError（包装 pydantic.ValidationError）。
        """
        declared = cls.declared_fields()
        known: dict[str, Any] = {}
        folded: dict[str, Any] = dict(raw.get("extra") or {})  # 已有 extra 先并入
        for key, value in raw.items():
            if key == "extra":
                continue
            if key in declared:
                known[key] = value
            else:
                folded[key] = value
        known["extra"] = folded
        try:
            return cls(**known)
        except ValidationError as error:
            raise RecordValidationError(
                f"记录校验失败（source={source_slug}）：{error}",
                source_slug=source_slug,
                cause=error,
            ) from error

    def to_row(self) -> dict[str, Any]:
        """转成可直接写入 SQLite 的一行：extra 序列化为 JSON 字符串。"""
        data = self.model_dump()
        folded = data.pop("extra", {})
        data[self.extra_column] = json.dumps(folded, ensure_ascii=False, sort_keys=True)
        return data

    def dedup_signature(self) -> tuple:
        """返回用于去重的主键值元组；dedup_keys 为空时返回空元组。"""
        return tuple(getattr(self, key) for key in self.dedup_keys)


__all__ = ["HarvestRecord"]
