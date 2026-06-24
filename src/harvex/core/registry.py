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
            module = importlib.import_module(f"{package_name}.{mod_info.name}")
            self._register_from_module(module)

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
                self._register_from_module(module)

    def _register_from_module(self, module) -> None:
        """只注册「定义在该模块内」的 Source 子类。

        刻意不走全局 BaseSource.__subclasses__() 扫描——那会把其它模块（甚至
        宿主应用、测试里历史导入）的源也卷进来，造成 slug 误冲突。按模块归属
        收集才是确定性的：一个模块导入一次，只贡献它自己定义的源。
        """
        for obj in vars(module).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseSource)
                and obj is not BaseSource
                and not inspect.isabstract(obj)
                and getattr(obj, "__module__", None) == module.__name__
                and getattr(obj, "profile", None) is not None
            ):
                self.register(obj)

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


__all__ = ["SourceRegistry"]
