"""core 测试：SourceRegistry 自动发现、注册、冲突、启用过滤。"""

from __future__ import annotations

import textwrap

import pytest

from harvex.core.errors import ConfigError
from harvex.core.registry import SourceRegistry

_SRC_A = '''\
from harvex import BaseSource, SourceProfile, HarvestRecord
class R(HarvestRecord):
    标题: str
class ASource(BaseSource):
    profile = SourceProfile(slug="a", name="源A")
    record_model = R
    def fetch(self): return []
    def parse(self, raw): return []
'''

_SRC_B = '''\
from harvex import BaseSource, SourceProfile, HarvestRecord
class R(HarvestRecord):
    标题: str
class BSource(BaseSource):
    profile = SourceProfile(slug="b", name="源B", enabled=False)
    record_model = R
    def fetch(self): return []
    def parse(self, raw): return []
'''


def _make_sources_dir(tmp_path, files: dict[str, str]):
    d = tmp_path / "sources_pkg"
    d.mkdir()
    (d / "__init__.py").write_text("", encoding="utf-8")
    for name, body in files.items():
        (d / name).write_text(textwrap.dedent(body), encoding="utf-8")
    return d


def test_discover_dir_finds_sources(tmp_path):
    d = _make_sources_dir(tmp_path, {"a.py": _SRC_A, "b.py": _SRC_B})
    reg = SourceRegistry()
    reg.discover_dir(d)
    assert set(reg.slugs()) >= {"a", "b"}
    assert reg.get("a").profile.name == "源A"


def test_enabled_filter(tmp_path):
    d = _make_sources_dir(tmp_path, {"a.py": _SRC_A, "b.py": _SRC_B})
    reg = SourceRegistry()
    reg.discover_dir(d)
    enabled_slugs = {c.profile.slug for c in reg.enabled()}
    assert "a" in enabled_slugs and "b" not in enabled_slugs   # b enabled=False


def test_unknown_slug_raises(tmp_path):
    reg = SourceRegistry()
    with pytest.raises(ConfigError):
        reg.get("nope")
