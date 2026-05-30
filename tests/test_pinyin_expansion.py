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


# ── Extended pinyin_variants tests ────────────────────────────────────────────


def test_pinyin_empty_string():
    """Empty string returns empty list."""
    assert pinyin_variants("") == []


def test_pinyin_english_only_returns_empty():
    """English-only text (no CJK) returns empty list."""
    assert pinyin_variants("Notepad") == []
    assert pinyin_variants("Chrome") == []
    assert pinyin_variants("hello world") == []


def test_pinyin_numbers_only_returns_empty():
    """Numbers-only text returns empty list (no CJK character)."""
    assert pinyin_variants("12345") == []
    assert pinyin_variants("0") == []


def test_pinyin_single_chinese_character():
    """Single Chinese character returns full pinyin only (no separate initials)."""
    variants = pinyin_variants("微")
    assert "wei" in variants
    # initials = "w", full = "wei" -> different, so both present
    assert "w" in variants


def test_pinyin_single_character_no_distinct_initials():
    """Single character where pinyin is one letter produces no separate initials entry."""
    # "阿" -> pinyin "a", initial "a" -> identical, only one variant
    variants = pinyin_variants("阿")
    assert "a" in variants
    assert len(variants) == 1


def test_pinyin_mixed_chinese_english():
    """Mixed CJK + ASCII text includes ASCII parts in both variants."""
    variants = pinyin_variants("微信PC")
    assert "weixinpc" in variants
    assert "wxpc" in variants


def test_pinyin_mixed_chinese_numbers():
    """Mixed CJK + digits includes digits in both variants."""
    variants = pinyin_variants("微信3")
    assert "weixin3" in variants
    assert "wx3" in variants


# ── Common app names ─────────────────────────────────────────────────────────


def test_pinyin_weixin():
    v = pinyin_variants("微信")
    assert "weixin" in v
    assert "wx" in v


def test_pinyin_zhifubao():
    v = pinyin_variants("支付宝")
    assert "zhifubao" in v
    assert "zfb" in v


def test_pinyin_taobao():
    v = pinyin_variants("淘宝")
    assert "taobao" in v
    assert "tb" in v


def test_pinyin_jingdong():
    v = pinyin_variants("京东")
    assert "jingdong" in v
    assert "jd" in v


def test_pinyin_baidu():
    v = pinyin_variants("百度")
    assert "baidu" in v
    assert "bd" in v


def test_pinyin_douyin():
    v = pinyin_variants("抖音")
    assert "douyin" in v
    assert "dy" in v


def test_pinyin_kuaishou():
    v = pinyin_variants("快手")
    assert "kuaishou" in v
    assert "ks" in v


def test_pinyin_bilibili():
    v = pinyin_variants("哔哩哔哩")
    assert "bilibili" in v
    assert "blbl" in v


def test_pinyin_wangyiyunyinyue():
    v = pinyin_variants("网易云音乐")
    assert "wangyiyunyinyue" in v
    assert "wyyyy" in v


def test_pinyin_tengxunqq():
    v = pinyin_variants("腾讯QQ")
    assert "tengxunqq" in v
    assert "txqq" in v


# ── System terms ─────────────────────────────────────────────────────────────


def test_pinyin_kongzhimianban():
    v = pinyin_variants("控制面板")
    assert "kongzhimianban" in v
    assert "kzmb" in v


def test_pinyin_renwuguanliqi():
    v = pinyin_variants("任务管理器")
    assert "renwuguanliqi" in v
    assert "rwglq" in v


def test_pinyin_zhucebiao():
    v = pinyin_variants("注册表")
    assert "zhucebiao" in v
    assert "zcb" in v


def test_pinyin_minglingtishifu():
    v = pinyin_variants("命令提示符")
    assert "minglingtishifu" in v
    assert "mltsf" in v


def test_pinyin_shebeiguanliqi():
    v = pinyin_variants("设备管理器")
    assert "shebeiguanliqi" in v
    assert "sbglq" in v


# ── Variant structure validation ─────────────────────────────────────────────


def test_pinyin_variants_contain_full_and_initials():
    """For multi-character CJK, output always contains full pinyin and initials."""
    for text, expected_full, expected_short in [
        ("微信", "weixin", "wx"),
        ("支付宝", "zhifubao", "zfb"),
        ("控制面板", "kongzhimianban", "kzmb"),
        ("淘宝", "taobao", "tb"),
        ("京东", "jingdong", "jd"),
    ]:
        v = pinyin_variants(text)
        assert expected_full in v, f"{text}: expected full '{expected_full}' in {v}"
        assert expected_short in v, f"{text}: expected initials '{expected_short}' in {v}"


def test_pinyin_output_is_deduplicated():
    """Output list contains no duplicate entries."""
    for text in ["微信", "支付宝", "控制面板", "淘宝", "抖音", "哔哩哔哩", "腾讯QQ"]:
        v = pinyin_variants(text)
        assert len(v) == len(set(v)), f"{text}: duplicates in {v}"


def test_pinyin_xpinyin_fallback(monkeypatch):
    import sys

    import core.pinyin_search as pinyin_search

    monkeypatch.setattr(pinyin_search, "_HAS_PYPINYIN", None)
    monkeypatch.setattr(pinyin_search, "_HAS_XPINYIN", None)

    class MockPinyin:
        def get_pinyin(self, text, splitter=""):
            return "mockedpinyin"

        def get_initials(self, text, splitter=""):
            return "mp"

    class MockModule:
        Pinyin = MockPinyin

    # Hide pypinyin by setting it to None in sys.modules, and mock xpinyin
    real_pypinyin = sys.modules.get("pypinyin")
    sys.modules["pypinyin"] = None
    sys.modules["xpinyin"] = MockModule
    try:
        variants = pinyin_search.pinyin_variants("微信")
        assert "mockedpinyin" in variants
        assert "mp" in variants
    finally:
        sys.modules.pop("xpinyin", None)
        if real_pypinyin is not None:
            sys.modules["pypinyin"] = real_pypinyin
        else:
            sys.modules.pop("pypinyin", None)


def test_pinyin_both_libraries_missing(monkeypatch):
    import sys

    import core.pinyin_search as pinyin_search

    monkeypatch.setattr(pinyin_search, "_HAS_PYPINYIN", None)
    monkeypatch.setattr(pinyin_search, "_HAS_XPINYIN", None)

    # Hide both by setting them to None in sys.modules
    real_pypinyin = sys.modules.get("pypinyin")
    real_xpinyin = sys.modules.get("xpinyin")
    sys.modules["pypinyin"] = None
    sys.modules["xpinyin"] = None
    try:
        # Falls back to local _PINYIN dict
        variants = pinyin_search.pinyin_variants("微信")
        assert "weixin" in variants
        assert "wx" in variants
    finally:
        if real_pypinyin is not None:
            sys.modules["pypinyin"] = real_pypinyin
        else:
            sys.modules.pop("pypinyin", None)
        if real_xpinyin is not None:
            sys.modules["xpinyin"] = real_xpinyin
        else:
            sys.modules.pop("xpinyin", None)
