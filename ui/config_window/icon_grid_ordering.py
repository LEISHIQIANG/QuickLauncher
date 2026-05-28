"""Pure ordering helpers for the config icon grid."""

from collections.abc import Iterable, Sequence


def move_drag_group_order(
    current_ids: Sequence[str | None],
    source_id: str,
    target_id: str,
    drag_ids: Iterable[str],
) -> list[str | None] | None:
    ids = list(current_ids)
    id_to_index = {}
    for index, shortcut_id in enumerate(ids):
        if shortcut_id:
            id_to_index[shortcut_id] = index
    if target_id not in id_to_index:
        return None

    drag_id_set = set(drag_ids or [])
    ordered_ids = []
    seen = set()
    for shortcut_id in ids:
        if shortcut_id in drag_id_set and shortcut_id not in seen:
            ordered_ids.append(shortcut_id)
            seen.add(shortcut_id)
    if not ordered_ids or target_id in seen:
        return None

    source_idx = id_to_index.get(source_id, id_to_index[ordered_ids[0]])
    target_idx = id_to_index[target_id]
    moving_set = set(ordered_ids)
    moving_ids = [shortcut_id for shortcut_id in ids if shortcut_id in moving_set]
    remaining_ids = [shortcut_id for shortcut_id in ids if shortcut_id not in moving_set]
    target_pos = next((i for i, shortcut_id in enumerate(remaining_ids) if shortcut_id == target_id), -1)
    if target_pos < 0:
        return None

    insert_at = target_pos + 1 if source_idx < target_idx else target_pos
    new_ids = remaining_ids[:insert_at] + moving_ids + remaining_ids[insert_at:]
    if new_ids == ids:
        return None
    return new_ids
