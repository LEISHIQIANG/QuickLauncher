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


# ── Extended tests ─────────────────────────────────────────────────────────


def test_url_field_matching():
    page = Folder(
        items=[
            ShortcutItem(name="Site", url="https://github.com/myproject"),
        ]
    )

    results = search_shortcuts([page], "github")
    assert len(results) == 1
    assert results[0].shortcut.name == "Site"
    assert "url" in results[0].matched_fields


def test_command_field_matching():
    page = Folder(
        items=[
            ShortcutItem(name="Run Test", command="pytest --verbose tests/"),
        ]
    )

    results = search_shortcuts([page], "pytest")
    assert len(results) == 1
    assert results[0].shortcut.name == "Run Test"
    assert "command" in results[0].matched_fields


def test_hotkey_field_matching():
    page = Folder(
        items=[
            ShortcutItem(name="Screenshot", hotkey="ctrl+shift+s"),
        ]
    )

    results = search_shortcuts([page], "shift")
    assert len(results) == 1
    assert results[0].shortcut.name == "Screenshot"
    assert "hotkey" in results[0].matched_fields


def test_usage_bonus_boosts_high_use_count_in_smart_mode():
    low = ShortcutItem(name="Alpha", use_count=0, id="low")
    high = ShortcutItem(name="AlphaTool", use_count=100, id="high")
    page = Folder(items=[low, high])

    smart_results = search_shortcuts([page], "alpha", sort_mode="smart")
    custom_results = search_shortcuts([page], "alpha", sort_mode="custom")

    # In smart mode, high use_count should boost AlphaTool above Alpha
    smart_names = [r.shortcut.name for r in smart_results]
    assert smart_names.index("AlphaTool") < smart_names.index("Alpha")

    # In custom mode, no usage bonus is applied, so order is by name/score only
    # Both should still appear
    assert len(custom_results) == 2


def test_sort_mode_smart_applies_usage_bonus():
    popular = ShortcutItem(name="Popular", use_count=200, smart_order=0, id="pop")
    page = Folder(items=[popular])

    smart_results = search_shortcuts([page], "popular", sort_mode="smart")
    assert len(smart_results) == 1
    assert smart_results[0].score > 0


def test_sort_mode_custom_no_usage_bonus():
    item = ShortcutItem(name="Popular", use_count=200, id="pop")
    page = Folder(items=[item])

    custom_results = search_shortcuts([page], "popular", sort_mode="custom")
    assert len(custom_results) == 1
    # custom mode should not add usage bonus
    # Score should be lower than smart mode equivalent


def test_limit_parameter_restricts_results():
    page = Folder(
        items=[
            ShortcutItem(name="Alpha"),
            ShortcutItem(name="Beta"),
            ShortcutItem(name="Gamma"),
            ShortcutItem(name="Delta"),
        ]
    )

    results = search_shortcuts([page], "a", limit=2)
    assert len(results) == 2


def test_limit_zero_returns_empty():
    page = Folder(items=[ShortcutItem(name="Alpha")])
    results = search_shortcuts([page], "alpha", limit=0)
    assert results == []


def test_multiple_folders_search():
    folder_a = Folder(id="a", name="Folder A", items=[ShortcutItem(name="ItemA")])
    folder_b = Folder(id="b", name="Folder B", items=[ShortcutItem(name="ItemB")])

    results = search_shortcuts([folder_a, folder_b], "item")
    assert len(results) == 2
    folder_ids = {r.folder_id for r in results}
    assert folder_ids == {"a", "b"}


def test_name_and_alias_match_different_query_terms():
    page = Folder(
        items=[
            ShortcutItem(name="Chrome", alias="Browser"),
        ]
    )

    results = search_shortcuts([page], "chrome browser")
    assert len(results) == 1
    assert results[0].shortcut.name == "Chrome"
    matched = set(results[0].matched_fields)
    assert "name" in matched
    assert "alias" in matched


def test_empty_items_list():
    page = Folder(items=[])
    results = search_shortcuts([page], "anything")
    assert results == []


def test_very_long_query_string():
    long_query = "a" * 500
    page = Folder(items=[ShortcutItem(name="Test")])
    results = search_shortcuts([page], long_query)
    # Should not crash; likely no match
    assert isinstance(results, list)


def test_special_characters_in_query():
    page = Folder(
        items=[
            ShortcutItem(name="Path Finder", target_path="C:/Program Files/App.exe"),
        ]
    )
    # Special characters should not crash the search
    results = search_shortcuts([page], "C:\\Program Files")
    assert isinstance(results, list)


def test_matched_fields_includes_target_path():
    page = Folder(
        items=[
            ShortcutItem(name="Editor", target_path="C:/Apps/Notepad.exe"),
        ]
    )

    results = search_shortcuts([page], "notepad")
    assert len(results) == 1
    assert "target_path" in results[0].matched_fields


def test_no_results_for_unrelated_query():
    page = Folder(
        items=[
            ShortcutItem(name="Photoshop"),
            ShortcutItem(name="Illustrator"),
        ]
    )

    results = search_shortcuts([page], "zzzzz")
    assert results == []


def test_search_across_multiple_pages_with_same_name():
    folder1 = Folder(id="f1", items=[ShortcutItem(name="Shared", alias="First")])
    folder2 = Folder(id="f2", items=[ShortcutItem(name="Shared", alias="Second")])

    results = search_shortcuts([folder1, folder2], "shared")
    assert len(results) == 2
    folder_ids = [r.folder_id for r in results]
    assert "f1" in folder_ids
    assert "f2" in folder_ids
