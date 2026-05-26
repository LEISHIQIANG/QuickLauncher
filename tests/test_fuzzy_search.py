from core.data_models import Folder, ShortcutItem
from core.fuzzy_search import search_shortcuts


def test_empty_query_returns_no_results():
    page = Folder(items=[ShortcutItem(name="Photoshop")])

    assert search_shortcuts([page], "") == []


def test_english_subsequence_matches_name():
    page = Folder(id="default", name="常用", items=[ShortcutItem(name="Photoshop")])

    results = search_shortcuts([page], "ps")

    assert [r.shortcut.name for r in results] == ["Photoshop"]
    assert "name" in results[0].matched_fields


def test_chinese_alias_tags_and_path_match():
    page = Folder(
        items=[
            ShortcutItem(name="工具", alias="画图", tags=["设计"], target_path="C:/Apps/Paint.exe"),
            ShortcutItem(name="浏览器", alias="", tags=["网络"], target_path="C:/Apps/Browser.exe"),
        ]
    )

    assert search_shortcuts([page], "画图")[0].shortcut.name == "工具"
    assert search_shortcuts([page], "网络")[0].shortcut.name == "浏览器"
    assert search_shortcuts([page], "paint")[0].shortcut.name == "工具"


def test_disabled_items_are_excluded():
    page = Folder(items=[ShortcutItem(name="Hidden", enabled=False)])

    assert search_shortcuts([page], "hidden") == []


def test_same_score_keeps_display_order():
    first = ShortcutItem(name="Alpha", order=2, smart_order=0)
    second = ShortcutItem(name="Alpha", order=1, smart_order=1)
    page = Folder(items=[first, second])

    custom_results = search_shortcuts([page], "alpha", sort_mode="custom")
    smart_results = search_shortcuts([page], "alpha", sort_mode="smart")

    assert [r.shortcut for r in custom_results] == [second, first]
    assert [r.shortcut for r in smart_results] == [first, second]


def test_acronym_and_compact_word_matching():
    page = Folder(
        items=[
            ShortcutItem(name="Visual Studio Code"),
            ShortcutItem(name="Visual Studio Installer"),
        ]
    )

    assert search_shortcuts([page], "vsc")[0].shortcut.name == "Visual Studio Code"
    assert search_shortcuts([page], "visualstudio")[0].shortcut.name == "Visual Studio Code"


def test_multi_keyword_can_match_across_fields():
    page = Folder(
        items=[
            ShortcutItem(name="Chrome", alias="浏览器", tags=["工作"]),
            ShortcutItem(name="Chrome Canary", tags=["测试"]),
        ]
    )

    result = search_shortcuts([page], "浏览器 工作")[0]

    assert result.shortcut.name == "Chrome"
    assert set(result.matched_fields) >= {"alias", "tags"}


def test_path_basename_and_minor_typo_match():
    page = Folder(
        items=[
            ShortcutItem(name="Image Tool", target_path="C:/Program Files/Adobe/Photoshop.exe"),
            ShortcutItem(name="Photo Viewer", target_path="C:/Windows/System32/PhotosApp.exe"),
        ]
    )

    assert search_shortcuts([page], "photoshop")[0].shortcut.name == "Image Tool"
    assert search_shortcuts([page], "photosop")[0].shortcut.name == "Image Tool"


def test_pinyin_initials_match_chinese_fields():
    page = Folder(
        items=[
            ShortcutItem(name="设置", alias="配置", tags=["系统"]),
            ShortcutItem(name="画图", alias="绘图", tags=["设计"]),
        ]
    )

    assert search_shortcuts([page], "sz")[0].shortcut.name == "设置"
    assert search_shortcuts([page], "huatu")[0].shortcut.name == "画图"
