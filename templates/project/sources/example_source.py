"""示例数据源：复制这个文件，改成你真实的源即可。

一个源 = 一个 BaseSource 子类，只需写两件事：
  - fetch()：怎么把原始数据拉回来（HTTP/浏览器/文件）
  - parse(raw)：怎么把原始数据解析成一条条 dict

校验、字段收口、写库去重、流水、健康检查、并发、告警都由框架负责。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from harvex import BaseSource, SourceProfile

from fields import JobRecord  # 项目根目录的 fields.py（运行时 sources 的父目录在 sys.path 上）


class ExampleSource(BaseSource):
    # profile 声明源的静态元信息；slug 必须唯一
    profile = SourceProfile(slug="example", name="示例源", channel="demo")
    record_model = JobRecord

    def fetch(self) -> Any:
        # 真实场景这样拉数据（框架已注入带超时/重试的 http 客户端）：
        #   return self.ctx.http.get_json("https://example.com/api/jobs")
        # 这里返回静态演示数据，便于 `harvex run` 开箱即跑：
        return [
            {"职位名称": "后端工程师", "公司": "示例公司", "地点": "上海",
             "职位链接": "https://example.com/jobs/1", "薪资": "25k-40k"},
            {"职位名称": "前端工程师", "公司": "示例公司", "地点": "远程",
             "职位链接": "https://example.com/jobs/2", "学历": "本科"},
        ]

    def parse(self, raw: Any) -> Iterable[Mapping[str, Any]]:
        # 把 raw 逐条 yield 成 dict；未声明字段（薪资/学历）会自动折叠进「扩展信息」
        for item in raw:
            yield dict(item)
