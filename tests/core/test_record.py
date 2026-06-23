"""测试 HarvestRecord 的核心字段收口行为。

覆盖点：
1. from_raw 正常路径：声明字段通过校验，未声明字段折叠进 extra
2. extra 中已有数据在 from_raw 后被合并进 extra 容器
3. 缺少必填字段时抛 RecordValidationError
4. to_row 将 extra 序列化为 JSON 字符串，extra_column 名称正确
5. dedup_signature 按 dedup_keys 顺序返回元组
6. dedup_keys 为空时 dedup_signature 返回空元组
"""
from __future__ import annotations

import json

import pytest
from pydantic import Field

from fxharvest.core.record import HarvestRecord
from fxharvest.core.errors import RecordValidationError


# ── 辅助子类 ────────────────────────────────────────────────

class JobRecord(HarvestRecord):
    """最小化招聘记录，用于本测试文件。"""
    职位名称: str
    公司: str
    地点: str = ""

    dedup_keys = ("职位名称", "公司")
    extra_column = "扩展信息"


class NoDedup(HarvestRecord):
    """没有 dedup_keys 的极简记录，用于测试全量追加场景。"""
    title: str


# ── 测试组：from_raw ──────────────────────────────────────────

class TestFromRaw:
    """from_raw 的各种输入场景。"""

    def test_声明字段通过校验(self):
        """声明字段的值被正确填充到对应属性。"""
        raw = {"职位名称": "后端工程师", "公司": "示例公司", "地点": "上海"}
        record = JobRecord.from_raw(raw)
        assert record.职位名称 == "后端工程师"
        assert record.公司 == "示例公司"
        assert record.地点 == "上海"

    def test_未声明字段折叠进extra(self):
        """raw 中没有声明的字段应该折叠进 extra 容器，不污染主表。"""
        raw = {
            "职位名称": "前端工程师",
            "公司": "ABC科技",
            "薪资": "20k-30k",           # 未声明字段
            "福利": "五险一金",           # 未声明字段
        }
        record = JobRecord.from_raw(raw)
        assert record.extra["薪资"] == "20k-30k"
        assert record.extra["福利"] == "五险一金"
        # 主模型上没有这两个属性
        assert not hasattr(record, "薪资")
        assert not hasattr(record, "福利")

    def test_原始extra字段被合并(self):
        """raw 中原有的 extra 字典内容应与新折叠字段合并。"""
        raw = {
            "职位名称": "数据工程师",
            "公司": "大数据公司",
            "extra": {"origin": "boss"},   # 已有 extra
            "薪资": "25k",                 # 新折叠字段
        }
        record = JobRecord.from_raw(raw)
        assert record.extra["origin"] == "boss"
        assert record.extra["薪资"] == "25k"

    def test_缺少必填字段抛RecordValidationError(self):
        """缺少 required 字段（职位名称）时，from_raw 应抛 RecordValidationError。"""
        raw = {"公司": "只有公司没职位"}  # 缺少必填的「职位名称」
        with pytest.raises(RecordValidationError) as exc_info:
            JobRecord.from_raw(raw, source_slug="test-source")
        # 错误信息中应包含 source_slug
        assert exc_info.value.source_slug == "test-source"

    def test_空raw也抛RecordValidationError(self):
        """完全空的 raw dict 缺少所有必填字段，应抛 RecordValidationError。"""
        with pytest.raises(RecordValidationError):
            JobRecord.from_raw({})

    def test_字段默认值在缺失时生效(self):
        """有默认值的字段（地点=""）在 raw 中缺失时使用默认值。"""
        raw = {"职位名称": "运营", "公司": "某公司"}
        record = JobRecord.from_raw(raw)
        assert record.地点 == ""

    def test_source_slug参数记录在异常中(self):
        """from_raw 的 source_slug 参数在校验失败时应附着到异常上。"""
        with pytest.raises(RecordValidationError) as exc_info:
            JobRecord.from_raw({"公司": "仅公司"}, source_slug="icbc")
        assert exc_info.value.source_slug == "icbc"


# ── 测试组：to_row ────────────────────────────────────────────

class TestToRow:
    """to_row 的序列化行为。"""

    def test_extra列名由extra_column决定(self):
        """to_row 返回的字典中，extra 对应的键名应等于 extra_column（'扩展信息'）。"""
        raw = {"职位名称": "产品", "公司": "某科技", "薪资": "15k"}
        record = JobRecord.from_raw(raw)
        row = record.to_row()
        assert "扩展信息" in row
        assert "extra" not in row  # 原始 extra 容器键不应出现

    def test_extra被序列化为JSON字符串(self):
        """to_row 中 extra 列应是 JSON 字符串，可反序列化还原。"""
        raw = {"职位名称": "测试", "公司": "QA公司", "薪资": "18k", "城市": "深圳"}
        record = JobRecord.from_raw(raw)
        row = record.to_row()
        extra_data = json.loads(row["扩展信息"])
        assert extra_data["薪资"] == "18k"
        assert extra_data["城市"] == "深圳"

    def test_空extra序列化为空JSON对象(self):
        """没有额外字段时，extra 列应序列化为空 JSON 对象字符串。"""
        raw = {"职位名称": "HR", "公司": "人力公司"}
        record = JobRecord.from_raw(raw)
        row = record.to_row()
        assert row["扩展信息"] == "{}"

    def test_声明字段出现在row中(self):
        """to_row 返回的字典包含所有声明字段的值。"""
        raw = {"职位名称": "运维", "公司": "云公司", "地点": "北京"}
        record = JobRecord.from_raw(raw)
        row = record.to_row()
        assert row["职位名称"] == "运维"
        assert row["公司"] == "云公司"
        assert row["地点"] == "北京"


# ── 测试组：dedup_signature ───────────────────────────────────

class TestDedupSignature:
    """dedup_signature 的返回值验证。"""

    def test_按dedup_keys顺序返回元组(self):
        """dedup_signature 应按照 dedup_keys 的声明顺序返回字段值元组。"""
        record = JobRecord.from_raw({"职位名称": "算法工程师", "公司": "AI公司"})
        sig = record.dedup_signature()
        assert sig == ("算法工程师", "AI公司")

    def test_dedup_keys为空时返回空元组(self):
        """没有 dedup_keys 的模型，dedup_signature 应返回空元组。"""
        record = NoDedup.from_raw({"title": "hello"})
        assert record.dedup_signature() == ()

    def test_不同记录相同键产生相同签名(self):
        """两条 raw 中 dedup_keys 字段值相同的记录，签名应相等。"""
        r1 = JobRecord.from_raw({"职位名称": "PM", "公司": "X公司", "地点": "上海"})
        r2 = JobRecord.from_raw({"职位名称": "PM", "公司": "X公司", "地点": "北京"})
        assert r1.dedup_signature() == r2.dedup_signature()

    def test_不同键产生不同签名(self):
        """dedup_keys 字段值不同的记录，签名应不相等。"""
        r1 = JobRecord.from_raw({"职位名称": "前端", "公司": "A公司"})
        r2 = JobRecord.from_raw({"职位名称": "前端", "公司": "B公司"})
        assert r1.dedup_signature() != r2.dedup_signature()


# ── 测试组：declared_fields ───────────────────────────────────

class TestDeclaredFields:
    """declared_fields 类方法的行为。"""

    def test_声明字段集合不含extra(self):
        """declared_fields 应返回模型声明的业务字段，不含 extra 容器本身。"""
        fields = JobRecord.declared_fields()
        assert "职位名称" in fields
        assert "公司" in fields
        assert "地点" in fields
        assert "extra" not in fields
