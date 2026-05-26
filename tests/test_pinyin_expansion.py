from core.data_models import Folder, ShortcutItem
from core.fuzzy_search import search_shortcuts
from core.pinyin_search import pinyin_variants


def test_expanded_pinyin_dictionary_matches_common_apps():
    # "微信" -> wx, weixin
    variants_weixin = pinyin_variants("微信")
    assert "weixin" in variants_weixin
    assert "wx" in variants_weixin

    # "支付宝" -> zfb, zhifubao
    variants_zfb = pinyin_variants("支付宝")
    assert "zhifubao" in variants_zfb
    assert "zfb" in variants_zfb

    # "控制面板" -> kzmb, kongzhimianban
    variants_kzmb = pinyin_variants("控制面板")
    assert "kongzhimianban" in variants_kzmb
    assert "kzmb" in variants_kzmb


def test_fuzzy_search_supports_expanded_pinyin():
    page = Folder(
        items=[
            ShortcutItem(name="微信", alias="WeChat"),
            ShortcutItem(name="支付宝", alias="Alipay"),
            ShortcutItem(name="控制面板"),
        ]
    )

    # Search initials
    assert search_shortcuts([page], "wx")[0].shortcut.name == "微信"
    assert search_shortcuts([page], "zfb")[0].shortcut.name == "支付宝"
    assert search_shortcuts([page], "kzmb")[0].shortcut.name == "控制面板"

    # Search full pinyin
    assert search_shortcuts([page], "weixin")[0].shortcut.name == "微信"
    assert search_shortcuts([page], "zhifubao")[0].shortcut.name == "支付宝"
    assert search_shortcuts([page], "kongzhimianban")[0].shortcut.name == "控制面板"


def test_dynamic_pinyin_discovery_mocked(monkeypatch):
    class MockPyPinyin:
        @staticmethod
        def pinyin(text, style=None):
            if style == 1:  # FIRST_LETTER
                return [["w"], ["x"]]
            return [["wei"], ["xin"]]

    class MockStyle:
        FIRST_LETTER = 1
        NORMAL = 2

    MockPyPinyin.Style = MockStyle

    import sys

    sys.modules["pypinyin"] = MockPyPinyin

    import core.pinyin_search as pinyin_search

    monkeypatch.setattr(pinyin_search, "_HAS_PYPINYIN", None)

    try:
        variants = pinyin_search.pinyin_variants("任意汉字")
        assert "weixin" in variants
        assert "wx" in variants
    finally:
        sys.modules.pop("pypinyin", None)
