"""InteractionContext — unified context for popup, commands, plugins, and action suggestions.

Captures a snapshot of the interaction environment at trigger time:
  - TriggerContext: how/when/where the popup was triggered
  - Clipboard: current clipboard content and classification
  - Selected text: text selected in the foreground window
  - Selected files: files selected in Explorer (from existing logic)

Usage:
    context = InteractionContext.capture()
    # or build step by step
    ctx = InteractionContext(trigger=trigger_ctx)
    ctx = ctx.with_clipboard(snapshot, classification)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .clipboard_service import ClipboardClassification, ClipboardSnapshot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ── TriggerContext ────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@dataclass
class TriggerContext:
    trigger_method: str = "unknown"
    trigger_pos: tuple[int, int] | None = None
    foreground_hwnd: int = 0
    foreground_root_hwnd: int = 0
    process_id: int = 0
    process_name: str = ""
    window_title: str = ""
    captured_at: float = 0.0

    @classmethod
    def capture_current(cls) -> TriggerContext:
        """Capture current trigger context from the environment."""
        captured_at = time.time()
        hwnd = 0
        root_hwnd = 0
        process_id = 0
        process_name = ""
        window_title = ""
        mouse_pos = None

        if os.name == "nt":
            try:
                import ctypes

                user32 = ctypes.windll.user32

                # Get foreground window
                hwnd = user32.GetForegroundWindow()
                if hwnd:
                    root_hwnd = user32.GetAncestor(hwnd, 2)  # GA_ROOT = 2

                    # Get window title
                    buf = ctypes.create_unicode_buffer(256)
                    user32.GetWindowTextW(hwnd, buf, 256)
                    window_title = buf.value or ""

                    # Get process ID and name
                    process_id = ctypes.wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
                    pid = process_id.value

                    if pid:
                        try:
                            import psutil

                            try:
                                proc = psutil.Process(pid)
                                process_name = proc.name() or ""
                            except Exception as exc:
                                logger.debug("通过psutil获取进程名失败: %s", exc, exc_info=True)
                        except ImportError:
                            logger.debug("psutil模块不可用", exc_info=True)
                        if not process_name:
                            try:
                                kernel32 = ctypes.windll.kernel32
                                handle = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
                                if handle:
                                    try:
                                        exe_buf = ctypes.create_unicode_buffer(260)
                                        size = ctypes.wintypes.DWORD(260)
                                        # Use QueryFullProcessImageNameW
                                        kernel32.QueryFullProcessImageNameW(handle, 0, exe_buf, ctypes.byref(size))
                                        process_name = os.path.basename(exe_buf.value or "")
                                    except Exception as exc:
                                        logger.debug("通过Windows API获取进程名失败: %s", exc, exc_info=True)
                                    finally:
                                        kernel32.CloseHandle(handle)
                            except Exception as exc:
                                logger.debug("打开进程句柄失败: %s", exc, exc_info=True)

                # Get mouse position
                pt = ctypes.wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                mouse_pos = (pt.x, pt.y)

            except Exception as e:
                logger.debug("TriggerContext.capture failed: %s", e)

        return cls(
            trigger_method="hotkey",
            trigger_pos=mouse_pos,
            foreground_hwnd=hwnd,
            foreground_root_hwnd=root_hwnd,
            process_id=process_id,
            process_name=process_name,
            window_title=window_title,
            captured_at=captured_at,
        )


# ---------------------------------------------------------------------------
# ── InteractionContext ────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@dataclass
class InteractionContext:
    trigger: TriggerContext | None = None
    clipboard: ClipboardSnapshot | None = None
    clipboard_classification: ClipboardClassification | None = None
    selected_text: SelectedTextResult | None = None  # noqa: F821
    selected_files: list[str] = field(default_factory=list)
    selected_files_status: str = "idle"

    # Backward-compatible properties
    @property
    def clipboard_text(self) -> str:
        return self.clipboard.text if self.clipboard else ""

    @property
    def clipboard_kind(self) -> str:
        if self.clipboard_classification:
            return self.clipboard_classification.kind
        return ""

    @property
    def selected_text_text(self) -> str:
        return self.selected_text.text if self.selected_text else ""

    # ---- factory ----

    @classmethod
    def capture(
        cls,
        *,
        with_clipboard: bool = True,
        with_classification: bool = True,
        with_selected_text: bool = False,
        with_selected_files: bool = False,
    ) -> InteractionContext:
        """Capture a full interaction context synchronously.

        Args:
            with_clipboard: Read clipboard snapshot.
            with_classification: Classify clipboard content.
            with_selected_text: Read selected text (may use clipboard fallback).
            with_selected_files: Read selected files from Explorer.

        Returns:
            Filled InteractionContext.
        """
        trigger = TriggerContext.capture_current()
        ctx = cls(trigger=trigger)

        if with_clipboard:
            try:
                from .clipboard_service import clipboard_service

                ctx.clipboard = clipboard_service.read_snapshot()
            except Exception as e:
                logger.debug("clipboard capture failed: %s", e)

        if with_classification and ctx.clipboard:
            try:
                from .clipboard_classifiers import classify_clipboard

                ctx.clipboard_classification = classify_clipboard(ctx.clipboard)
            except Exception as e:
                logger.debug("clipboard classification failed: %s", e)

        if with_selected_files:
            try:
                from core.file_selection import get_selected_files_for_process

                files = get_selected_files_for_process() or []
                ctx.selected_files = list(files)
                ctx.selected_files_status = "loaded" if files else "empty"
            except Exception as e:
                logger.debug("selected files capture failed: %s", e)
                ctx.selected_files_status = "error"

        if with_selected_text:
            try:
                from .selected_text_service import selected_text_service

                ctx.selected_text = selected_text_service.get_selected_text(
                    foreground_hwnd=trigger.foreground_hwnd if trigger else None,
                    foreground_process_name=trigger.process_name if trigger else "",
                    allow_clipboard_fallback=True,
                )
            except Exception as e:
                logger.debug("selected text capture failed: %s", e)

        return ctx

    def to_dict(self) -> dict:
        """Serialize to dict for plugin API or logging (no full clipboard text in logs)."""
        return {
            "trigger_method": self.trigger.trigger_method if self.trigger else "",
            "trigger_pos": self.trigger.trigger_pos if self.trigger else None,
            "foreground_process": self.trigger.process_name if self.trigger else "",
            "foreground_window": self.trigger.window_title if self.trigger else "",
            "clipboard_kind": self.clipboard_kind,
            "clipboard_size": len(self.clipboard_text) if self.clipboard_text else 0,
            "has_clipboard_files": bool(self.clipboard and self.clipboard.file_paths),
            "has_clipboard_image": bool(self.clipboard and self.clipboard.has_image),
            "selected_text_length": len(self.selected_text_text) if self.selected_text_text else 0,
            "selected_text_method": self.selected_text.method if self.selected_text else "",
            "selected_files_count": len(self.selected_files),
            "selected_files_status": self.selected_files_status,
        }

    def to_context_meta(self) -> dict:
        """Build context_meta dict for CommandContext."""
        meta = self.to_dict()
        meta.pop("trigger_pos", None)
        return meta
