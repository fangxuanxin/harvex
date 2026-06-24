"""采集插件注册表：发现、加载、实例化采集方式插件。

发现来源（按优先级合并，后者覆盖前者同名 kind）：
1. 框架自带插件目录 ``harvex/acquire/assets/plugins/``（随包发布）。
2. 可选的项目级插件目录（如下游项目的 ``assets/plugins/``），供用户/AI 自行扩充。

加载策略：读 plugin.toml → import entry 模块 → 取其中的 Acquirer 子类。
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

from ..core.errors import ConfigError
from .base import Acquirer, AcquireContext
from .manifest import PluginManifest

# 框架自带插件目录
BUNDLED_PLUGINS_DIR = Path(__file__).parent / "assets" / "plugins"


class PluginRegistry:
    """采集插件注册表：kind → PluginManifest，并能按 kind 加载 Acquirer 子类。"""

    def __init__(self) -> None:
        self._manifests: dict[str, PluginManifest] = {}
        self._classes: dict[str, type[Acquirer]] = {}

    # ---- 发现 ----
    def discover(self, *extra_dirs: str | Path, include_bundled: bool = True) -> "PluginRegistry":
        """扫描插件目录，登记所有 plugin.toml。返回自身便于链式调用。"""
        dirs: list[Path] = []
        if include_bundled:
            dirs.append(BUNDLED_PLUGINS_DIR)
        dirs.extend(Path(d) for d in extra_dirs)
        for base in dirs:
            if not base.is_dir():
                continue
            for plugin_dir in sorted(p for p in base.iterdir() if p.is_dir()):
                if (plugin_dir / "plugin.toml").is_file():
                    manifest = PluginManifest.load(plugin_dir)
                    self._manifests[manifest.kind] = manifest
        return self

    # ---- 查询 ----
    def kinds(self) -> list[str]:
        return sorted(self._manifests)

    def manifest(self, kind: str) -> PluginManifest:
        if kind not in self._manifests:
            raise ConfigError(f"未知采集方式：{kind}（已发现：{', '.join(self.kinds()) or '无'}）")
        return self._manifests[kind]

    # ---- 加载 ----
    def load_class(self, kind: str) -> type[Acquirer]:
        """按 kind 加载并缓存 Acquirer 子类（不实例化）。"""
        if kind in self._classes:
            return self._classes[kind]
        manifest = self.manifest(kind)
        module = self._import_entry(manifest)
        acquirer_cls = self._find_acquirer(module, manifest)
        self._classes[kind] = acquirer_cls
        return acquirer_cls

    def create(self, kind: str, context: AcquireContext) -> Acquirer:
        """按 kind 实例化一个 Acquirer，并把该插件的 assets 目录注入 context。"""
        manifest = self.manifest(kind)
        if context.assets_dir is None and manifest.assets_dir.is_dir():
            context.assets_dir = manifest.assets_dir
        return self.load_class(kind)(context)

    # ---- 内部 ----
    @staticmethod
    def _import_entry(manifest: PluginManifest):
        entry = manifest.entry_path
        if not entry.is_file():
            raise ConfigError(f"插件 entry 不存在：{entry}")
        mod_name = f"harvex_plugin_{manifest.kind}"
        spec = importlib.util.spec_from_file_location(mod_name, entry)
        if not spec or not spec.loader:
            raise ConfigError(f"无法加载插件模块：{entry}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _find_acquirer(module, manifest: PluginManifest) -> type[Acquirer]:
        # 优先按清单指定的 class_name 取；否则取模块内第一个 Acquirer 子类
        if manifest.class_name:
            obj = getattr(module, manifest.class_name, None)
            if obj is None or not (inspect.isclass(obj) and issubclass(obj, Acquirer)):
                raise ConfigError(f"插件 {manifest.kind} 未找到 Acquirer 子类 {manifest.class_name}")
            return obj
        for obj in vars(module).values():
            if inspect.isclass(obj) and issubclass(obj, Acquirer) and obj is not Acquirer:
                return obj
        raise ConfigError(f"插件 {manifest.kind} 的 {manifest.entry} 内没有 Acquirer 子类")


def load_acquirer(kind: str, context: AcquireContext, *, plugin_dirs: list[str | Path] | None = None) -> Acquirer:
    """便捷函数：发现插件并按 kind 创建一个 Acquirer 实例。"""
    registry = PluginRegistry().discover(*(plugin_dirs or []))
    return registry.create(kind, context)


__all__ = ["PluginRegistry", "load_acquirer", "BUNDLED_PLUGINS_DIR"]
