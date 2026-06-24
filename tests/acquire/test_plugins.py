"""acquire 层测试：插件发现、清单解析、Acquirer 加载（骨架阶段）。

当前自带插件为铺垫骨架：acquire() 故意抛 NotImplementedError，
这里验证「发现/清单/加载/实例化」这层管线本身是通的。
"""

from __future__ import annotations

import pytest

from harvex.acquire import (
    Acquirer,
    AcquireContext,
    PluginRegistry,
    load_acquirer,
)
from harvex.acquire.registry import BUNDLED_PLUGINS_DIR


def test_bundled_plugins_discovered():
    reg = PluginRegistry().discover()
    kinds = reg.kinds()
    # 三种自带采集方式都应被发现
    assert {"http", "playwright_headless", "applescript_browser"} <= set(kinds)


def test_manifest_fields():
    reg = PluginRegistry().discover()
    m = reg.manifest("playwright_headless")
    assert m.name and m.class_name == "PlaywrightHeadlessAcquirer"
    assert "playwright>=1.42" in m.requires
    assert m.assets_dir.is_dir()           # 自带 inject.js 所在目录


def test_load_class_and_instantiate():
    reg = PluginRegistry().discover()
    cls = reg.load_class("http")
    assert issubclass(cls, Acquirer) and cls.kind == "http"
    acq = reg.create("http", AcquireContext(url="https://example.com"))
    assert isinstance(acq, Acquirer)
    # 骨架阶段：acquire 抛 NotImplementedError（铺垫，待 AI 补全）
    with pytest.raises(NotImplementedError):
        acq.acquire()


def test_create_injects_assets_dir():
    reg = PluginRegistry().discover()
    ctx = AcquireContext(url="https://example.com")
    reg.create("applescript_browser", ctx)
    # 该插件 assets/ 应被注入 context，便于实现期读取 .applescript / inject.js
    assert ctx.assets_dir is not None and ctx.assets_dir.is_dir()


def test_unknown_kind_raises():
    reg = PluginRegistry().discover()
    with pytest.raises(Exception):
        reg.manifest("nope")


def test_bundled_dir_exists():
    assert BUNDLED_PLUGINS_DIR.is_dir()
    assert load_acquirer  # 便捷函数已导出
