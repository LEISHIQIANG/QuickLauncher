"""Pure helpers for folder panel drag/drop behavior."""


def decode_mime_text(mime_data, fmt: str) -> str:
    try:
        payload = mime_data.data(fmt)
        if hasattr(payload, "data"):
            payload = payload.data()
        return bytes(payload).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def shortcut_ids_from_mime(mime_data) -> list[str]:
    raw_ids = ""
    try:
        if mime_data.hasFormat("application/x-shortcut-ids"):
            raw_ids = decode_mime_text(mime_data, "application/x-shortcut-ids")
    except Exception:
        raw_ids = ""

    ids = [sid.strip() for sid in raw_ids.splitlines() if sid.strip()]
    if not ids:
        try:
            if mime_data.hasFormat("application/x-shortcut-id"):
                single_id = decode_mime_text(mime_data, "application/x-shortcut-id").strip()
                if single_id:
                    ids = [single_id]
        except Exception:
            ids = []

    deduped = []
    seen = set()
    for shortcut_id in ids:
        if shortcut_id in seen:
            continue
        seen.add(shortcut_id)
        deduped.append(shortcut_id)
    return deduped


def is_auto_sync_folder_locked(folder) -> bool:
    return bool(folder and getattr(folder, "linked_path", "") and getattr(folder, "auto_sync", False))


def should_copy_shortcut_drop(target_folder, source_folder=None) -> bool:
    return bool(getattr(target_folder, "is_icon_repo", False) or getattr(source_folder, "is_icon_repo", False))


def move_folder_id_to_target(folder_ids: list[str], source_id: str, target_id: str) -> list[str] | None:
    if source_id == target_id:
        return None
    ids = list(folder_ids)
    try:
        source_index = ids.index(source_id)
        target_index = ids.index(target_id)
    except ValueError:
        return None
    ids.pop(source_index)
    ids.insert(target_index, source_id)
    if ids == list(folder_ids):
        return None
    return ids
