"""SourceRegistry：扫描项目 sources/ 目录自动发现并注册 Source 子类。

新项目把每个数据源写成一个 BaseSource 子类放进 sources/ 目录，
registry 负责 import 这些模块、收集所有定义了 profile 的子类、按 slug 建索引。
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import pkgutil
import sys
from pathlib import Path

from .errors import ConfigError
from .source import BaseSource


class SourceRegistry:
    """数据源注册表：slug → BaseSource 子类。"""

    def __init__(self) -> None:
        self._sources: dict[str, type[BaseSource]] = {}

    def register(self, source_cls: type[BaseSource]) -> None:
        """注册一个 Source 子类（必须已设置 profile）。"""
        profile = getattr(source_cls, "profile", None)
        if profile is None:
            raise ConfigError(f"{source_cls.__name__} 未定义 profile，无法注册")
        if profile.slug in self._sources and self._sources[profile.slug] is not source_cls:
            raise ConfigError(f"slug 冲突：{profile.slug} 已被 {self._sources[profile.slug].__name__} 占用")
        self._sources[profile.slug] = source_cls

    def discover_package(self, package_name: str) -> None:
        """从一个已可导入的包名（如项目的 'sources'）发现源。"""
        package = importlib.import_module(package_name)
        for mod_info in pkgutil.iter_modules(package.__path__):
            importlib.import_module(f"{package_name}.{mod_info.name}")
        self._collect_subclasses()

    def discover_dir(self, sources_dir: str | Path) -> None:
        """从文件系统目录发现源：import 目录下所有非下划线开头的 .py 模块。"""
        sources_dir = Path(sources_dir).resolve()
        if not sources_dir.is_dir():
            raise ConfigError(f"sources 目录不存在：{sources_dir}")
        # 把父目录加入 sys.path，使目录可作为包/模块被导入
        parent = str(sources_dir.parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        for py_file in sorted(sources_dir.glob("*.py")):
            if py_file.stem.startswith("_"):
                continue
            mod_name = f"{sources_dir.name}.{py_file.stem}"
            spec = importlib.util.spec_from_file_location(mod_name, py_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = module
                spec.loader.exec_module(module)
        self._collect_subclasses()

    def _collect_subclasses(self) -> None:
        """递归收集所有已加载的、定义了 profile 的 BaseSource 子类。"""
        for cls in _all_subclasses(BaseSource):
            if inspect.isabstract(cls):
                continue
            if getattr(cls, "profile", None) is None:
                continue
            self.register(cls)

    def get(self, slug: str) -> type[BaseSource]:
        if slug not in self._sources:
            raise ConfigError(f"未知数据源 slug：{slug}（已注册：{', '.join(self.slugs()) or '无'}）")
        return self._sources[slug]

    def all(self) -> list[type[BaseSource]]:
        """全部已注册源（按 slug 排序）。"""
        return [self._sources[s] for s in self.slugs()]

    def enabled(self) -> list[type[BaseSource]]:
        """仅 profile.enabled 为真的源。"""
        return [c for c in self.all() if c.profile.enabled]

    def slugs(self) -> list[str]:
        return sorted(self._sources)


def _all_subclasses(base: type) -> set[type]:
    """递归取一个类的所有子类。"""
    result: set[type] = set()
    for sub in base.__subclasses__():
        result.add(sub)
        result |= _all_subclasses(sub)
    return result


__all__ = ["SourceRegistry"]
