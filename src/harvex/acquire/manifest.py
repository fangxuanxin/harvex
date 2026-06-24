"""插件清单（plugin.toml）解析。

每个采集插件目录下放一个 ``plugin.toml`` 描述自身元信息，registry 据此发现与加载。
清单字段刻意精简，方便将来 AI 服务新增插件时照抄填写。
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.errors import ConfigError


@dataclass(frozen=True)
class PluginManifest:
    """一个采集插件的清单。

    对应 plugin.toml::

        kind = "http"                 # 类型标识（唯一）
        name = "传统 HTTP 采集"
        version = "0.1.0"
        description = "用 httpx 直接请求，适合 API / 静态页"
        entry = "acquirer.py"         # Acquirer 子类所在文件（相对插件目录）
        class_name = "HttpAcquirer"   # Acquirer 子类名
        requires = []                 # 额外 pip 依赖（空=仅核心）
        assets = []                   # 自带脚本/模板文件（相对插件目录）
        platforms = ["any"]           # 适用平台：any / macos / linux ...
    """

    kind: str
    name: str
    directory: Path                                  # 插件所在目录（运行时填入）
    version: str = "0.1.0"
    description: str = ""
    entry: str = "acquirer.py"
    class_name: str = ""
    requires: list[str] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=lambda: ["any"])

    @property
    def entry_path(self) -> Path:
        return self.directory / self.entry

    @property
    def assets_dir(self) -> Path:
        return self.directory / "assets"

    @classmethod
    def load(cls, plugin_dir: str | Path) -> "PluginManifest":
        """从插件目录读取并校验 plugin.toml。"""
        plugin_dir = Path(plugin_dir)
        toml_path = plugin_dir / "plugin.toml"
        if not toml_path.is_file():
            raise ConfigError(f"插件缺少 plugin.toml：{plugin_dir}")
        try:
            data: dict[str, Any] = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as error:
            raise ConfigError(f"plugin.toml 解析失败（{toml_path}）：{error}") from error

        for required in ("kind", "name"):
            if not data.get(required):
                raise ConfigError(f"plugin.toml 缺少必填字段 '{required}'：{toml_path}")

        return cls(
            kind=data["kind"],
            name=data["name"],
            directory=plugin_dir,
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            entry=data.get("entry", "acquirer.py"),
            class_name=data.get("class_name", ""),
            requires=list(data.get("requires", [])),
            assets=list(data.get("assets", [])),
            platforms=list(data.get("platforms", ["any"])),
        )


__all__ = ["PluginManifest"]
