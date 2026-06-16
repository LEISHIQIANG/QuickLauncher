"""Tests for core.data_models: ShortcutType, ShortcutItem, Folder, AppSettings, AppData."""

import time

from core.data_models import (
    DEFAULT_SPECIAL_APPS,
    AppData,
    AppSettings,
    Folder,
    ShortcutItem,
    ShortcutType,
)
from core.runtime_constants import (
    COMMAND_CHAIN_MAX_STEPS,
    DEFAULT_COMMAND_OUTPUT_MAX_CHARS,
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    MIN_COMMAND_OUTPUT_MAX_CHARS,
    MIN_COMMAND_TIMEOUT_SECONDS,
    normalize_chain_step_delay_ms,
)

# ---------------------------------------------------------------------------
# 1. ShortcutType enum
# ---------------------------------------------------------------------------


def test_shortcut_type_values():
    assert ShortcutType.FILE.value == "file"
    assert ShortcutType.FOLDER.value == "folder"
    assert ShortcutType.URL.value == "url"
    assert ShortcutType.HOTKEY.value == "hotkey"
    assert ShortcutType.COMMAND.value == "command"
    assert ShortcutType.CHAIN.value == "chain"
    assert ShortcutType.BATCH_LAUNCH.value == "batch_launch"


def test_shortcut_type_has_all_members():
    assert len(ShortcutType) == 8


def test_shortcut_type_from_string():
    for member in ShortcutType:
        assert ShortcutType(member.value) == member


# ---------------------------------------------------------------------------
# 2. ShortcutItem construction and defaults
# ---------------------------------------------------------------------------


def test_shortcut_item_defaults():
    item = ShortcutItem()
    assert item.name == ""
    assert item.type == ShortcutType.FILE
    assert item.order == 0
    assert item.enabled is True
    assert item.tags == []
    assert item.last_used_at == 0.0
    assert item.use_count == 0
    assert item.smart_order is None
    assert item.target_path == ""
    assert item.target_args == ""
    assert item.working_dir == ""
    assert item.hotkey == ""
    assert item.hotkey_modifiers == []
    assert item.hotkey_key == ""
    assert item.hotkey_keys == []
    assert item.url == ""
    assert item.preferred_browser_path == ""
    assert item.preferred_browser_args == ""
    assert item.command == ""
    assert item.command_type == "cmd"
    assert item.show_window is False
    assert item.command_variables_enabled is False
    assert item.capture_output is False
    assert item.command_timeout_seconds == DEFAULT_COMMAND_TIMEOUT_SECONDS
    assert item.command_output_max_chars == DEFAULT_COMMAND_OUTPUT_MAX_CHARS
    assert item.command_panel_size == "medium"
    assert item.command_params == []
    assert item.command_env == {}
    assert item.command_encoding == "auto"
    assert item.chain_steps == []
    assert item.chain_result_window == "medium"
    assert item.raw_mode is False
    assert item.macro_events == []
    assert item.macro_speed == 1.0
    assert item.macro_include_mouse_move is False
    assert item.macro_hide_while_recording is False
    assert item.trigger_mode == "immediate"
    assert item.icon_path == ""
    assert item.icon_data == ""
    assert item.alias == ""
    assert item.icon_invert_light is False
    assert item.icon_invert_dark is False
    assert item.icon_invert_with_theme is False
    assert item.icon_invert_current is False
    assert item.icon_invert_theme_when_set == ""
    assert item.run_as_admin is False


def test_shortcut_item_custom_values():
    item = ShortcutItem(name="Test", type=ShortcutType.URL, url="https://example.com", order=3)
    assert item.name == "Test"
    assert item.type == ShortcutType.URL
    assert item.url == "https://example.com"
    assert item.order == 3


def test_shortcut_item_unique_ids():
    a = ShortcutItem()
    b = ShortcutItem()
    assert a.id != b.id


# ---------------------------------------------------------------------------
# 3. ShortcutItem to_dict / from_dict round-trip
# ---------------------------------------------------------------------------


def test_shortcut_item_round_trip():
    item = ShortcutItem(
        name="Launch",
        type=ShortcutType.COMMAND,
        target_path="notepad.exe",
        target_args="--verbose",
        working_dir="C:\\tmp",
        tags=["dev", "tools"],
        enabled=False,
        order=5,
        use_count=10,
        command="echo hi",
        command_type="powershell",
        show_window=True,
        capture_output=True,
        command_timeout_seconds=30,
        command_output_max_chars=5000,
        command_panel_size="large",
        command_params=[{"name": "p1", "type": "text"}],
        command_env={"KEY": "VAL"},
        command_encoding="utf-8",
        alias="N",
        run_as_admin=True,
    )
    data = item.to_dict()
    restored = ShortcutItem.from_dict(data)

    # id should be preserved across round-trip
    assert restored.id == item.id
    assert restored.name == "Launch"
    assert restored.type == ShortcutType.COMMAND
    assert restored.target_path == "notepad.exe"
    assert restored.target_args == "--verbose"
    assert restored.working_dir == "C:\\tmp"
    assert restored.tags == ["dev", "tools"]
    assert restored.enabled is False
    assert restored.order == 5
    assert restored.use_count == 10
    assert restored.command == "echo hi"
    assert restored.command_type == "powershell"
    assert restored.show_window is True
    assert restored.capture_output is True
    assert restored.command_timeout_seconds == 30
    assert restored.command_output_max_chars == 5000
    assert restored.command_panel_size == "large"
    assert restored.command_params[0]["name"] == "p1"
    assert restored.command_env == {"KEY": "VAL"}
    assert restored.command_encoding == "utf-8"
    assert restored.alias == "N"
    assert restored.run_as_admin is True


def test_shortcut_item_macro_options_round_trip():
    item = ShortcutItem(
        name="宏",
        type=ShortcutType.MACRO,
        macro_events=[{"type": 6, "delay_us": 200_000, "vk_code": 65}],
        macro_speed=2.0,
        macro_hide_while_recording=True,
    )

    data = item.to_dict()
    restored = ShortcutItem.from_dict(data)

    assert data["macro_speed"] == 2.0
    assert data["macro_hide_while_recording"] is True
    assert restored.type == ShortcutType.MACRO
    assert restored.macro_events == [{"type": 6, "delay_us": 200_000, "vk_code": 65}]
    assert restored.macro_speed == 2.0
    assert restored.macro_hide_while_recording is True


def test_shortcut_item_from_dict_missing_keys():
    restored = ShortcutItem.from_dict({"name": "bare"})
    assert restored.name == "bare"
    assert restored.type == ShortcutType.FILE
    assert restored.enabled is True
    assert restored.tags == []


def test_shortcut_item_from_dict_invalid_type():
    restored = ShortcutItem.from_dict({"type": "nonexistent"})
    assert restored.type == ShortcutType.FILE


def test_shortcut_item_to_dict_type_is_string():
    item = ShortcutItem(type=ShortcutType.HOTKEY)
    data = item.to_dict()
    assert data["type"] == "hotkey"
    assert isinstance(data["type"], str)


def test_hotkey_multiple_main_keys_round_trip_and_legacy_fallback():
    item = ShortcutItem(
        type=ShortcutType.HOTKEY,
        hotkey="Win + A + B",
        hotkey_modifiers=["win"],
        hotkey_key="a",
        hotkey_keys=["a", "b"],
    )

    restored = ShortcutItem.from_dict(item.to_dict())
    legacy = ShortcutItem.from_dict({"type": "hotkey", "hotkey_key": "f8"})

    assert restored.hotkey_keys == ["a", "b"]
    assert restored.hotkey_key == "a"
    assert legacy.hotkey_keys == ["f8"]


def test_batch_launch_steps_round_trip():
    item = ShortcutItem(
        id="batch",
        name="Batch",
        type=ShortcutType.BATCH_LAUNCH,
        batch_launch_steps=[{"shortcut_id": "one", "delay_ms": 250}],
    )

    restored = ShortcutItem.from_dict(item.to_dict())

    assert restored.type == ShortcutType.BATCH_LAUNCH
    assert restored.module_id == "quicklauncher.batch_launch"
    assert restored.batch_launch_steps[0]["shortcut_id"] == "one"
    assert restored.batch_launch_steps[0]["delay_ms"] == 250
    assert restored.chain_steps == []


# ---------------------------------------------------------------------------
# 4. _normalize_tags
# ---------------------------------------------------------------------------


def test_normalize_tags_none():
    assert ShortcutItem._normalize_tags(None) == []


def test_normalize_tags_empty_string():
    assert ShortcutItem._normalize_tags("") == []


def test_normalize_tags_empty_list():
    assert ShortcutItem._normalize_tags([]) == []


def test_normalize_tags_single_string():
    assert ShortcutItem._normalize_tags("dev") == ["dev"]


def test_normalize_tags_list():
    assert ShortcutItem._normalize_tags(["a", "b", "c"]) == ["a", "b", "c"]


def test_normalize_tags_strips_whitespace():
    assert ShortcutItem._normalize_tags(["  x  "]) == ["x"]


def test_normalize_tags_deduplicates_case_insensitive():
    result = ShortcutItem._normalize_tags(["Dev", "dev", "DEV"])
    assert result == ["Dev"]


def test_normalize_tags_skips_empty_entries():
    assert ShortcutItem._normalize_tags(["", "  ", "valid"]) == ["valid"]


def test_normalize_tags_skips_none_entries():
    assert ShortcutItem._normalize_tags([None, "valid"]) == ["valid"]


def test_normalize_tags_preserves_original_casing():
    result = ShortcutItem._normalize_tags(["MyTag"])
    assert result == ["MyTag"]


# ---------------------------------------------------------------------------
# 5. _normalize_command_params
# ---------------------------------------------------------------------------


def test_normalize_command_params_not_list():
    assert ShortcutItem._normalize_command_params("bad") == []
    assert ShortcutItem._normalize_command_params(None) == []


def test_normalize_command_params_skips_non_dict():
    assert ShortcutItem._normalize_command_params([1, "x", None]) == []


def test_normalize_command_params_skips_no_name():
    assert ShortcutItem._normalize_command_params([{"type": "text"}]) == []


def test_normalize_command_params_basic():
    params = [{"name": "arg1", "type": "text", "required": True, "default": "hi"}]
    result = ShortcutItem._normalize_command_params(params)
    assert len(result) == 1
    assert result[0]["name"] == "arg1"
    assert result[0]["type"] == "text"
    assert result[0]["required"] is True
    assert result[0]["default"] == "hi"
    assert result[0]["choices"] == []
    assert result[0]["sensitive"] is False


def test_normalize_command_params_invalid_type_fallback():
    params = [{"name": "x", "type": "unknown"}]
    result = ShortcutItem._normalize_command_params(params)
    assert result[0]["type"] == "text"


def test_normalize_command_params_choices_string():
    params = [{"name": "opt", "type": "choice", "choices": "a, b, c"}]
    result = ShortcutItem._normalize_command_params(params)
    assert result[0]["choices"] == ["a", "b", "c"]


def test_normalize_command_params_choices_list():
    params = [{"name": "opt", "type": "choice", "choices": ["x", "y"]}]
    result = ShortcutItem._normalize_command_params(params)
    assert result[0]["choices"] == ["x", "y"]


def test_normalize_command_params_choices_invalid_type():
    params = [{"name": "opt", "choices": 42}]
    result = ShortcutItem._normalize_command_params(params)
    assert result[0]["choices"] == []


def test_normalize_command_params_sensitive():
    params = [{"name": "secret", "sensitive": True}]
    result = ShortcutItem._normalize_command_params(params)
    assert result[0]["sensitive"] is True
    assert result[0]["remember"] is False


def test_normalize_command_params_new_fields_and_whitelists():
    params = [
        {
            "name": "body",
            "type": "textarea",
            "label": "Body",
            "placeholder": "JSON",
            "help": "Paste JSON",
            "multiline": True,
            "remember": True,
            "source": "clipboard",
            "validator": "json",
            "pattern": ".*",
            "min_value": "1",
            "max_value": "5",
            "advanced": True,
        },
        {"name": "bad", "source": "bad", "validator": "bad"},
    ]
    result = ShortcutItem._normalize_command_params(params)
    assert result[0]["type"] == "textarea"
    assert result[0]["label"] == "Body"
    assert result[0]["placeholder"] == "JSON"
    assert result[0]["help"] == "Paste JSON"
    assert result[0]["multiline"] is True
    assert result[0]["remember"] is True
    assert result[0]["source"] == "clipboard"
    assert result[0]["validator"] == "json"
    assert result[0]["pattern"] == ".*"
    assert result[0]["min_value"] == "1"
    assert result[0]["max_value"] == "5"
    assert result[0]["advanced"] is True
    assert result[1]["source"] == ""
    assert result[1]["validator"] == ""


# ---------------------------------------------------------------------------
# 6. _normalize_command_env
# ---------------------------------------------------------------------------


def test_normalize_command_env_dict():
    result = ShortcutItem._normalize_command_env({"A": "1", "B": "2"})
    assert result == {"A": "1", "B": "2"}


def test_normalize_command_env_strips_keys():
    result = ShortcutItem._normalize_command_env({"  KEY  ": "val"})
    assert "KEY" in result


def test_normalize_command_env_skips_empty_keys():
    result = ShortcutItem._normalize_command_env({"": "val"})
    assert result == {}


def test_normalize_command_env_not_dict_or_string():
    assert ShortcutItem._normalize_command_env(42) == {}
    assert ShortcutItem._normalize_command_env(None) == {}


def test_normalize_command_env_string_multiline():
    text = "FOO=bar\nBAZ=qux"
    result = ShortcutItem._normalize_command_env(text)
    assert result == {"FOO": "bar", "BAZ": "qux"}


def test_normalize_command_env_string_skips_comments():
    text = "# comment\nFOO=bar\n"
    result = ShortcutItem._normalize_command_env(text)
    assert result == {"FOO": "bar"}


def test_normalize_command_env_string_skips_no_equals():
    text = "no_equals_line\nFOO=bar"
    result = ShortcutItem._normalize_command_env(text)
    assert result == {"FOO": "bar"}


def test_normalize_command_env_string_skips_empty_lines():
    text = "\n  \nFOO=bar"
    result = ShortcutItem._normalize_command_env(text)
    assert result == {"FOO": "bar"}


def test_normalize_command_env_string_value_with_equals():
    text = "URL=http://example.com?a=1"
    result = ShortcutItem._normalize_command_env(text)
    assert result["URL"] == "http://example.com?a=1"


# ---------------------------------------------------------------------------
# 7. _normalize_chain_steps
# ---------------------------------------------------------------------------


def test_normalize_chain_steps_not_list():
    assert ShortcutItem._normalize_chain_steps("bad") == []


def test_normalize_chain_steps_empty():
    assert ShortcutItem._normalize_chain_steps([]) == []


def test_normalize_chain_steps_skips_non_dict():
    assert ShortcutItem._normalize_chain_steps([1, "x", None]) == []


def test_normalize_chain_steps_skips_no_shortcut_id():
    assert ShortcutItem._normalize_chain_steps([{"delay_ms": 100}]) == []


def test_normalize_chain_steps_basic():
    steps = [{"shortcut_id": "s1", "delay_ms": 500, "stop_on_error": False}]
    result = ShortcutItem._normalize_chain_steps(steps)
    assert len(result) == 1
    assert result[0]["shortcut_id"] == "s1"
    assert result[0]["delay_ms"] == 500
    assert result[0]["stop_on_error"] is False
    assert result[0]["enabled"] is True
    assert result[0]["use_previous_output"] is False
    assert result[0]["input_binding"] == ""
    assert result[0]["param_bindings"] == {}
    assert result[0]["args"] == {}


def test_normalize_chain_steps_bindings_and_args():
    steps = [
        {
            "shortcut_id": "s1",
            "input_binding": "prev.stdout",
            "param_bindings": {"host": "prev.outputs.host", "empty": ""},
            "args": {"port": 443, "": "ignored"},
        }
    ]
    result = ShortcutItem._normalize_chain_steps(steps)
    assert result[0]["input_binding"] == "prev.stdout"
    assert result[0]["param_bindings"] == {"host": "prev.outputs.host"}
    assert result[0]["args"] == {"port": "443"}


def test_normalize_chain_steps_preserves_id():
    steps = [{"id": "fixed-id", "shortcut_id": "s1"}]
    result = ShortcutItem._normalize_chain_steps(steps)
    assert result[0]["id"] == "fixed-id"


def test_normalize_chain_steps_generates_id():
    steps = [{"shortcut_id": "s1"}]
    result = ShortcutItem._normalize_chain_steps(steps)
    assert isinstance(result[0]["id"], str)
    assert len(result[0]["id"]) > 0


def test_normalize_chain_steps_truncates_beyond_max():
    steps = [{"shortcut_id": f"s{i}"} for i in range(COMMAND_CHAIN_MAX_STEPS + 50)]
    result = ShortcutItem._normalize_chain_steps(steps)
    assert len(result) == COMMAND_CHAIN_MAX_STEPS


def test_normalize_chain_steps_delay_clamped():
    steps = [{"shortcut_id": "s1", "delay_ms": 999999999}]
    result = ShortcutItem._normalize_chain_steps(steps)
    assert result[0]["delay_ms"] == normalize_chain_step_delay_ms(999999999)


def test_chain_canvas_roundtrip():
    item = ShortcutItem(type=ShortcutType.CHAIN, name="Canvas")
    item.chain_canvas = {
        "version": 1,
        "nodes": [
            {"id": "n1", "node_type": "shortcut", "shortcut_id": "a", "x": 10, "y": 20, "order": 1},
            {"id": "n2", "node_type": "processor", "processor_id": "text_template", "x": 240, "y": 20, "order": 2},
        ],
        "connections": [
            {"id": "c1", "source_node": "n1", "source_port": "stdout", "target_node": "n2", "target_port": "input"}
        ],
    }

    loaded = ShortcutItem.from_dict(item.to_dict())

    assert loaded.chain_canvas["nodes"][0]["shortcut_id"] == "a"
    assert loaded.chain_canvas["nodes"][1]["processor_id"] == "text_template"
    assert loaded.chain_canvas["connections"][0]["source_port"] == "stdout"


def test_old_chain_steps_generate_canvas_connections():
    loaded = ShortcutItem.from_dict(
        {
            "type": "chain",
            "chain_steps": [
                {"id": "s1", "shortcut_id": "first"},
                {
                    "id": "s2",
                    "shortcut_id": "second",
                    "input_binding": "1.stdout",
                    "param_bindings": {"host": "1.output"},
                },
            ],
        }
    )

    assert len(loaded.chain_canvas["nodes"]) == 2
    assert {c["target_port"] for c in loaded.chain_canvas["connections"]} == {"input", "host"}


# ---------------------------------------------------------------------------
# 8. mark_used
# ---------------------------------------------------------------------------


def test_mark_used_without_timestamp():
    item = ShortcutItem()
    before = time.time()
    item.mark_used()
    after = time.time()
    assert item.use_count == 1
    assert before <= item.last_used_at <= after


def test_mark_used_with_timestamp():
    item = ShortcutItem()
    ts = 1700000000.0
    item.mark_used(timestamp=ts)
    assert item.last_used_at == ts
    assert item.use_count == 1


def test_mark_used_increments():
    item = ShortcutItem(use_count=5)
    item.mark_used()
    assert item.use_count == 6


def test_mark_used_negative_count():
    item = ShortcutItem()
    item.use_count = -3
    item.mark_used()
    # max(0, int(-3)) + 1 = 1
    assert item.use_count == 1


# ---------------------------------------------------------------------------
# 9. is_enabled
# ---------------------------------------------------------------------------


def test_is_enabled_true():
    assert ShortcutItem(enabled=True).is_enabled() is True


def test_is_enabled_false():
    assert ShortcutItem(enabled=False).is_enabled() is False


# ---------------------------------------------------------------------------
# 10. Folder
# ---------------------------------------------------------------------------


def test_folder_defaults():
    f = Folder()
    assert f.name == ""
    assert f.order == 0
    assert f.is_system is False
    assert f.is_dock is False
    assert f.is_icon_repo is False
    assert f.items == []
    assert f.linked_path == ""
    assert f.auto_sync is False
    assert f.last_sync_time == 0.0


def test_folder_custom():
    f = Folder(id="test", name="MyFolder", order=3, is_dock=True)
    assert f.id == "test"
    assert f.name == "MyFolder"
    assert f.order == 3
    assert f.is_dock is True


def test_folder_round_trip():
    item = ShortcutItem(name="Link", type=ShortcutType.URL, url="https://x.com")
    f = Folder(id="f1", name="Page", items=[item], linked_path="C:\\sync")
    data = f.to_dict()
    restored = Folder.from_dict(data)
    assert restored.id == "f1"
    assert restored.name == "Page"
    assert restored.linked_path == "C:\\sync"
    assert len(restored.items) == 1
    assert restored.items[0].name == "Link"
    assert restored.items[0].type == ShortcutType.URL


def test_folder_from_dict_empty():
    restored = Folder.from_dict({})
    assert restored.name == ""
    assert restored.items == []


def test_folder_round_trip_preserves_item_ids():
    item1 = ShortcutItem(name="A")
    item2 = ShortcutItem(name="B")
    f = Folder(items=[item1, item2])
    data = f.to_dict()
    restored = Folder.from_dict(data)
    assert restored.items[0].id == item1.id
    assert restored.items[1].id == item2.id


# ---------------------------------------------------------------------------
# 11. AppSettings construction, to_dict, from_dict, alpha properties
# ---------------------------------------------------------------------------


def test_app_settings_defaults():
    s = AppSettings()
    assert s.theme == "dark"
    assert s.bg_alpha == 90
    assert s.dock_bg_alpha == 90
    assert s.icon_alpha == 1.0
    assert s.icon_size == 24
    assert s.cell_size == 44
    assert s.cols == 5
    assert s.corner_radius == 10
    assert s.close_after_launch is True
    assert s.auto_start is False
    assert s.sort_mode == "custom"
    assert s.dock_enabled is True
    assert s.popup_align_mode == "mouse_center"
    assert s.bg_mode == "theme"
    assert s.special_apps == DEFAULT_SPECIAL_APPS


def test_app_settings_alpha_255():
    s = AppSettings(bg_alpha=100)
    assert s.bg_alpha_255 == 255


def test_app_settings_alpha_255_zero():
    s = AppSettings(bg_alpha=0)
    assert s.bg_alpha_255 == 0


def test_app_settings_alpha_255_half():
    s = AppSettings(bg_alpha=50)
    assert s.bg_alpha_255 == 127


def test_app_settings_dock_alpha_255():
    s = AppSettings(dock_bg_alpha=100)
    assert s.dock_bg_alpha_255 == 255


def test_app_settings_dock_alpha_255_zero():
    s = AppSettings(dock_bg_alpha=0)
    assert s.dock_bg_alpha_255 == 0


def test_app_settings_round_trip():
    s = AppSettings(
        theme="light",
        bg_alpha=75,
        dock_bg_alpha=60,
        icon_size=32,
        cols=4,
        sort_mode="smart",
        language="en_US",
    )
    data = s.to_dict()
    restored = AppSettings.from_dict(data)
    assert restored.theme == "light"
    assert restored.bg_alpha == 75
    assert restored.dock_bg_alpha == 60
    assert restored.icon_size == 32
    assert restored.cols == 4
    assert restored.sort_mode == "smart"
    assert restored.language == "en_US"


# ---------------------------------------------------------------------------
# 12. AppSettings.from_dict bg_alpha > 100 (conversion from 255)
# ---------------------------------------------------------------------------


def test_app_settings_from_dict_bg_alpha_255_to_100():
    """Legacy data stores alpha 0-255; from_dict should convert to 0-100."""
    restored = AppSettings.from_dict({"bg_alpha": 255})
    assert restored.bg_alpha == 100


def test_app_settings_from_dict_bg_alpha_128():
    restored = AppSettings.from_dict({"bg_alpha": 128})
    assert restored.bg_alpha == int(128 * 100 / 255)


def test_app_settings_from_dict_bg_alpha_within_range():
    """Values <= 100 should not be converted."""
    restored = AppSettings.from_dict({"bg_alpha": 50})
    assert restored.bg_alpha == 50


def test_app_settings_from_dict_invalid_sort_mode():
    restored = AppSettings.from_dict({"sort_mode": "invalid"})
    assert restored.sort_mode == "custom"


def test_app_settings_from_dict_special_apps_empty_falls_back():
    restored = AppSettings.from_dict({"special_apps": []})
    assert restored.special_apps == DEFAULT_SPECIAL_APPS


# ---------------------------------------------------------------------------
# 13. AppData
# ---------------------------------------------------------------------------


def test_app_data_default_folders():
    ad = AppData()
    assert ad.version == "2.5"
    assert len(ad.folders) == 2
    assert ad.folders[0].id == "dock"
    assert ad.folders[0].is_dock is True
    assert ad.folders[1].id == "default"
    assert ad.folders[1].is_dock is False


def test_app_data_get_dock():
    ad = AppData()
    dock = ad.get_dock()
    assert dock is not None
    assert dock.id == "dock"
    assert dock.is_dock is True


def test_app_data_get_pages():
    ad = AppData()
    pages = ad.get_pages()
    assert len(pages) == 1
    assert pages[0].id == "default"


def test_app_data_get_folder_by_id():
    ad = AppData()
    assert ad.get_folder_by_id("dock") is not None
    assert ad.get_folder_by_id("default") is not None
    assert ad.get_folder_by_id("nonexistent") is None


def test_app_data_get_dock_returns_none_if_missing():
    ad = AppData(folders=[Folder(id="x", name="X", is_dock=False)])
    assert ad.get_dock() is None


# ---------------------------------------------------------------------------
# 14. AppData to_dict / from_dict round-trip
# ---------------------------------------------------------------------------


def test_app_data_round_trip():
    ad = AppData()
    ad.version = "3.0"
    ad.settings.theme = "light"
    # Add an item to the dock
    dock = ad.get_dock()
    dock.items.append(ShortcutItem(name="Notepad", type=ShortcutType.FILE, target_path="notepad.exe"))

    data = ad.to_dict()
    assert data["version"] == "3.0"
    assert data["settings"]["theme"] == "light"
    assert len(data["folders"][0]["items"]) == 1

    restored = AppData.from_dict(data)
    assert restored.version == "3.0"
    assert restored.settings.theme == "light"
    restored_dock = restored.get_dock()
    assert restored_dock is not None
    assert len(restored_dock.items) == 1
    assert restored_dock.items[0].name == "Notepad"


def test_app_data_from_dict_empty():
    restored = AppData.from_dict({})
    # Should create default folders since no folders provided
    assert len(restored.folders) == 2
    assert restored.version == "1.0"


def test_app_data_from_dict_preserves_folder_items():
    item = ShortcutItem(name="Test", type=ShortcutType.COMMAND, command="echo ok")
    folder = Folder(id="f1", name="Cmds", items=[item])
    data = {
        "version": "2.5",
        "folders": [folder.to_dict()],
    }
    restored = AppData.from_dict(data)
    assert len(restored.folders) == 1
    assert restored.folders[0].items[0].command == "echo ok"
    assert restored.folders[0].items[0].id == item.id


# ---------------------------------------------------------------------------
# 15. DEFAULT_SPECIAL_APPS
# ---------------------------------------------------------------------------


def test_default_special_apps_is_list():
    assert isinstance(DEFAULT_SPECIAL_APPS, list)


def test_default_special_apps_non_empty():
    assert len(DEFAULT_SPECIAL_APPS) > 0


def test_default_special_apps_all_strings():
    assert all(isinstance(s, str) for s in DEFAULT_SPECIAL_APPS)


def test_default_special_apps_all_lowercase():
    assert all(s == s.lower() for s in DEFAULT_SPECIAL_APPS)


def test_default_special_apps_contains_known_entries():
    assert "autocad" in DEFAULT_SPECIAL_APPS
    assert "blender" in DEFAULT_SPECIAL_APPS
    assert "revit" in DEFAULT_SPECIAL_APPS
    assert "aftereffects" in DEFAULT_SPECIAL_APPS


def test_default_special_apps_no_duplicates():
    assert len(DEFAULT_SPECIAL_APPS) == len(set(DEFAULT_SPECIAL_APPS))


# ---------------------------------------------------------------------------
# Extra: from_dict command_panel_size / chain_result_window / encoding validation
# ---------------------------------------------------------------------------


def test_from_dict_command_panel_size_invalid():
    item = ShortcutItem.from_dict({"command_panel_size": "huge"})
    assert item.command_panel_size == "medium"


def test_from_dict_command_panel_size_valid():
    for size in ("small", "medium", "large"):
        item = ShortcutItem.from_dict({"command_panel_size": size})
        assert item.command_panel_size == size


def test_from_dict_chain_result_window_invalid():
    item = ShortcutItem.from_dict({"chain_result_window": "invalid"})
    assert item.chain_result_window == "medium"


def test_from_dict_command_encoding_invalid():
    item = ShortcutItem.from_dict({"command_encoding": "latin1"})
    assert item.command_encoding == "auto"


def test_from_dict_command_encoding_valid():
    for enc in ("auto", "utf-8", "gbk", "mbcs"):
        item = ShortcutItem.from_dict({"command_encoding": enc})
        assert item.command_encoding == enc


def test_from_dict_command_timeout_normalized():
    item = ShortcutItem.from_dict({"command_timeout_seconds": -5})
    assert item.command_timeout_seconds == MIN_COMMAND_TIMEOUT_SECONDS


def test_from_dict_command_output_max_chars_normalized():
    item = ShortcutItem.from_dict({"command_output_max_chars": 0})
    assert item.command_output_max_chars == MIN_COMMAND_OUTPUT_MAX_CHARS
