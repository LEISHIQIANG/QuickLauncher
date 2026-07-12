from types import SimpleNamespace

from ui.config_window.folder_panel_helpers import (
    decode_mime_text,
    is_auto_sync_folder_locked,
    move_folder_id_to_target,
    shortcut_ids_from_mime,
    should_copy_shortcut_drop,
)


class _Payload:
    def __init__(self, value):
        self._value = value

    def data(self):
        return self._value


class _Mime:
    def __init__(self, formats):
        self._formats = formats

    def hasFormat(self, fmt):
        return fmt in self._formats

    def data(self, fmt):
        return _Payload(self._formats.get(fmt, b""))


def test_decode_mime_text_accepts_qbytearray_like_payload():
    assert decode_mime_text(_Mime({"text/plain": "中文".encode()}), "text/plain") == "中文"
    assert decode_mime_text(_Mime({}), "missing") == ""


def test_shortcut_ids_from_mime_prefers_batch_and_dedupes():
    mime = _Mime(
        {
            "application/x-shortcut-id": b"one",
            "application/x-shortcut-ids": b"one\ntwo\none\n",
        }
    )

    assert shortcut_ids_from_mime(mime) == ["one", "two"]


def test_shortcut_ids_from_mime_falls_back_to_single_id():
    assert shortcut_ids_from_mime(_Mime({"application/x-shortcut-id": b"solo"})) == ["solo"]
    assert shortcut_ids_from_mime(_Mime({})) == []


def test_folder_drop_policy_helpers():
    synced = SimpleNamespace(linked_path="G:/linked", auto_sync=True)
    unsynced = SimpleNamespace(linked_path="", auto_sync=True)
    icon_repo = SimpleNamespace(is_icon_repo=True)
    normal = SimpleNamespace(is_icon_repo=False)

    assert is_auto_sync_folder_locked(synced) is True
    assert is_auto_sync_folder_locked(unsynced) is False
    assert is_auto_sync_folder_locked(None) is False
    assert should_copy_shortcut_drop(icon_repo, normal) is True
    assert should_copy_shortcut_drop(normal, icon_repo) is True
    assert should_copy_shortcut_drop(normal, normal) is False


def test_move_folder_id_to_target_preserves_existing_panel_semantics():
    assert move_folder_id_to_target(["one", "two", "three"], "one", "three") == ["two", "three", "one"]
    assert move_folder_id_to_target(["one", "two", "three"], "three", "one") == ["three", "one", "two"]
    assert move_folder_id_to_target(["one", "two"], "one", "one") is None
    assert move_folder_id_to_target(["one", "two"], "missing", "two") is None
