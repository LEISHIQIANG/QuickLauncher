"""PopupCommandResultMixin — Phase 2: show command results inline in the popup."""

from __future__ import annotations

import logging
import os

from core.action_executor import ActionExecutionContext, execute_command_action
from core.command_action_safety import normalize_command_action, sanitize_command_actions
from core.command_registry import MAX_COMMAND_RESULT_ACTIONS
from qt_compat import (
    QApplication,
    QColor,
    QEvent,
    QFont,
    QImage,
    QKeySequence,
    QObject,
    QPainter,
    QPen,
    QRect,
    QRectF,
    Qt,
    QtCompat,
    QTextEdit,
    QTextOption,
)
from ui.styles.style import PopupMenu
from ui.utils.safe_file_dialog import get_save_file_name
from ui.utils.ui_scale import font_px, scale_qss, sp

logger = logging.getLogger(__name__)

_RESULT_PAD = 12
_ACTION_BTN_H = 18
_ACTION_BTN_GAP = 6
_CARD_RADIUS = 10
_CARD_MIN_H = 90
_CARD_PADDING_TOP = 6
_CARD_PADDING_LEFT = 10
_CARD_PADDING_RIGHT = 10
_CARD_MSG_MAX_H = 60
_CARD_MAX_H = 300
_CARD_BTN_AREA_H = 36
_EXPAND_BTN_H = 24


class TextEditKeyFilter(QObject):
    """Event filter to intercept keys on the selectable QTextEdit.

    Allows standard shortcuts (Ctrl+C, Ctrl+A) to propagate inside the QTextEdit,
    but forwards all other keyboard input (such as typing characters, Esc, Enter)
    directly to the launcher parent widget.
    """

    def __init__(self, parent_launcher):
        super().__init__(parent_launcher)
        self.launcher = parent_launcher

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            modifiers = event.modifiers()

            # Let standard text-editing/copying shortcuts work natively in QTextEdit
            if event.matches(QKeySequence.Copy) or (modifiers == Qt.ControlModifier and key == Qt.Key_C):
                return False
            if event.matches(QKeySequence.SelectAll) or (modifiers == Qt.ControlModifier and key == Qt.Key_A):
                return False

            # Keep modifier keys themselves from being forwarded to the parent launcher
            if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
                return False

            # Keep navigation keys inside the QTextEdit for scrolling and selection
            if key in (
                Qt.Key_Left,
                Qt.Key_Right,
                Qt.Key_Up,
                Qt.Key_Down,
                Qt.Key_Home,
                Qt.Key_End,
                Qt.Key_PageUp,
                Qt.Key_PageDown,
            ):
                return False

            # Forward all other keys to the launcher parent
            QApplication.sendEvent(self.launcher, event)
            return True
        return super().eventFilter(obj, event)


class CompactResultPopupMenu(PopupMenu):
    """Small PopupMenu variant sized for the command result panel."""

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(theme=theme, radius=sp(8), parent=parent)
        self._layout.setContentsMargins(sp(6), sp(6), sp(6), sp(6))
        self._layout.setSpacing(sp(2))
        self._btn_style_dark = scale_qss(
            "QPushButton{background:transparent;border:none;padding:5px 12px;margin:0px;"
            "border-radius:6px;color:rgba(255,255,255,0.86);font-size:10px;text-align:left;"
            "font-family:'Segoe UI','Microsoft YaHei UI',sans-serif;font-weight:400;}"
            "QPushButton:hover{background:rgba(255,255,255,0.11);color:rgba(255,255,255,0.96);}"
            "QPushButton:pressed{background:rgba(255,255,255,0.17);}"
            "QPushButton:disabled{color:rgba(255,255,255,95);}"
        )
        self._btn_style_light = scale_qss(
            "QPushButton{background:transparent;border:none;padding:5px 12px;margin:0px;"
            "border-radius:6px;color:rgba(28,28,30,0.86);font-size:10px;text-align:left;"
            "font-family:'Segoe UI','Microsoft YaHei UI',sans-serif;font-weight:400;}"
            "QPushButton:hover{background:rgba(0,0,0,0.07);color:rgba(28,28,30,0.96);}"
            "QPushButton:pressed{background:rgba(0,0,0,0.11);}"
            "QPushButton:disabled{color:rgba(60,60,67,105);}"
        )


class ResultTextEdit(QTextEdit):
    """Selectable result text with a compact app-styled context menu."""

    def __init__(self, launcher):
        super().__init__(launcher)
        self.launcher = launcher

    def contextMenuEvent(self, event):
        theme = "dark"
        try:
            theme = getattr(self.launcher.settings, "theme", "dark")
        except Exception as exc:
            logger.debug("获取主题设置失败: %s", exc, exc_info=True)

        has_text = bool(self.toPlainText())
        has_selection = self.textCursor().hasSelection()
        menu = CompactResultPopupMenu(theme=theme, parent=None)
        menu.add_action("复制", lambda: self.copy(), enabled=has_selection)
        menu.add_action("复制全部", lambda: QApplication.clipboard().setText(self.toPlainText()), enabled=has_text)
        menu.add_action("全选", lambda: self.selectAll(), enabled=has_text)
        menu.add_separator()
        menu.add_action("关闭面板", self._close_result_panel, enabled=True)
        menu.popup(event.globalPos())
        event.accept()

    def _close_result_panel(self):
        try:
            self.launcher.clear_command_result()
            if hasattr(self.launcher, "_set_search_query"):
                self.launcher._set_search_query("/")
        except Exception:
            logger.exception("Failed to close command result panel from context menu")


class PopupCommandResultMixin:
    """Mixin that adds command result display to LauncherPopup.

    Must appear BEFORE PopupRendererMixin in the MRO so paintEvent
    can be intercepted.  Provides helper methods; the actual
    _execute_item / keyPressEvent modifications are in popup_window.py.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._command_result = None
        self._command_id = ""
        self._result_expanded = False
        self._result_auto_pin_previous_state = None
        self._result_hover_button = None
        self._result_pressed_button = None

    # ------------------------------------------------------------------
    # Result management
    # ------------------------------------------------------------------

    def _ensure_text_edit(self):
        """Safely ensure the QTextEdit child widget is created and styled."""
        try:
            # Test if QWidget APIs like parent() can be called safely (safety check for mocks)
            self.parent()
        except RuntimeError:
            return None
        except Exception:
            return None

        # Double check that we are not in a lightweight mock
        if self.__dict__.get("_command_result") is None:
            return None

        if not hasattr(self, "_result_text_edit") or self._result_text_edit is None:
            try:
                self._result_text_edit = ResultTextEdit(self)
                self._result_text_edit.setReadOnly(True)
                self._result_text_edit.setFrameStyle(0)  # NoFrame
                self._result_text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                self._result_text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                self._result_text_edit.setLineWrapMode(QTextEdit.WidgetWidth)
                self._result_text_edit.setWordWrapMode(QTextOption.WrapAnywhere)
                self._result_text_edit.setFocusPolicy(Qt.ClickFocus)

                # Install custom key filter
                self._key_filter = TextEditKeyFilter(self)
                self._result_text_edit.installEventFilter(self._key_filter)

                # Apply elegant stylesheet for seamless transparent look
                self._result_text_edit.setStyleSheet(
                    "QTextEdit {  background-color: transparent;  border: none;  padding: 0px;  margin: 0px;}"
                )
            except Exception as e:
                logger.warning("Failed to initialize result QTextEdit: %s", e)
                self._result_text_edit = None

        return self._result_text_edit

    def _update_text_edit_geometry(self):
        """Position the transparent QTextEdit perfectly over the text region."""
        te = self._ensure_text_edit()
        if te is None:
            return

        result = self._command_result
        if result is None:
            te.hide()
            return

        card_rect = self._result_card_rect()
        if card_rect.isNull():
            te.hide()
            return

        # Calculate coordinates dynamically using the exact same logic as paintEvent
        card_x = card_rect.left()
        card_y = card_rect.top()
        card_w = card_rect.width()
        card_h = card_rect.height()

        table_top = card_y + sp(16)
        if result.display_type == "table":
            rows = result.payload.get("rows", [])
            if rows:
                row_h = sp(22)
                table_top += min(len(rows), 6) * row_h + sp(8)

        msg_y = table_top
        # Always reserve space for bottom button area (since Close button is always present)
        btn_h = sp(_ACTION_BTN_H) + sp(8)
        msg_max_h = card_h - (msg_y - card_y) - btn_h - sp(6)
        if msg_max_h < sp(30):
            msg_max_h = sp(60)

        padding_left = sp(6)
        padding_right = 0

        msg_rect = QRect(card_x + padding_left, msg_y, card_w - padding_left - padding_right, msg_max_h)

        te.setGeometry(msg_rect)

        # Style the text color dynamically matching the current theme
        try:
            _, text_color, _, _, accent_color, _, _ = self._get_theme_colors()
            text_color_hex = text_color.name()
            is_dark = getattr(self.settings, "theme", "dark") == "dark"
            scrollbar_handle_color = "rgba(255, 255, 255, 60)" if is_dark else "rgba(0, 0, 0, 40)"

            import os

            font_family = "Microsoft YaHei" if os.name == "nt" else "Segoe UI"
            _te_font = QFont(font_family)
            _te_font.setPixelSize(font_px(12))
            te.setFont(_te_font)
            te.setStyleSheet(
                f"QTextEdit {{"
                f"  background-color: transparent;"
                f"  border: none;"
                f"  color: {text_color_hex};"
                f"  padding-left: 0px;"
                f"  padding-right: 0px;"
                f"  padding-top: 0px;"
                f"  padding-bottom: 0px;"
                f"  margin: 0px;"
                f"}}"
            )

            try:
                te.document().setDocumentMargin(0)
                fmt = te.document().rootFrame().frameFormat()
                fmt.setLeftMargin(0)
                fmt.setRightMargin(sp(12))
                fmt.setTopMargin(0)
                fmt.setBottomMargin(0)
                te.document().rootFrame().setFrameFormat(fmt)
            except Exception as exc:
                logger.debug("设置文档框架格式失败: %s", exc, exc_info=True)

            # Apply styling directly to the vertical scrollbar child widget for bulletproof styling propagation
            te.verticalScrollBar().setStyleSheet(
                scale_qss(
                    f"QScrollBar:vertical {{"
                    f"  border: none;"
                    f"  background: transparent;"
                    f"  width: 3px;"
                    f"  margin: 0px;"
                    f"}}"
                    f"QScrollBar::handle:vertical {{"
                    f"  background: {scrollbar_handle_color};"
                    f"  min-height: 12px;"
                    f"  border-radius: 1px;"
                    f"}}"
                    f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{"
                    f"  border: none;"
                    f"  background: none;"
                    f"  height: 0px;"
                    f"}}"
                    f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{"
                    f"  background: none;"
                    f"}}"
                )
            )
        except Exception as exc:
            logger.debug("设置滚动条样式失败: %s", exc, exc_info=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_text_edit_geometry()

    def show_command_result(self, result, command_id=""):
        if result is None:
            self.clear_command_result()
            return

        had_result = self.__dict__.get("_command_result") is not None
        try:
            result.actions = sanitize_command_actions(getattr(result, "actions", []))
        except Exception:
            logger.debug("sanitize command result actions failed", exc_info=True)
        self._command_result = result
        self._command_id = command_id

        # 结果面板显示期间临时固定窗口，关闭面板时恢复进入前的固定状态。
        if not had_result and self.__dict__.get("_result_auto_pin_previous_state") is None:
            self._result_auto_pin_previous_state = bool(getattr(self, "is_pinned", False))
        self.is_pinned = True
        if hasattr(self, "_hide_timer") and self._hide_timer.isActive():
            self._hide_timer.stop()

        # Show and set text
        te = self._ensure_text_edit()
        if te is not None:
            if result.display_type == "qr":
                te.hide()
            else:
                msg = result.message or result.error or "完成"
                te.setFocusPolicy(Qt.StrongFocus)
                te.setPlainText(msg)
                te.show()
                te.setFocus()
                self._update_text_edit_geometry()
        self.update()

    def toggle_result_panel_post_close_pin(self) -> bool:
        """Toggle the pin state that will be restored after the result panel closes."""
        if self.__dict__.get("_command_result") is None:
            return False
        previous_pin_state = self.__dict__.get("_result_auto_pin_previous_state", None)
        if previous_pin_state is None:
            return False
        self._result_auto_pin_previous_state = not bool(previous_pin_state)
        self.is_pinned = True
        hide_timer = self.__dict__.get("_hide_timer")
        try:
            if hide_timer is not None and hide_timer.isActive():
                hide_timer.stop()
        except Exception as exc:
            logger.debug("停止隐藏定时器失败: %s", exc, exc_info=True)
        try:
            self.update()
        except Exception as exc:
            logger.debug("更新窗口失败: %s", exc, exc_info=True)
        return True

    def clear_command_result(self):
        self._command_result = None
        self._command_id = ""
        previous_pin_state = self.__dict__.get("_result_auto_pin_previous_state", None)
        if previous_pin_state is not None:
            self.is_pinned = bool(previous_pin_state)
            self._result_auto_pin_previous_state = None
        result_text_edit = self.__dict__.get("_result_text_edit")
        if result_text_edit is not None:
            try:
                result_text_edit.hide()
            except Exception as exc:
                logger.debug("隐藏结果文本框失败: %s", exc, exc_info=True)
        try:
            self.setFocus()
        except Exception as exc:
            logger.debug("设置焦点失败: %s", exc, exc_info=True)
        self.update()

    def has_command_result(self):
        return self.__dict__.get("_command_result") is not None

    # ------------------------------------------------------------------
    # paintEvent — draw result card on top of everything
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._command_result is None:
            return
        planner = QPainter(self)
        planner.setRenderHint(QPainter.Antialiasing)
        planner.setRenderHint(QtCompat.HighQualityAntialiasing)
        planner.setRenderHint(QPainter.TextAntialiasing)
        try:
            _, text_color, _, _, accent_color, _, _ = self._get_theme_colors()
            self._draw_command_result(planner, text_color, accent_color)
        except Exception:
            logger.exception("Error drawing command result")
        finally:
            planner.end()

    # ------------------------------------------------------------------
    # Mouse click handling for action buttons
    # ------------------------------------------------------------------

    def _result_card_rect(self):
        """Compute the card bounding rect for hit-testing."""
        if self._command_result is None:
            return QRect()
        y_top = self._body_y_offset() if hasattr(self, "_body_y_offset") else sp(38)
        y_bottom = getattr(self, "dock_y", self.height() - sp(6))
        panel_h = y_bottom - y_top
        card_x = sp(_RESULT_PAD)
        card_y = y_top + sp(8)
        card_w = self.width() - sp(_RESULT_PAD) * 2
        card_h = panel_h - sp(16)
        return QRect(card_x, card_y, card_w, card_h)

    def _close_button_rect(self):
        """Return the QRect of the bottom-right close button."""
        card_rect = self._result_card_rect()
        if card_rect.isNull():
            return QRect()

        font_family = "Microsoft YaHei" if os.name == "nt" else "Segoe UI"
        font = QFont(font_family)
        font.setPixelSize(font_px(11))
        from qt_compat import QFontMetrics

        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance("关闭") if hasattr(fm, "horizontalAdvance") else fm.width("关闭")
        close_w = max(sp(40), text_w + sp(12))
        return QRect(
            card_rect.right() - sp(6) - close_w,
            card_rect.bottom() - sp(_ACTION_BTN_H) - sp(6),
            close_w,
            sp(_ACTION_BTN_H),
        )

    def _action_button_rects(self):
        """Return list of (QRect, action_index) for each action button."""
        result = self.__dict__.get("_command_result")
        if not result or not result.actions:
            return []
        card_rect = self._result_card_rect()
        if card_rect.isNull():
            return []

        btn_y = card_rect.bottom() - sp(_ACTION_BTN_H) - sp(6)
        rects = []

        # Get font metrics to calculate dynamic button width

        font_family = "Microsoft YaHei" if os.name == "nt" else "Segoe UI"
        font = QFont(font_family)
        font.setPixelSize(font_px(11))
        from qt_compat import QFontMetrics

        fm = QFontMetrics(font)

        current_x = card_rect.left() + sp(6)
        for i, action in enumerate(result.actions[:MAX_COMMAND_RESULT_ACTIONS]):
            label = action.label or action.type
            if label == "copy":
                label = "复制"
            elif label == "open_url":
                label = "打开链接"
            elif label == "open_file":
                label = "打开文件"
            elif label == "open_folder":
                label = "打开文件夹"
            elif label == "save_text":
                label = "保存文本"
            elif label == "save_file":
                label = "保存图片"
            elif label == "create_shortcut":
                label = "创建快捷方式"

            text_w = fm.horizontalAdvance(label) if hasattr(fm, "horizontalAdvance") else fm.width(label)
            btn_w = max(sp(40), text_w + sp(12))
            rects.append((QRect(current_x, btn_y, btn_w, sp(_ACTION_BTN_H)), i))
            current_x += btn_w + sp(_ACTION_BTN_GAP)

        return rects

    def _expand_btn_rect(self):
        """Return the expand/collapse button rect at bottom of card."""
        return QRect()  # 固定尺寸后，无需折叠/展开按钮

    def _result_button_at(self, pos):
        """Return the interactive bottom button under pos, if any."""
        if self.__dict__.get("_command_result") is None:
            return None

        close_rect = self._close_button_rect()
        if not close_rect.isNull() and close_rect.contains(pos):
            return ("close", -1)

        for btn_rect, idx in self._action_button_rects():
            if btn_rect.contains(pos):
                return ("action", idx)

        return None

    def update_result_button_hover(self, pos):
        """Update hover feedback for hand-drawn result panel buttons."""
        hover = self._result_button_at(pos)
        if self.__dict__.get("_result_hover_button") != hover:
            self._result_hover_button = hover
            self.update()

        try:
            self.setCursor(Qt.PointingHandCursor if hover is not None else QtCompat.ArrowCursor)
        except Exception as exc:
            logger.debug("设置光标失败: %s", exc, exc_info=True)
        return hover

    def clear_result_button_feedback(self):
        """Clear transient hover/pressed feedback."""
        if (
            self.__dict__.get("_result_hover_button") is not None
            or self.__dict__.get("_result_pressed_button") is not None
        ):
            self._result_hover_button = None
            self._result_pressed_button = None
            self.update()

    def mousePressEvent(self, event):
        if self._command_result is not None and event.button() == Qt.LeftButton:
            pos = event.pos()
            expand_rect = self._expand_btn_rect()
            if not expand_rect.isNull() and expand_rect.contains(pos):
                self._result_expanded = not self._result_expanded
                self.update()
                event.accept()
                return

            # Check "关闭" (Close) button click in bottom right corner
            button = self._result_button_at(pos)
            if button is not None:
                self._result_pressed_button = button
                self._result_hover_button = button
                self.update()
                event.accept()
                return
            # Star toggle
            if self._command_id:
                card_rect = self._result_card_rect()
                star_rect = self._star_rect(card_rect)
                if star_rect.contains(pos):
                    self._toggle_favorite()
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.__dict__.get("_command_result") is not None and event.button() == Qt.LeftButton:
            pos = event.pos()
            pressed = self.__dict__.get("_result_pressed_button")
            released = self._result_button_at(pos)
            self._result_pressed_button = None
            self._result_hover_button = released

            if pressed is not None:
                if pressed == released:
                    kind, idx = pressed
                    if kind == "close":
                        self.clear_command_result()
                        if hasattr(self, "_set_search_query"):
                            self._set_search_query("/")
                    elif kind == "action":
                        result = self.__dict__.get("_command_result")
                        if result is not None and 0 <= idx < len(result.actions):
                            self._execute_action(result.actions[idx])
                self.update()
                event.accept()
                return

        super().mouseReleaseEvent(event)

    def _toggle_favorite(self):
        """Toggle the current command's favorite status."""
        cid = self._command_id
        if not cid:
            return
        try:
            from core import data_manager

            if data_manager is None:
                return
            settings = data_manager.get_settings()
            if cid in settings.favorite_commands:
                settings.favorite_commands.remove(cid)
            else:
                settings.favorite_commands.append(cid)
            data_manager.save()
            self.update()
        except Exception as e:
            logger.warning("切换收藏失败: %s", e)

    def _execute_action(self, action):
        action = normalize_command_action(action)
        if action is None:
            return
        ok = execute_command_action(
            action,
            ActionExecutionContext(
                source=str(getattr(self, "_command_id", "") or "launcher_popup"),
                parent=self,
                set_clipboard_text=QApplication.clipboard().setText,
                save_file_dialog=get_save_file_name,
            ),
        )
        if ok and action.type not in {"copy", "copy_table", "copy_json"}:
            self.clear_command_result()

    # ------------------------------------------------------------------
    # Result card rendering
    # ------------------------------------------------------------------

    def _is_favorited(self) -> bool:
        """Check if the current command ID is in favorites."""
        if not self._command_id:
            return False
        try:
            from core import data_manager

            if data_manager is not None:
                return self._command_id in data_manager.get_settings().favorite_commands
        except Exception as exc:
            logger.debug("检查收藏状态失败: %s", exc, exc_info=True)
        return False

    def _star_rect(self, card_rect):
        """Return the star button rect in the top-right of the card."""
        return QRect()

    def _card_height(self):
        """Dynamic card height based on message length, capped at _CARD_MAX_H."""
        card_rect = self._result_card_rect()
        return card_rect.height() if not card_rect.isNull() else 0

    def _draw_command_result(self, painter, text_color, accent_color):
        result = self._command_result
        if result is None:
            return

        w = self.width()
        y_top = self._body_y_offset() if hasattr(self, "_body_y_offset") else sp(38)
        y_bottom = getattr(self, "dock_y", self.height() - sp(6))
        panel_h = y_bottom - y_top

        card_rect = self._result_card_rect()
        if card_rect.isNull():
            return
        card_x = card_rect.left()
        card_y = card_rect.top()
        card_w = card_rect.width()
        card_h = card_rect.height()

        is_dark = getattr(self.settings, "theme", "dark") == "dark"

        # Semi-transparent overlay covering the entire icon grid area, excluding the dock
        overlay = QColor(20, 20, 22, 230) if is_dark else QColor(240, 240, 243, 240)
        painter.fillRect(QRect(0, y_top, w, panel_h), overlay)

        # Card background with elegant fine border
        card_color = QColor(accent_color)
        card_color.setAlpha(35 if is_dark else 20)
        painter.setBrush(card_color)

        border_pen = QPen(
            QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 60 if is_dark else 40), 1
        )
        painter.setPen(border_pen)
        painter.drawRoundedRect(QRectF(card_x, card_y, card_w, card_h), sp(_CARD_RADIUS), sp(_CARD_RADIUS))

        # Color swatch (payload.color_hex)
        color_hex = result.payload.get("color_hex", "")
        if color_hex:
            try:
                swatch_color = QColor(color_hex)
                if swatch_color.isValid():
                    swatch_rect = QRect(card_x + sp(16), card_y + sp(16), sp(32), sp(32))
                    painter.setBrush(swatch_color)
                    painter.setPen(QtCompat.NoPen)
                    painter.drawRoundedRect(QRectF(swatch_rect), sp(6), sp(6))
            except Exception as exc:
                logger.debug("绘制颜色色块失败: %s", exc, exc_info=True)

        # Table display
        table_top = card_y + sp(16)
        if result.display_type == "table":
            rows = result.payload.get("rows", [])
            if rows:
                _tbl_font = QFont("Segoe UI")
                _tbl_font.setPixelSize(font_px(13))
                painter.setFont(_tbl_font)
                painter.setPen(text_color)
                row_h = sp(22)
                col_x = card_x + sp(56)
                for ri, row in enumerate(rows[:6]):
                    cells = row if isinstance(row, list) else [str(row)]
                    for ci, cell in enumerate(cells):
                        cell_text = str(cell)
                        painter.drawText(
                            QRect(col_x + ci * sp(120), table_top + ri * row_h, sp(120), row_h),
                            Qt.AlignLeft | Qt.AlignVCenter,
                            cell_text,
                        )
                table_top += min(len(rows), 6) * row_h + sp(8)

        # Message text Y position and layout
        msg_y = table_top
        btn_h = sp(_ACTION_BTN_H) + sp(8)

        # Calculate dynamic maximum height inside our generous fixed container
        msg_max_h = card_h - (msg_y - card_y) - btn_h - sp(6)
        if msg_max_h < sp(30):
            msg_max_h = sp(60)  # fallback to standard size if layout squeezed

        # Message text fallback (e.g. for mock tests where QTextEdit cannot be instantiated)
        te = self._ensure_text_edit()
        if te is None:
            import os

            font_family = "Microsoft YaHei" if os.name == "nt" else "Segoe UI"
            _msg_font = QFont(font_family)
            _msg_font.setPixelSize(font_px(13))
            painter.setFont(_msg_font)
            painter.setPen(text_color)
            msg = result.message or result.error or "完成"

            _CARD_PADDING_LEFT = sp(6)
            _CARD_PADDING_RIGHT = sp(6)

            msg_rect = QRect(
                card_x + _CARD_PADDING_LEFT, msg_y, card_w - _CARD_PADDING_LEFT - _CARD_PADDING_RIGHT, msg_max_h
            )
            painter.drawText(msg_rect, Qt.AlignLeft | Qt.TextWordWrap, msg)

        # Progress bar (display_type == "progress" or is_async)
        if result.is_async and result.progress > 0:
            bar_y = msg_y + sp(40)
            bar_h = sp(6)
            _CARD_PADDING_LEFT = sp(8)
            _CARD_PADDING_RIGHT = sp(8)
            bar_w = card_w - _CARD_PADDING_LEFT - _CARD_PADDING_RIGHT
            bar_x = card_x + _CARD_PADDING_LEFT
            # Track background
            painter.setBrush(QColor(255, 255, 255, 20 if is_dark else 40))
            painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), sp(3), sp(3))
            # Fill
            fill = int(bar_w * min(result.progress, 1.0))
            if fill > sp(4):
                painter.setBrush(QColor(accent_color))
                painter.drawRoundedRect(QRectF(bar_x, bar_y, fill, bar_h), sp(3), sp(3))

        # QR text (painted directly since QTextEdit is hidden for QR mode)
        if result.display_type == "qr":
            import os

            font_family = "Microsoft YaHei" if os.name == "nt" else "Segoe UI"
            _qr_font = QFont(font_family)
            _qr_font.setPixelSize(font_px(13))
            painter.setFont(_qr_font)
            painter.setPen(text_color)
            _CARD_PADDING_LEFT = sp(6)
            _CARD_PADDING_RIGHT = sp(6)
            qr_msg = result.message or result.error or "完成"
            qr_msg_rect = QRect(
                card_x + _CARD_PADDING_LEFT, msg_y, card_w - _CARD_PADDING_LEFT - _CARD_PADDING_RIGHT, msg_max_h
            )
            painter.drawText(qr_msg_rect, Qt.AlignLeft | Qt.TextWordWrap, qr_msg)

        # QR image (display_type == "qr") — drawn after text, on top
        if result.display_type == "qr" and result.payload.get("image_path"):
            qr_path = result.payload["image_path"]
            qr_img = QImage(qr_path)
            if not qr_img.isNull():
                qr_size = min(sp(120), card_h - sp(32))
                qr_x = card_x + (card_w - qr_size) // 2
                qr_y = card_y + (card_h - qr_size) // 2
                qr_scaled = qr_img.scaled(qr_size, qr_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                painter.drawImage(qr_x, qr_y, qr_scaled)

        # Action buttons
        if result.actions:
            btn_rects = self._action_button_rects()
            for btn_rect, idx in btn_rects:
                action = result.actions[idx]
                button_id = ("action", idx)
                is_hovered = self.__dict__.get("_result_hover_button") == button_id
                is_pressed = self.__dict__.get("_result_pressed_button") == button_id
                draw_rect = QRect(btn_rect)
                if is_pressed:
                    draw_rect.translate(1, 1)

                # Exquisite glassmorphic button background
                bg_alpha = 30 if is_dark else 15
                if is_hovered:
                    bg_alpha = 72 if is_dark else 34
                if is_pressed:
                    bg_alpha = 105 if is_dark else 50
                btn_bg = QColor(accent_color.red(), accent_color.green(), accent_color.blue(), bg_alpha)
                painter.setBrush(btn_bg)

                # Exquisite border styling for extreme crispness
                border_alpha = 90 if is_dark else 60
                if is_hovered:
                    border_alpha = 140 if is_dark else 95
                if is_pressed:
                    border_alpha = 170 if is_dark else 120
                border_pen = QPen(
                    QColor(accent_color.red(), accent_color.green(), accent_color.blue(), border_alpha), 1
                )
                painter.setPen(border_pen)
                painter.drawRoundedRect(QRectF(draw_rect), sp(5), sp(5))

                # Exquisite text color and modern font selection
                btn_text_color = QColor(255, 255, 255, 220) if is_dark else QColor(accent_color).darker(150)
                if is_hovered or is_pressed:
                    btn_text_color = QColor(255, 255, 255, 245) if is_dark else QColor(accent_color).darker(175)
                painter.setPen(btn_text_color)

                import os

                font_family = "Microsoft YaHei" if os.name == "nt" else "Segoe UI"
                font = QFont(font_family)
                font.setPixelSize(font_px(11))
                painter.setFont(font)

                # Friendly localizations
                label = action.label or action.type
                if label == "copy":
                    label = "复制"
                elif label == "open_url":
                    label = "打开链接"
                elif label == "open_file":
                    label = "打开文件"
                elif label == "open_folder":
                    label = "打开文件夹"
                elif label == "save_text":
                    label = "保存文本"
                elif label == "create_shortcut":
                    label = "创建快捷方式"

                painter.drawText(draw_rect, Qt.AlignCenter, label)

        # Close button in bottom-right corner
        close_rect = self._close_button_rect()

        # Soft highlighted styling for close button
        close_id = ("close", -1)
        close_hovered = self.__dict__.get("_result_hover_button") == close_id
        close_pressed = self.__dict__.get("_result_pressed_button") == close_id
        close_draw_rect = QRect(close_rect)
        if close_pressed:
            close_draw_rect.translate(1, 1)
        close_alpha = 40 if is_dark else 15
        if close_hovered:
            close_alpha = 70 if is_dark else 28
        if close_pressed:
            close_alpha = 95 if is_dark else 42
        close_color = QColor(0, 0, 0, close_alpha)
        painter.setBrush(close_color)
        close_border_alpha = 60 if is_dark else 40
        if close_hovered:
            close_border_alpha = 115 if is_dark else 80
        if close_pressed:
            close_border_alpha = 150 if is_dark else 105
        close_border_pen = QPen(QColor(text_color.red(), text_color.green(), text_color.blue(), close_border_alpha), 1)
        close_border_pen.setStyle(Qt.SolidLine)
        painter.setPen(close_border_pen)
        painter.drawRoundedRect(QRectF(close_draw_rect), sp(5), sp(5))

        close_text_color = QColor(text_color)
        if close_hovered or close_pressed:
            close_text_color.setAlpha(255)
        painter.setPen(close_text_color)
        import os

        font_family = "Microsoft YaHei" if os.name == "nt" else "Segoe UI"
        font = QFont(font_family)
        font.setPixelSize(font_px(11))
        painter.setFont(font)
        painter.drawText(close_rect, Qt.AlignCenter, "关闭")

        # Error line below card (draw inside the card bottom area nicely)
        if result.error:
            import os

            font_family = "Microsoft YaHei" if os.name == "nt" else "Segoe UI"
            error_font = QFont(font_family)
            error_font.setPixelSize(font_px(11))
            painter.setFont(error_font)
            painter.setPen(QColor("#f44336"))
            painter.drawText(
                QRect(
                    card_x + sp(8),
                    card_y + card_h - sp(36) if result.actions else card_y + card_h - sp(18),
                    card_w - sp(16),
                    sp(14),
                ),
                Qt.AlignLeft,
                result.error,
            )
