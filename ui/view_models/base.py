"""Lightweight view-model base classes for the P1-06 UI refactor.

The classes defined here borrow the *spirit* of MVVM without pulling
in a third-party binding framework.  The concrete ``ViewModel``
subclasses are plain :class:`QObject` derivatives; the view layer
interacts with them through :func:`pyqtSignal` and
:func:`pyqtProperty` members so the existing :class:`pyqtSignal` /
:func:`pyqtSlot` test infrastructure continues to work.

The three public classes are:

* :class:`ViewModel` — base class.  Exposes a single
  :pyattr:`state_changed` signal plus an :func:`emit_state` helper.
* :class:`ListViewModel` — adds ``items_changed`` and the
  ``item_inserted`` / ``item_removed`` / ``item_updated`` signals used
  by lists in the chain canvas, icon grid and folder panel.
* :class:`DialogViewModel` — adds ``accepted`` / ``rejected`` /
  ``dirty_changed`` signals and ``commit`` / ``revert`` semantics
  used by every editor dialog (command / chain / macro / shortcut).
"""

from __future__ import annotations

from typing import Any

from qt_compat import QObject, pyqtSignal


class ViewModel(QObject):
    """Base class for the P1-06 view-model layer.

    The intent mirrors MVVM: the view subscribes to
    :pyattr:`state_changed` (and any domain-specific signal) and
    reads properties.  Direct mutation of the view-model is reserved
    for the presenter / service layer.
    """

    #: Emitted whenever the public state of the view-model changes.
    #: The optional ``payload`` argument is a dict snapshot of the
    #: changed fields; the view may use it to avoid recomputing
    #: fields that did not change.
    state_changed = pyqtSignal(object)

    #: Emitted when :pyattr:`is_dirty` flips.
    dirty_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dirty = False

    # ── state helpers ────────────────────────────────────────────────

    def emit_state(self, payload: dict[str, Any] | None = None) -> None:
        """Notify the view that the public state has changed."""
        self.state_changed.emit(payload)

    def is_dirty(self) -> bool:
        """Return ``True`` if the view-model has unsaved changes."""
        return self._dirty

    def set_dirty(self, value: bool) -> None:
        if value == self._dirty:
            return
        self._dirty = bool(value)
        self.dirty_changed.emit(self._dirty)
        self.emit_state({"dirty": self._dirty})

    # ── lifecycle ────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Release any resources held by the view-model.

        The default implementation is a no-op; subclasses that own
        background workers or cached state should override.
        """


class ListViewModel(ViewModel):
    """Base class for list-backed view-models.

    Subclasses expose a typed :pyattr:`items` accessor and call
    :func:`_notify_item_inserted` / :func:`_notify_item_removed` /
    :func:`_notify_item_updated` whenever the underlying collection
    changes so the view can sync without re-reading the whole list.
    """

    items_changed = pyqtSignal()
    item_inserted = pyqtSignal(int)
    item_removed = pyqtSignal(int)
    item_updated = pyqtSignal(int)

    def _notify_items_reset(self) -> None:
        self.items_changed.emit()
        self.emit_state({"items_reset": True})

    def _notify_item_inserted(self, index: int) -> None:
        self.item_inserted.emit(int(index))
        self.items_changed.emit()
        self.emit_state({"item_inserted": int(index)})

    def _notify_item_removed(self, index: int) -> None:
        self.item_removed.emit(int(index))
        self.items_changed.emit()
        self.emit_state({"item_removed": int(index)})

    def _notify_item_updated(self, index: int) -> None:
        self.item_updated.emit(int(index))
        self.items_changed.emit()
        self.emit_state({"item_updated": int(index)})


class DialogViewModel(ViewModel):
    """Base class for modal/dialog view-models.

    Tracks the ``dirty`` flag and provides explicit
    :func:`commit` / :func:`revert` hooks so dialogs can prompt for
    unsaved changes before closing.
    """

    accepted = pyqtSignal()
    rejected = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._committed = False
        self._reverted = False

    def commit(self) -> bool:
        """Persist pending changes to the underlying service.

        Subclasses should override this and return ``True`` on
        success.  The default implementation marks the dialog as
        committed and emits :pyattr:`accepted`.
        """
        self._committed = True
        self._reverted = False
        self.set_dirty(False)
        self.accepted.emit()
        return True

    def revert(self) -> bool:
        """Discard pending changes.

        Subclasses should override this and return ``True`` on
        success.  The default implementation marks the dialog as
        reverted and emits :pyattr:`rejected`.
        """
        self._reverted = True
        self._committed = False
        self.set_dirty(False)
        self.rejected.emit()
        return True

    def is_committed(self) -> bool:
        return self._committed

    def is_reverted(self) -> bool:
        return self._reverted


__all__ = [
    "DialogViewModel",
    "ListViewModel",
    "ViewModel",
]
