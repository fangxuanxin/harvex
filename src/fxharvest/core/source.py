"""BaseSource：数据源插件契约（类契约 + 自动发现）。

新项目写一个数据源 = 写一个 BaseSource 子类，放进项目的 sources/ 目录：

    class IcbcSource(BaseSource):
        profile = SourceProfile(slug="icbc", name="工商银行", channel="bank")
        record_model = JobRecord

        def fetch(self):
            return self.ctx.http.get_json("https://...")

        def parse(self, raw):
            for item in raw["data"]:
                yield {"职位名称": item["title"], ...}

框架的 registry 会自动扫描 sources/ 发现所有 BaseSource 子类并注册。
源只负责「怎么抓、怎么解析成 dict」；校验/收口/写库/流水/健康全交给 pipeline。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from .record import HarvestRecord

if TYPE_CHECKING:  # 避免运行时循环依赖
    from .context import SourceContext


@dataclass(frozen=True)
class SourceProfile:
    """数据源的静态元信息（声明在 Source 子类上，也可被 config.toml 覆盖）。"""

    slug: str                       # 唯一标识（英文短名），用于注册/命令行/库内 source 列
    name: str                       # 人类可读名称
    enabled: bool = True            # 软开关：False 则不参与抓取轮次
    channel: str | None = None      # 分类/渠道（如 bank / tech）
    schedule: str | None = None     # 调度时间点提示（如 "10:00,17:00"），由 scheduling 层消费
    config: dict[str, Any] = field(default_factory=dict)  # 源特有配置（地区关键词、近 N 月等）


class BaseSource(ABC):
    """所有数据源的抽象基类。子类必须设置 profile 并实现 fetch/parse。"""

    profile: ClassVar[SourceProfile]                       # 子类必须覆盖
    record_model: ClassVar[type[HarvestRecord]] = HarvestRecord  # 本源产出的记录模型

    def __init__(self, context: "SourceContext") -> None:
        # ctx 注入 http_client / logger / clock / config / run_id，由 pipeline 构造
        self.ctx = context

    @property
    def slug(self) -> str:
        return self.profile.slug

    @abstractmethod
    def fetch(self) -> Any:
        """拉取原始数据（HTTP / 浏览器 / 文件等）。失败应抛 FetchError。"""

    @abstractmethod
    def parse(self, raw: Any) -> Iterable[Mapping[str, Any]]:
        """把原始数据解析成 raw dict 序列（一条记录一个 dict）。失败应抛 ParseError。"""

    def collect(self) -> list[HarvestRecord]:
        """便捷模板方法：fetch → parse → from_raw 校验收口，返回记录列表。

        pipeline 默认走这条；也可由 pipeline 自行拆分调用以做更细的流水登记。
        """
        raw = self.fetch()
        records: list[HarvestRecord] = []
        for item in self.parse(raw):
            records.append(self.record_model.from_raw(item, source_slug=self.slug))
        return records


__all__ = ["BaseSource", "SourceProfile"]
