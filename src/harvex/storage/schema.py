"""schema.py：从 HarvestRecord 子类推导建表 DDL 与唯一索引 SQL。

设计原则：
- 列类型统一 TEXT（SQLite 弱类型，简单稳妥，避免类型转换摩擦）。
- id 用 INTEGER PRIMARY KEY AUTOINCREMENT，自增主键。
- created_at / updated_at 为框架强制元字段，由 upsert 逻辑维护。
- extra_column 名称由 record_model.extra_column 决定，保持子类可覆盖。
- dedup_keys 非空时生成唯一索引 SQL，空时不生成（全量 append 场景）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.record import HarvestRecord


@dataclass
class SchemaSpec:
    """描述一张业务表的结构规格。

    Attributes:
        table:      表名（由调用方传入，通常与 Sink 的 table 参数对应）。
        columns:    全量列名列表，包含声明字段、extra 列、id、created_at、updated_at。
                    顺序固定：[id, *declared_fields, extra_column, created_at, updated_at]。
        dedup_keys: 去重主键字段名元组，对应 HarvestRecord.dedup_keys。
    """

    table: str
    columns: list[str] = field(default_factory=list)
    dedup_keys: tuple[str, ...] = field(default_factory=tuple)


def build_schema(record_model: type[HarvestRecord], table: str) -> SchemaSpec:
    """由 record_model 推导 SchemaSpec。

    列顺序：id → 各声明字段（排序确保稳定）→ extra_column → created_at → updated_at。
    不包含 pydantic 的内部字段（extra 容器由 extra_column 替代）。
    """
    # declared_fields() 已排除 "extra" 容器本身
    declared = sorted(record_model.declared_fields())
    extra_col = record_model.extra_column

    columns: list[str] = ["id", *declared, extra_col, "created_at", "updated_at"]

    return SchemaSpec(
        table=table,
        columns=columns,
        dedup_keys=record_model.dedup_keys,
    )


def create_table_sql(spec: SchemaSpec) -> str:
    """生成 CREATE TABLE IF NOT EXISTS DDL。

    - id：INTEGER PRIMARY KEY AUTOINCREMENT
    - created_at / updated_at：TEXT，框架元字段
    - 其余列：TEXT
    """
    col_defs: list[str] = []
    for col in spec.columns:
        if col == "id":
            col_defs.append('"id" INTEGER PRIMARY KEY AUTOINCREMENT')
        elif col in ("created_at", "updated_at"):
            col_defs.append(f'"{col}" TEXT')
        else:
            col_defs.append(f'"{col}" TEXT')

    col_block = ",\n    ".join(col_defs)
    return f'CREATE TABLE IF NOT EXISTS "{spec.table}" (\n    {col_block}\n);'


def unique_index_sql(spec: SchemaSpec) -> str | None:
    """生成唯一索引 DDL；dedup_keys 为空时返回 None（无需唯一约束）。

    索引名固定为 uq_<table>_dedup，便于 ensure_table 时幂等检测。
    """
    if not spec.dedup_keys:
        return None

    key_cols = ", ".join(f'"{k}"' for k in spec.dedup_keys)
    index_name = f"uq_{spec.table}_dedup"
    return (
        f'CREATE UNIQUE INDEX IF NOT EXISTS "{index_name}" '
        f'ON "{spec.table}" ({key_cols});'
    )


__all__ = ["SchemaSpec", "build_schema", "create_table_sql", "unique_index_sql"]
