"""extras 测试：tui 显示宽度、llm 缓存、browser parse 路径（不触真实浏览器/网络）。"""

from __future__ import annotations

from fxharvest.extras.tui.textwidth import display_width, ljust_display


def test_display_width_east_asian():
    # 中文 2 宽，ASCII 1 宽
    assert display_width("职位ABC") == 7
    assert display_width("") == 0


def test_ljust_display_pads_to_width():
    out = ljust_display("职位", 10)
    assert display_width(out) == 10


def test_llm_cache_hit(tmp_path):
    from fxharvest.extras.llm.cache import TranslationCache
    from fxharvest.extras.llm.translator import Translator

    class _Resp:
        def __init__(self, t):
            self.choices = [type("C", (), {"message": type("M", (), {"content": t})})]

    class _Client:
        def __init__(self):
            self.n = 0
            self.chat = type("X", (), {"completions": self})()

        def create(self, **kw):
            self.n += 1
            return _Resp("译文")

    fake = _Client()
    cache = TranslationCache(str(tmp_path / "cache.db"))
    tr = Translator(client=fake, cache=cache)
    assert tr.translate("hello") == "译文" and fake.n == 1
    assert tr.translate("hello") == "译文" and fake.n == 1   # 命中缓存，不再调用
    assert tr.translate("") == ""                            # 空串短路


def test_browser_parse_without_playwright():
    """parse 路径不依赖 playwright，可独立验证。"""
    import re

    from fxharvest import HarvestRecord, SourceProfile
    from fxharvest.extras.browser.browser_source import BrowserSource

    class _R(HarvestRecord):
        职位名称: str

    class Demo(BrowserSource):
        profile = SourceProfile(slug="demo", name="演示")
        record_model = _R
        start_url = "https://example.com"

        def parse(self, html):
            for m in re.findall(r"<h2>(.*?)</h2>", html):
                yield {"职位名称": m}

    items = list(Demo.parse(Demo.__new__(Demo), "<h2>后端</h2><h2>前端</h2>"))
    assert [i["职位名称"] for i in items] == ["后端", "前端"]
