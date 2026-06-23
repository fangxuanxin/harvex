"""本项目的标准字段定义。

继承 HarvestRecord 声明「标准列」；源解析出的未声明字段会自动折叠进 extra_column。
按需把字段改成你项目的业务字段（这里以招聘场景为例）。
"""

from __future__ import annotations

from fxharvest import HarvestRecord


class JobRecord(HarvestRecord):
    # —— 标准字段（会成为业务表的列）——
    职位名称: str
    公司: str | None = None
    地点: str | None = None
    职位链接: str | None = None
    职位描述: str | None = None

    # 去重主键：同名同公司视为同一岗位，重复抓取走 upsert 更新
    dedup_keys = ("职位名称", "公司")
    # 未声明字段折叠进这一列（入库为 JSON 字符串）
    extra_column = "扩展信息"
