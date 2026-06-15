"""
统一样式模块
提供统一的 UI 样式、颜色常量和组件

此模块整合了原本分散在 folder_panel.py 和 icon_grid.py 中的 PopupMenu 类，
以及统一的颜色方案和样式表生成器。
"""

import logging

from qt_compat import (
    QApplication,
    QColor,
    QCursor,
    QEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPoint,
    QPushButton,
    QRectF,
    Qt,
    QtCompat,
    QTimer,
    QVBoxLayout,
    QWidget,
)
from ui.styles.window_chrome import apply_custom_window_chrome
from ui.utils.ui_scale import get_scale_percent, scale_qss, sp
from ui.utils.window_effect import paint_win10_rounded_surface

logger = logging.getLogger(__name__)


class Colors:
    """
    设计规范颜色常量
    """

    # 系统蓝色
    BLUE = "#007AFF"
    BLUE_LIGHT = "#0A84FF"

    # 系统绿色
    # 系统绿色 (改为青色)
    GREEN = "#30B0C7"
    GREEN_LIGHT = "#40C8E0"

    # 系统红色
    RED = "#FF3B30"
    RED_LIGHT = "#FF453A"

    # 系统灰色
    GRAY = "#8E8E93"
    GRAY2 = "#636366"
    GRAY3 = "#48484A"
    GRAY4 = "#3A3A3C"
    GRAY5 = "#2C2C2E"
    GRAY6 = "#1C1C1E"

    # 深色主题背景
    DARK_BG_PRIMARY = "rgba(28, 28, 30, 0.85)"
    DARK_BG_SECONDARY = "rgba(44, 44, 46, 0.85)"
    DARK_BG_TERTIARY = "rgba(58, 58, 60, 0.85)"
    DARK_TEXT_PRIMARY = "#FFFFFF"
    DARK_TEXT_SECONDARY = "#8E8E93"
    DARK_BORDER = "rgba(255, 255, 255, 0.1)"
    DARK_SEPARATOR = "rgba(255, 255, 255, 0.16)"

    # 浅色主题背景
    LIGHT_BG_PRIMARY = "rgba(242, 242, 247, 0.8)"
    LIGHT_BG_SECONDARY = "rgba(255, 255, 255, 0.8)"
    LIGHT_BG_TERTIARY = "rgba(229, 229, 234, 0.8)"
    LIGHT_TEXT_PRIMARY = "#1C1C1E"
    LIGHT_TEXT_SECONDARY = "#8E8E93"
    LIGHT_BORDER = "rgba(0, 0, 0, 0.08)"
    LIGHT_SEPARATOR = "rgba(60, 60, 67, 0.18)"

    # 通用圆角
    RADIUS_SMALL = 8
    RADIUS_MEDIUM = 10
    RADIUS_LARGE = 12
    RADIUS_XLARGE = 16

    @classmethod
    def get_bg_primary(cls, theme: str) -> str:
        return cls.DARK_BG_PRIMARY if theme == "dark" else cls.LIGHT_BG_PRIMARY

    @classmethod
    def get_bg_secondary(cls, theme: str) -> str:
        return cls.DARK_BG_SECONDARY if theme == "dark" else cls.LIGHT_BG_SECONDARY

    @classmethod
    def get_text_primary(cls, theme: str) -> str:
        return cls.DARK_TEXT_PRIMARY if theme == "dark" else cls.LIGHT_TEXT_PRIMARY

    @classmethod
    def get_text_secondary(cls, theme: str) -> str:
        return cls.DARK_TEXT_SECONDARY if theme == "dark" else cls.LIGHT_TEXT_SECONDARY

    @classmethod
    def get_border(cls, theme: str) -> str:
        return cls.DARK_BORDER if theme == "dark" else cls.LIGHT_BORDER

    @classmethod
    def get_accent(cls, theme: str) -> str:
        return cls.BLUE_LIGHT if theme == "dark" else cls.BLUE

    @classmethod
    def get_selection_bg(cls, theme: str) -> str:
        return "rgba(10, 132, 255, 0.30)" if theme == "dark" else "rgba(0, 122, 255, 0.14)"

    @classmethod
    def get_selection_hover_bg(cls, theme: str) -> str:
        return "rgba(255, 255, 255, 0.08)" if theme == "dark" else "rgba(0, 0, 0, 0.05)"

    @classmethod
    def get_selection_text(cls, theme: str) -> str:
        return "rgba(255, 255, 255, 0.95)" if theme == "dark" else "rgba(28, 28, 30, 0.96)"


class PopupMenu(QWidget):
    """
    自定义风格右键弹出菜单

    特性:
    - 圆角边框（完美圆角，无直角残留）
    - 磨砂玻璃模糊背景（与主配置窗口一致）
    - 悬停高亮效果
    - 支持深色/浅色主题
    - 自动定位到屏幕内
    - 内联展开式子菜单
    """

    _active_popups = set()
    _WIN10_SHADOW_SIZE = 10
    _WIN10_SHADOW_DISTANCE = 1

    def __init__(self, theme: str = "dark", radius: int = 12, parent=None, native_effects: bool = True):
        if parent is None and not isinstance(theme, str):
            parent = theme
            theme = getattr(parent, "theme", "dark")
        if theme not in ("dark", "light"):
            theme = "dark"
        super().__init__(parent)
        self._theme = theme
        self._radius = self._effective_radius(radius)
        self._blur_applied = False
        self._native_effects_enabled = bool(native_effects)
        self._effect_generation = 0
        apply_custom_window_chrome(
            self,
            kind="popup",
            translucent=True,
            no_shadow=True,
        )
        self._install_win10_companion_shadow()
        self._leave_timer = QTimer(self)
        self._leave_timer.setSingleShot(True)
        self._leave_timer.setInterval(220)
        self._leave_timer.timeout.connect(self._hide_if_pointer_outside)

        self.setAutoFillBackground(False)
        self.setAttribute(QtCompat.WA_NoSystemBackground, True)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(sp(7), sp(7), sp(7), sp(7))
        self._layout.setSpacing(sp(2))

        # 子菜单项容器列表，用于展开/收起
        self._sub_items_widgets = []
        self._submenu_expanded = False

        # 按钮样式
        self._btn_style_dark = scale_qss(
            "QPushButton{background:transparent;border:none;padding:6px 14px;margin:0px;min-height:20px;"
            "border-radius:6px;color:rgba(255,255,255,0.88);font-size:12px;text-align:left;"
            "font-family:'Segoe UI Variable Text','Segoe UI','Microsoft YaHei UI',sans-serif;font-weight:400;}"
            "QPushButton:hover{background:rgba(255,255,255,0.105);color:rgba(255,255,255,0.98);}"
            "QPushButton:pressed{background:rgba(255,255,255,0.16);}"
            "QPushButton:disabled{color:rgba(255,255,255,0.42);}"
        )
        self._btn_style_light = scale_qss(
            "QPushButton{background:transparent;border:none;padding:6px 14px;margin:0px;min-height:20px;"
            "border-radius:6px;color:rgba(28,28,30,0.88);font-size:12px;text-align:left;"
            "font-family:'Segoe UI Variable Text','Segoe UI','Microsoft YaHei UI',sans-serif;font-weight:400;}"
            "QPushButton:hover{background:rgba(0,0,0,0.055);color:rgba(28,28,30,0.96);}"
            "QPushButton:pressed{background:rgba(0,0,0,0.095);}"
            "QPushButton:disabled{color:rgba(60,60,67,0.42);}"
        )
        # 子菜单项缩进样式
        self._sub_btn_style_dark = scale_qss(
            "QPushButton{background:transparent;border:none;padding:6px 14px 6px 30px;margin:0px;min-height:20px;"
            "border-radius:6px;color:rgba(255,255,255,0.74);font-size:12px;text-align:left;"
            "font-family:'Segoe UI Variable Text','Segoe UI','Microsoft YaHei UI',sans-serif;font-weight:400;}"
            "QPushButton:hover{background:rgba(255,255,255,0.105);color:rgba(255,255,255,0.96);}"
            "QPushButton:pressed{background:rgba(255,255,255,0.16);}"
        )
        self._sub_btn_style_light = scale_qss(
            "QPushButton{background:transparent;border:none;padding:6px 14px 6px 30px;margin:0px;min-height:20px;"
            "border-radius:6px;color:rgba(28,28,30,0.68);font-size:12px;text-align:left;"
            "font-family:'Segoe UI Variable Text','Segoe UI','Microsoft YaHei UI',sans-serif;font-weight:400;}"
            "QPushButton:hover{background:rgba(0,0,0,0.055);color:rgba(28,28,30,0.95);}"
            "QPushButton:pressed{background:rgba(0,0,0,0.095);}"
        )
        self._sep_style_dark = "background-color: rgba(255, 255, 255, 16);"
        self._sep_style_light = "background-color: rgba(60, 60, 67, 18);"

    def add_action(self, text: str, callback, enabled: bool = True):
        """添加菜单项"""
        btn = QPushButton(text, self)
        btn.setEnabled(bool(enabled))
        btn.setCursor(QtCompat.PointingHandCursor)
        try:
            policy = getattr(Qt, "NoFocus", None)
            if policy is None:
                policy = getattr(Qt.FocusPolicy, "NoFocus", None)
            if policy is not None:
                btn.setFocusPolicy(policy)
        except Exception as exc:
            logger.debug("设置按钮焦点策略失败: %s", exc, exc_info=True)
        btn.setStyleSheet(self._btn_style_dark if self._theme == "dark" else self._btn_style_light)
        btn.clicked.connect(lambda checked=False, cb=callback, label=text: self._trigger(cb, label))
        btn.setProperty("popup_menu_role", "action")
        btn.installEventFilter(self)
        self._layout.addWidget(btn)
        return btn

    def add_submenu(self, text: str, items: list):
        """添加内联展开式子菜单

        Args:
            text: 菜单项文字（如 "移动到"）
            items: [(label, callback), ...] 子菜单项列表
        """
        # 触发按钮
        btn = QPushButton(text + "  ▸", self)
        btn.setCursor(QtCompat.PointingHandCursor)
        try:
            policy = getattr(Qt, "NoFocus", None)
            if policy is None:
                policy = getattr(Qt.FocusPolicy, "NoFocus", None)
            if policy is not None:
                btn.setFocusPolicy(policy)
        except Exception as exc:
            logger.debug("设置按钮焦点策略失败: %s", exc, exc_info=True)
        btn.setStyleSheet(self._btn_style_dark if self._theme == "dark" else self._btn_style_light)
        btn.setProperty("popup_menu_role", "submenu")
        btn.installEventFilter(self)
        self._layout.addWidget(btn)

        # 创建子菜单项（初始隐藏）
        sub_widgets = []
        sub_style = self._sub_btn_style_dark if self._theme == "dark" else self._sub_btn_style_light
        for label, callback in items:
            sub_btn = QPushButton(label, self)
            sub_btn.setCursor(QtCompat.PointingHandCursor)
            sub_btn.setStyleSheet(sub_style)
            sub_btn.clicked.connect(lambda checked=False, cb=callback, label=label: self._trigger(cb, label))
            sub_btn.setProperty("popup_menu_role", "sub_action")
            sub_btn.installEventFilter(self)
            sub_btn.hide()
            self._layout.addWidget(sub_btn)
            sub_widgets.append(sub_btn)

        self._sub_items_widgets = sub_widgets

        return btn

    def _expand_submenu(self):
        """展开子菜单项"""
        if self._submenu_expanded:
            return
        self._submenu_expanded = True
        for w in self._sub_items_widgets:
            w.show()
        self.adjustSize()
        self._move_into_screen(self.pos())
        self._schedule_blur_effect()

    def _collapse_submenu(self):
        """收起子菜单项"""
        if not self._submenu_expanded:
            return
        self._submenu_expanded = False
        for w in self._sub_items_widgets:
            w.hide()
        self.adjustSize()
        self._move_into_screen(self.pos())
        self._schedule_blur_effect()

    def add_separator(self):
        """添加分隔线"""
        sep = QWidget(self)
        sep.setFixedHeight(1)
        sep.setStyleSheet(self._sep_style_dark if self._theme == "dark" else self._sep_style_light)
        self._layout.addWidget(sep)
        return sep

    def _trigger(self, callback, action_label: str = ""):
        """触发回调并关闭菜单"""
        try:
            self.hide()
        except Exception as exc:
            logger.debug("隐藏菜单失败: %s", exc, exc_info=True)

        # Run menu actions after Qt has processed the popup hide/focus release.
        # Several actions open modal dialogs or rebuild the icon grid; doing that
        # inside the QPushButton click stack can leave the native popup grab in an
        # unstable state on packaged Windows builds.
        self._retain_until_hidden()
        QTimer.singleShot(0, lambda cb=callback, label=action_label: self._run_deferred_action(cb, label))

    def _run_deferred_action(self, callback, action_label: str = ""):
        try:
            if action_label:
                logger.debug("执行菜单动作: %s", action_label)
            callback()
        except Exception as e:
            logging.getLogger(__name__).exception("菜单动作执行失败 action=%s error=%s", action_label, e)
        finally:
            PopupMenu._release_popup(self)
            try:
                self.deleteLater()
            except RuntimeError:
                logger.debug("延迟删除菜单失败", exc_info=True)

    def popup(self, global_pos):
        """在指定位置显示菜单"""
        self.adjustSize()
        self._move_into_screen(global_pos)
        self._retain_until_hidden()
        win10_shadow = self._uses_win10_companion_shadow()
        if bool(getattr(self, "_native_effects_enabled", False)):
            # Menus appear at full opacity. Prepare the native surface before
            # show() so the first Qt paint already uses the final tint instead
            # of changing color on the first hover-triggered repaint.
            self._apply_blur_effect()
        self.show()
        self.adjustSize()
        self._move_into_screen(self.pos())
        if win10_shadow:
            self._sync_win10_companion_shadow_now()
        self.raise_()
        try:
            self.activateWindow()
            self.setFocus()
        except Exception as exc:
            logger.debug("激活菜单窗口失败: %s", exc, exc_info=True)
        QTimer.singleShot(0, self._reposition_after_show)

    def _retain_until_hidden(self):
        """Keep parentless popup widgets alive while native effects settle."""
        try:
            PopupMenu._active_popups.add(self)
        except Exception as exc:
            logger.debug("保持弹出菜单生命周期失败: %s", exc, exc_info=True)

    @classmethod
    def _release_popup(cls, menu):
        try:
            cls._active_popups.discard(menu)
        except Exception as exc:
            logger.debug("释放弹出菜单生命周期失败: %s", exc, exc_info=True)

    @staticmethod
    def _uses_win10_companion_shadow() -> bool:
        try:
            from ui.utils.window_effect import is_win10

            return is_win10()
        except Exception as exc:
            logger.debug("判断菜单阴影策略失败: %s", exc, exc_info=True)
            return False

    def _install_win10_companion_shadow(self) -> bool:
        if not self._uses_win10_companion_shadow():
            return False
        try:
            from ui.utils.window_effect import install_win10_window_shadow

            return install_win10_window_shadow(
                self,
                self._radius,
                shadow_size=self._WIN10_SHADOW_SIZE,
                shadow_distance=self._WIN10_SHADOW_DISTANCE,
                synchronous=True,
            )
        except (ImportError, AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            logger.debug("安装菜单 Win10 阴影失败: %s", exc, exc_info=True)
            return False

    def _sync_win10_companion_shadow_now(self) -> bool:
        """Create, position, and paint the Win10 shadow before the menu's first frame."""
        if not self._uses_win10_companion_shadow():
            return False
        try:
            shadow = getattr(self, "_quicklauncher_win10_shadow", None)
            if shadow is None:
                if not self._install_win10_companion_shadow():
                    return False
                shadow = getattr(self, "_quicklauncher_win10_shadow", None)
            if shadow is None:
                return False
            shadow.sync()
            shadow_widget = getattr(shadow, "widget", None)
            if shadow_widget is None:
                return False
            shadow_widget.repaint()
            return bool(shadow_widget.isVisible())
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            logger.debug("同步菜单 Win10 阴影失败: %s", exc, exc_info=True)
            return False

    def _next_effect_generation(self) -> int:
        self._effect_generation = int(getattr(self, "_effect_generation", 0) or 0) + 1
        return self._effect_generation

    def _schedule_blur_effect(self, delay_ms: int = 40):
        if not bool(getattr(self, "_native_effects_enabled", False)):
            return
        generation = self._next_effect_generation()
        QTimer.singleShot(
            max(0, int(delay_ms)),
            lambda generation=generation: self._apply_blur_effect_if_current(generation),
        )

    def _apply_blur_effect_if_current(self, generation: int):
        if generation != int(getattr(self, "_effect_generation", -1) or -1):
            return
        try:
            if not self.isVisible():
                return
        except RuntimeError:
            return
        self._apply_blur_effect()

    @staticmethod
    def _effective_radius(radius: int) -> int:
        requested = max(0, int(radius))
        try:
            from ui.utils.window_effect import is_win11

            if is_win11() and requested > 0:
                return min(requested, 8)
        except Exception as exc:
            logger.debug("计算菜单圆角失败: %s", exc, exc_info=True)
        return requested

    def _move_into_screen(self, global_pos):
        """确保菜单在屏幕内"""
        pos = self._as_point(global_pos)
        geo = self._available_geometry_for_pos(pos)

        x = int(pos.x())
        y = int(pos.y())

        if geo is not None:
            margin = sp(4)
            width = max(1, int(self.width()))
            height = max(1, int(self.height()))
            min_x = int(geo.left()) + margin
            min_y = int(geo.top()) + margin
            max_x = int(geo.right()) - width - margin + 1
            max_y = int(geo.bottom()) - height - margin + 1
            x = max(min_x, min(x, max_x))
            y = max(min_y, min(y, max_y))

        self.move(x, y)

    def _reposition_after_show(self):
        """Native window metrics may settle after show() on Win10; clamp once more."""
        try:
            self.adjustSize()
            self._move_into_screen(self.pos())
            if self._uses_win10_companion_shadow():
                self._sync_win10_companion_shadow_now()
            elif not bool(getattr(self, "_blur_applied", False)):
                self._schedule_blur_effect()
        except RuntimeError:
            return
        except Exception as exc:
            logger.debug("菜单显示后二次定位失败: %s", exc, exc_info=True)

    @staticmethod
    def _as_point(global_pos):
        if isinstance(global_pos, QPoint):
            return QPoint(global_pos)
        if hasattr(global_pos, "toPoint"):
            return global_pos.toPoint()
        try:
            return QPoint(int(global_pos.x()), int(global_pos.y()))
        except Exception:
            return QPoint(0, 0)

    @staticmethod
    def _available_geometry_for_pos(pos):
        try:
            screen = QApplication.screenAt(pos)
        except Exception:
            screen = None
        if screen is None:
            try:
                for candidate in QApplication.screens():
                    if candidate.geometry().contains(pos):
                        screen = candidate
                        break
            except Exception:
                screen = None
        if screen is None:
            try:
                screen = QApplication.primaryScreen()
            except Exception:
                screen = None
        try:
            return screen.availableGeometry() if screen else None
        except Exception:
            return None

    def focusOutEvent(self, event):
        """失去焦点时隐藏"""
        try:
            self.hide()
        except Exception as exc:
            logger.debug("隐藏菜单失败: %s", exc, exc_info=True)
        return super().focusOutEvent(event)

    def enterEvent(self, event):
        self._leave_timer.stop()
        return super().enterEvent(event)

    def leaveEvent(self, event):
        """Allow brief pointer slips, then dismiss when it stays outside."""
        if self.isVisible():
            self._leave_timer.start()
        return super().leaveEvent(event)

    def _hide_if_pointer_outside(self):
        try:
            local_pos = self.mapFromGlobal(QCursor.pos())
            if self.isVisible() and not self.rect().contains(local_pos):
                self.hide()
        except RuntimeError:
            return
        except Exception as exc:
            logger.debug("检查菜单鼠标位置失败: %s", exc, exc_info=True)

    def event(self, event):
        if event.type() == QEvent.WindowDeactivate:
            self.hide()
        return super().event(event)

    def showEvent(self, event):
        """Ensure direct show() callers also paint the final surface first."""
        native_effects = bool(getattr(self, "_native_effects_enabled", False))
        if native_effects and not bool(getattr(self, "_blur_applied", False)):
            self._apply_blur_effect()
        return super().showEvent(event)

    def eventFilter(self, obj, event):
        role = obj.property("popup_menu_role") if isinstance(obj, QPushButton) else None
        event_type = event.type()
        if role and event_type == QEvent.Enter:
            if role == "submenu":
                self._expand_submenu()
            elif role == "action":
                self._collapse_submenu()
            self._refresh_action_hover(obj)
        elif role and event_type == QEvent.Leave:
            self._refresh_action_hover(obj)
        return super().eventFilter(obj, event)

    def _refresh_action_hover(self, button):
        """Repaint the parent surface so transparent hover fills cannot linger."""
        try:
            button.update()
            dirty_rect = button.geometry().adjusted(-sp(2), -sp(2), sp(2), sp(2))
            self.update(dirty_rect)
            self.repaint(dirty_rect)
            QTimer.singleShot(0, self.update)
        except RuntimeError:
            return
        except Exception as exc:
            logger.debug("刷新菜单悬停样式失败: %s", exc, exc_info=True)

    def mousePressEvent(self, event):
        try:
            if not self.rect().contains(event.pos()):
                self.hide()
                event.accept()
                return
        except Exception as exc:
            logger.debug("处理菜单外部点击失败: %s", exc, exc_info=True)
        return super().mousePressEvent(event)

    def hideEvent(self, event):
        self._leave_timer.stop()
        PopupMenu._release_popup(self)
        return super().hideEvent(event)

    def closeEvent(self, event):
        PopupMenu._release_popup(self)
        return super().closeEvent(event)

    def keyPressEvent(self, event):
        """按 ESC 隐藏"""
        try:
            key = event.key()
            if key == QtCompat.Key_Escape:
                self.hide()
                return
        except Exception as exc:
            logger.debug("处理按键事件失败: %s", exc, exc_info=True)
        return super().keyPressEvent(event)

    def _apply_blur_effect(self):
        """应用磨砂玻璃模糊效果 + 圆角裁剪（与主配置窗口风格一致）"""
        try:
            from ui.utils.window_effect import (
                get_window_effect,
                is_win10,
                is_win11,
                remove_win10_window_shadow,
            )

            hwnd = int(self.winId())
            if not hwnd:
                return

            effect = get_window_effect()
            w = self.width()
            h = self.height()
            r = self._radius

            if is_win11():
                remove_win10_window_shadow(self)
                effect.clear_window_region(hwnd)
                effect.set_dwm_blur_behind(hwnd, 0, 0, 0, enable=False)

                # Win11: context-menu sized DWM corners + Acrylic tint.
                self._radius = 8
                corner_pref = getattr(effect, "DWMWCP_ROUNDSMALL", None)
                if corner_pref is not None:
                    effect.set_round_corners(hwnd, preference=corner_pref)
                else:
                    effect.set_round_corners(hwnd, enable=True)
                if self._theme == "dark":
                    gradient_color = "d81f1f23"
                else:
                    gradient_color = "e8f7f7fb"
                effect.set_acrylic(hwnd, gradient_color, enable=True, blur=True)
            elif is_win10():
                # A single Qt-painted shadow avoids the doubled rectangular
                # system shadow that Win10 adds to translucent popup windows.
                effect.clear_window_region(hwnd)
                self._install_win10_companion_shadow()
                effect.set_dwm_blur_behind(hwnd, 0, 0, 0, enable=False)
            else:
                remove_win10_window_shadow(self)
                if w > 0 and h > 0:
                    effect.set_window_region(hwnd, w, h, r)
                effect.set_dwm_blur_behind(hwnd, w, h, r, enable=True)
                # 应用半透明着色层
                if self._theme == "dark":
                    gradient_color = "c81c1c1e"
                else:
                    gradient_color = "c8f2f2f7"
                effect.set_acrylic(hwnd, gradient_color, enable=True, blur=False)

            self._blur_applied = True
        except Exception as e:
            logging.getLogger(__name__).debug(f"菜单模糊效果失败: {e}")

    @staticmethod
    def _surface_colors(theme: str, blur_applied: bool, *, win10: bool, win11: bool):
        """Match the menu tint to the themed tool-window surface on each OS."""
        if blur_applied and (win10 or win11):
            if theme == "dark":
                return QColor(28, 28, 30, 180 if win10 else 100), QColor(190, 190, 197, 60)
            return (
                QColor(242, 242, 247, 160 if win10 else 100),
                QColor(229, 229, 234, 150 if win10 else 120),
            )
        if blur_applied:
            if theme == "dark":
                return QColor(31, 31, 35, 120), QColor(255, 255, 255, 38)
            return QColor(255, 255, 255, 120), QColor(0, 0, 0, 20)
        if theme == "dark":
            return QColor(30, 30, 30, 220), QColor(255, 255, 255, int(0.1 * 255))
        return QColor(255, 255, 255, 220), QColor(0, 0, 0, int(0.08 * 255))

    def paintEvent(self, event):
        """绘制圆角背景（模糊层之上的半透明着色）"""
        painter = QPainter(self)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)
        painter.setRenderHint(QtCompat.TextAntialiasing)
        painter.setRenderHint(QtCompat.SmoothPixmapTransform)

        try:
            cm_source = QPainter.CompositionMode.CompositionMode_Source
            cm_over = QPainter.CompositionMode.CompositionMode_SourceOver
        except Exception:
            cm_source = getattr(QPainter, "CompositionMode_Source", None)
            cm_over = getattr(QPainter, "CompositionMode_SourceOver", None)

        if cm_source is not None:
            painter.setCompositionMode(cm_source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        if cm_over is not None:
            painter.setCompositionMode(cm_over)

        # 主题颜色：当模糊效果生效时降低不透明度以显示模糊
        win10_qt_fallback = False
        win11_native = False
        try:
            from ui.utils.window_effect import is_win10, is_win11

            win10_qt_fallback = is_win10()
            win11_native = is_win11()
        except Exception as exc:
            logger.debug("检测Win10菜单绘制模式失败: %s", exc, exc_info=True)

        bg, border = self._surface_colors(
            self._theme,
            self._blur_applied,
            win10=win10_qt_fallback,
            win11=win11_native,
        )

        if win10_qt_fallback:
            paint_win10_rounded_surface(painter, self, bg, border, self._radius, inset=0.5)
            painter.end()
            return

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        painter.fillPath(path, bg)
        pen = QPen(border, 1)
        pen.setJoinStyle(QtCompat.RoundJoin)
        pen.setCapStyle(QtCompat.RoundCap)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()

    def resizeEvent(self, event):
        """窗口大小变化时重新应用模糊和圆角裁剪"""
        super().resizeEvent(event)
        if self._blur_applied and self.isVisible():
            self._schedule_blur_effect()


class StyleSheet:
    """
    简约风格样式表生成器
    """

    @staticmethod
    def get_button_style(theme: str) -> str:
        """获取按钮样式 - 苹果奶白风格"""
        if theme == "dark":
            return """
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.12);
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 10px;
                    padding: 3px 12px;
                    color: rgba(255, 255, 255, 0.85);
                    font-size: 11px;
                    font-weight: 400;
                    min-height: 22px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.20);
                    border: 1px solid rgba(255, 255, 255, 0.25);
                }
                QPushButton:focus {
                    border: 1px solid rgba(10, 132, 255, 0.78);
                }
                QPushButton:pressed {
                    background-color: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.14);
                }
                QPushButton:default {
                    background-color: #0A84FF;
                    border: 1px solid #0A84FF;
                    color: white;
                }
                QPushButton:default:hover {
                    background-color: #0077EA;
                }
                QPushButton:default:pressed {
                    background-color: #006FD6;
                    border: 1px solid #006FD6;
                }
                QPushButton:disabled {
                    background-color: rgba(255, 255, 255, 0.06);
                    color: rgba(235, 235, 245, 0.3);
                }
            """
        else:
            return """
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.80);
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    border-radius: 10px;
                    padding: 3px 12px;
                    color: rgba(28, 28, 30, 0.75);
                    font-size: 11px;
                    font-weight: 400;
                    min-height: 22px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.95);
                    border: 1px solid rgba(0, 0, 0, 0.10);
                }
                QPushButton:focus {
                    border: 1px solid rgba(0, 122, 255, 0.55);
                }
                QPushButton:pressed {
                    background-color: rgba(240, 240, 245, 0.90);
                    border: 1px solid rgba(0, 0, 0, 0.12);
                }
                QPushButton:default {
                    background-color: #007AFF;
                    border: 1px solid #007AFF;
                    color: white;
                }
                QPushButton:default:hover {
                    background-color: #0A84FF;
                }
                QPushButton:default:pressed {
                    background-color: #006FD6;
                    border: 1px solid #006FD6;
                }
                QPushButton:disabled {
                    background-color: rgba(0, 0, 0, 0.04);
                    color: rgba(60, 60, 67, 0.3);
                }
            """

    @staticmethod
    def get_input_style(theme: str) -> str:
        selection_bg = Colors.get_selection_bg(theme)
        selection_text = Colors.get_selection_text(theme)
        """获取输入框样式 - 紧凑版"""
        if theme == "dark":
            return """
                QLineEdit, QTextEdit, QPlainTextEdit {
                    background-color: rgba(190, 190, 197, 0.22);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 6px;
                    padding: 4px 8px;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: 400;
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                    border: 1px solid #0A84FF;
                    background-color: rgba(190, 190, 197, 0.28);
                }
                QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
                    background-color: rgba(190, 190, 197, 0.12);
                    color: rgba(235, 235, 245, 0.3);
                }
            """.replace(
                "{selection_bg}", selection_bg
            ).replace(
                "{selection_text}", selection_text
            )
        else:
            return """
                QLineEdit, QTextEdit, QPlainTextEdit {
                    background-color: #ffffff;
                    border: 1px solid rgba(0, 0, 0, 0.12);
                    border-radius: 6px;
                    padding: 4px 8px;
                    color: #1c1c1e;
                    font-size: 11px;
                    font-weight: 400;
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                    border: 1px solid #007AFF;
                    background-color: #ffffff;
                }
                QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
                    background-color: #f5f5f7;
                    color: rgba(60, 60, 67, 0.3);
                }
            """.replace(
                "{selection_bg}", selection_bg
            ).replace(
                "{selection_text}", selection_text
            )

    @staticmethod
    def get_scrollbar_style(theme: str) -> str:
        """获取滚动条样式"""
        if theme == "dark":
            handle_color = "rgba(255, 255, 255, 80)"
            handle_hover = "rgba(255, 255, 255, 120)"
        else:
            handle_color = "rgba(0, 0, 0, 60)"
            handle_hover = "rgba(0, 0, 0, 100)"

        return f"""
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {handle_color};
                min-height: 30px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {handle_hover};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QScrollBar:horizontal {{
                border: none;
                background: transparent;
                height: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: {handle_color};
                min-width: 30px;
                border-radius: 3px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {handle_hover};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
                background: none;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
        """

    @staticmethod
    def get_combobox_style(theme: str) -> str:
        selection_bg = Colors.get_selection_bg(theme)
        selection_hover_bg = Colors.get_selection_hover_bg(theme)
        selection_text = Colors.get_selection_text(theme)
        """获取下拉框样式"""
        if theme == "dark":
            return (
                """
                QComboBox {
                    background-color: rgba(190, 190, 197, 0.22);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 6px;
                    padding: 5px 8px;
                    padding-right: 25px;
                    color: rgba(255, 255, 255, 0.9);
                    min-height: 24px;
                    font-size: 12px;
                    margin: 0px;
                }
                QComboBox:hover {
                    border: 1px solid #0A84FF;
                    background-color: rgba(190, 190, 197, 0.30);
                }
                QComboBox:focus {
                    border: 1px solid #0A84FF;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                    subcontrol-position: center right;
                    subcontrol-origin: padding;
                    right: 5px;
                }
                QComboBox::down-arrow {
                    image: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2.5 3.5L5 6L7.5 3.5' fill='none' stroke='white' stroke-width='1.2' stroke-linecap='round' stroke-linejoin='round'/></svg>");
                    width: 10px;
                    height: 10px;
                }
                QComboBox QAbstractItemView {
                    background-color: rgba(40, 40, 45, 200);
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 8px;
                    padding: 4px;
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                    color: #ffffff;
                    outline: none;
                }
                QComboBox QAbstractItemView::item {
                    padding: 4px 8px;
                    border-radius: 6px;
                    margin: 2px;
                }
                QComboBox QAbstractItemView::item:hover {
                    background-color: {selection_hover_bg};
                }
                QComboBox QAbstractItemView::item:selected {
                    background-color: {selection_bg};
                    color: {selection_text};
                    border: 1px solid rgba(10, 132, 255, 0.45);
                }
            """.replace(
                    "{selection_bg}", selection_bg
                )
                .replace("{selection_hover_bg}", selection_hover_bg)
                .replace("{selection_text}", selection_text)
            )
        else:
            return (
                """
                QComboBox {
                    background-color: rgba(255, 255, 255, 120);
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    border-radius: 6px;
                    padding: 5px 8px;
                    padding-right: 25px;
                    color: #1c1c1e;
                    min-height: 24px;
                    font-size: 12px;
                    margin: 0px;
                }
                QComboBox:hover {
                    border: 1px solid #007AFF;
                    background-color: rgba(255, 255, 255, 180);
                }
                QComboBox:focus {
                    border: 1px solid #007AFF;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                    subcontrol-position: center right;
                    subcontrol-origin: padding;
                    right: 5px;
                }
                QComboBox::down-arrow {
                    image: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2.5 3.5L5 6L7.5 3.5' fill='none' stroke='black' stroke-width='1.2' stroke-linecap='round' stroke-linejoin='round'/></svg>");
                    width: 10px;
                    height: 10px;
                }
                QComboBox QAbstractItemView {
                    background-color: rgba(255, 255, 255, 210);
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    border-radius: 8px;
                    padding: 4px;
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                    color: #1c1c1e;
                    outline: none;
                }
                QComboBox QAbstractItemView::item {
                    padding: 4px 8px;
                    border-radius: 6px;
                    margin: 2px;
                }
                QComboBox QAbstractItemView::item:hover {
                    background-color: {selection_hover_bg};
                }
                QComboBox QAbstractItemView::item:selected {
                    background-color: {selection_bg};
                    color: {selection_text};
                    border: 1px solid rgba(0, 122, 255, 0.25);
                }
            """.replace(
                    "{selection_bg}", selection_bg
                )
                .replace("{selection_hover_bg}", selection_hover_bg)
                .replace("{selection_text}", selection_text)
            )

    @staticmethod
    def get_groupbox_style(theme: str) -> str:
        """获取分组框样式 - 极简风格"""
        if theme == "dark":
            return """
                QGroupBox {
                    font-weight: 400;
                    border: none;
                    margin-top: 10px;
                    padding-top: 24px;
                    font-size: 13px;
                    color: white;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 0px;
                    padding: 0px 0px 8px 0px;
                    background-color: transparent;
                    color: #ffffff;
                }
            """
        else:
            return """
                QGroupBox {
                    font-weight: 400;
                    border: none;
                    margin-top: 6px;
                    padding-top: 20px;
                    font-size: 13px;
                    color: #1c1c1e;
                }
                QGroupBox::title {
                    subcontrol-origin: padding;
                    subcontrol-position: top left;
                    left: 0px;
                    padding: 0px 0px 4px 0px;
                    background-color: transparent;
                    color: #1c1c1e;
                }
            """

    @staticmethod
    def get_slider_style(theme: str) -> str:
        """获取滑块样式"""
        accent = "#0A84FF" if theme == "dark" else "#007AFF"
        track_bg = "#3a3a3c" if theme == "dark" else "#D1D1D6"

        # 处理手柄边框，使其更柔和以避免毛刺感
        if theme == "dark":
            handle_border = "1px solid rgba(0, 0, 0, 0.2)"
            handle_bg = "#ffffff"
        else:
            handle_border = "1px solid rgba(0, 0, 0, 0.05)"
            handle_bg = "#ffffff"

        return f"""
            QSlider::groove:horizontal {{
                height: 4px;
                background: transparent;
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {accent};
                border-radius: 2px;
            }}
            QSlider::add-page:horizontal {{
                background: {track_bg};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {handle_bg};
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
                border: {handle_border};
            }}
            QSlider::handle:horizontal:hover {{
                background: #f8f8f8;
                border: 1px solid rgba(0, 0, 0, 0.1);
            }}
            QSlider::handle:horizontal:pressed {{
                background: #f0f0f0;
            }}
        """


class Glassmorphism:
    """
    磨砂玻璃拟态样式生成器
    提供 Glassmorphism + Neumorphism 混合效果
    """

    # 样式表缓存：避免每次调用都重新生成大量字符串拼接
    _full_stylesheet_cache: dict[tuple[str, int], str] = {}

    @classmethod
    def clear_stylesheet_cache(cls) -> None:
        """清除缓存的样式表（DPI 缩放变化时调用）"""
        cls._full_stylesheet_cache.clear()

    @staticmethod
    def get_glassmorphism_container_style(theme: str) -> str:
        """获取磨砂玻璃容器背景样式（用于主窗口背景）"""
        if theme == "dark":
            return """
                background-color: rgba(28, 28, 30, 160);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            """
        else:
            return """
                background-color: rgba(242, 242, 247, 120);
                border: 1px solid rgba(0, 0, 0, 0.05);
                border-radius: 12px;
            """

    @staticmethod
    def get_neumorphism_button_style(theme: str) -> str:
        """获取拟态按钮样式（带柔和阴影）"""
        if theme == "dark":
            return """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(85, 85, 90, 0.9),
                        stop:0.5 rgba(75, 75, 80, 0.9),
                        stop:1 rgba(65, 65, 70, 0.9));
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 10px;
                    padding: 4px 16px;
                    color: rgba(255, 255, 255, 0.95);
                    font-size: 12px;
                    font-weight: 400;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(95, 95, 100, 0.95),
                        stop:0.5 rgba(85, 85, 90, 0.95),
                        stop:1 rgba(75, 75, 80, 0.95));
                    border: 1px solid rgba(255, 255, 255, 0.25);
                }
                QPushButton:focus {
                    border: 1px solid rgba(10, 132, 255, 0.78);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(55, 55, 60, 0.9),
                        stop:1 rgba(65, 65, 70, 0.9));
                    border: 1px solid rgba(255, 255, 255, 0.1);
                }
                QPushButton:default {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(10, 132, 255, 0.8),
                        stop:1 rgba(0, 100, 220, 0.8));
                    border: 1px solid rgba(255, 255, 255, 0.15);
                }
                QPushButton:disabled {
                    background: rgba(44, 44, 46, 0.4);
                    color: rgba(255, 255, 255, 0.3);
                }
            """
        else:
            return """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(255, 255, 255, 0.8),
                        stop:0.5 rgba(250, 250, 252, 0.8),
                        stop:1 rgba(240, 240, 245, 0.8));
                    border: 1px solid rgba(0, 0, 0, 0.06);
                    border-radius: 10px;
                    padding: 4px 16px;
                    color: rgba(28, 28, 30, 0.9);
                    font-size: 12px;
                    font-weight: 400;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(255, 255, 255, 0.9),
                        stop:1 rgba(245, 245, 250, 0.9));
                    border: 1px solid rgba(0, 0, 0, 0.1);
                }
                QPushButton:focus {
                    border: 1px solid rgba(0, 122, 255, 0.55);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(235, 235, 240, 0.9),
                        stop:1 rgba(245, 245, 250, 0.9));
                    border: 1px solid rgba(0, 0, 0, 0.12);
                }
                QPushButton:default {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(0, 122, 255, 0.8),
                        stop:1 rgba(0, 100, 220, 0.8));
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    color: #ffffff;
                }
                QPushButton:disabled {
                    background: rgba(242, 242, 247, 0.4);
                    color: rgba(60, 60, 67, 0.3);
                }
            """

    @staticmethod
    def get_flat_action_button_style(theme: str) -> str:
        """获取扁平操作按钮样式（与主配置窗口底部四按钮一致）"""
        if theme == "dark":
            btn_bg = "rgba(255,255,255,0.18)"
            btn_border = "rgba(255,255,255,0.22)"
            btn_hover = "rgba(255,255,255,0.28)"
            text_color = "rgba(255,255,255,0.85)"
        else:
            btn_bg = "rgba(255,255,255,0.75)"
            btn_border = "rgba(255,255,255,0.35)"
            btn_hover = "rgba(255,255,255,0.95)"
            text_color = "#1D1D1F"

        return scale_qss(
            f"""
            QPushButton {{
                font-size: 11px;
                padding: 4px 13px;
                background: {btn_bg};
                border: 1px solid {btn_border};
                border-radius: 10px;
                color: {text_color};
            }}
            QPushButton:hover {{ background-color: {btn_hover}; }}
            QPushButton:pressed {{ background-color: {btn_bg}; opacity: 0.8; }}
            QPushButton:disabled {{ background-color: rgba(255,255,255,0.3); color: #C7C7CC; }}
        """
        )

    @staticmethod
    def get_action_button_style(theme: str, is_compact: bool = False, is_delete: bool = False) -> str:
        """获取设置/配置窗口按钮的统一精细样式 (保证视觉 100% 一致)"""
        if is_delete:
            if theme == "dark":
                return scale_qss(
                    """
                    QPushButton {
                        font-size: 10px;
                        padding: 2px 4px;
                        margin: 0px;
                        background: rgba(244, 67, 54, 0.15);
                        border: 1px solid rgba(244, 67, 54, 0.3);
                        border-radius: 4px;
                        color: #ff5252;
                        font-weight: 400;
                    }
                    QPushButton:hover {
                        background-color: rgba(244, 67, 54, 0.25);
                        border: 1px solid rgba(244, 67, 54, 0.5);
                        color: #ff7979;
                    }
                    QPushButton:pressed { opacity: 0.7; }
                    QPushButton:disabled {
                        color: rgba(128,128,128,0.4);
                        background: rgba(128,128,128,0.08);
                        border: 1px solid rgba(128,128,128,0.15);
                    }
                """
                )
            else:
                return scale_qss(
                    """
                    QPushButton {
                        font-size: 10px;
                        padding: 2px 4px;
                        margin: 0px;
                        background: rgba(211, 47, 47, 0.08);
                        border: 1px solid rgba(211, 47, 47, 0.25);
                        border-radius: 4px;
                        color: #d32f2f;
                        font-weight: 400;
                    }
                    QPushButton:hover {
                        background-color: rgba(211, 47, 47, 0.15);
                        border: 1px solid rgba(211, 47, 47, 0.45);
                        color: #c62828;
                    }
                    QPushButton:pressed { opacity: 0.7; }
                    QPushButton:disabled {
                        color: rgba(128,128,128,0.4);
                        background: rgba(128,128,128,0.08);
                        border: 1px solid rgba(128,128,128,0.15);
                    }
                """
                )

        if theme == "dark":
            btn_bg = "rgba(255,255,255,0.18)"
            btn_border = "rgba(255,255,255,0.22)"
            btn_hover = "rgba(255,255,255,0.28)"
            btn_hover_text = "rgba(255,255,255,0.95)"
            text_color = "rgba(255,255,255,0.85)"
        else:
            btn_bg = "rgba(255,255,255,0.75)"
            btn_border = "rgba(255,255,255,0.35)"
            btn_hover = "rgba(255,255,255,0.95)"
            btn_hover_text = "rgba(28,28,30,0.9)"
            text_color = "rgba(28,28,30,0.75)"

        if is_compact:
            return scale_qss(
                f"""
                QPushButton {{
                    font-size: 10px;
                    padding: 2px 4px;
                    margin: 0px;
                    background: {btn_bg};
                    border: 1px solid {btn_border};
                    border-radius: 4px;
                    color: {text_color};
                    font-weight: 400;
                }}
                QPushButton:hover {{
                    background-color: {btn_hover};
                    color: {btn_hover_text};
                }}
                QPushButton:pressed {{ opacity: 0.7; }}
                QPushButton:disabled {{
                    color: rgba(128,128,128,0.4);
                    background: rgba(128,128,128,0.08);
                    border: 1px solid rgba(128,128,128,0.15);
                }}
                QPushButton:checked {{
                    background-color: rgba(10,132,255,0.85);
                    color: white;
                    border: 1px solid rgba(10,132,255,0.9);
                }}
            """
            )
        else:
            return scale_qss(
                f"""
                QPushButton {{
                    font-size: 11px;
                    padding: 5px 12px;
                    background: {btn_bg};
                    border: 1px solid {btn_border};
                    border-radius: 8px;
                    color: {text_color};
                    font-weight: 400;
                }}
                QPushButton:hover {{
                    background-color: {btn_hover};
                    color: {btn_hover_text};
                }}
                QPushButton:pressed {{ opacity: 0.7; }}
                QPushButton:disabled {{
                    color: rgba(128,128,128,0.4);
                    background: rgba(128,128,128,0.08);
                    border: 1px solid rgba(128,128,128,0.15);
                }}
                QPushButton:checked {{
                    background-color: rgba(10,132,255,0.85);
                    color: white;
                    border: 1px solid rgba(10,132,255,0.9);
                }}
            """
            )

    @staticmethod
    def get_neumorphism_input_style(theme: str) -> str:
        selection_bg = Colors.get_selection_bg(theme)
        selection_text = Colors.get_selection_text(theme)
        """获取拟态输入框样式"""
        if theme == "dark":
            return """
                /* Text Inputs */
                QLineEdit, QTextEdit, QPlainTextEdit {
                    background: rgba(38, 38, 42, 0.7);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 6px;
                    padding: 3px 8px;
                    min-height: 24px;
                    font-size: 12px;
                    font-weight: 400;
                    margin: 0px;
                    color: rgba(255, 255, 255, 0.9);
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                    border: 1px solid rgba(10, 132, 255, 0.8);
                    background: rgba(42, 42, 46, 0.85);
                }
                QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
                    background: rgba(38, 38, 42, 0.3);
                    color: rgba(255, 255, 255, 0.3);
                }

                /* SpinBox (Container) */
                QSpinBox {
                    background: rgba(38, 38, 42, 0.7);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 6px;
                    padding: 3px 8px;
                    min-height: 24px;
                    font-size: 12px;
                    margin: 0px;
                    color: rgba(255, 255, 255, 0.9);
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                }
                QSpinBox:focus, QSpinBox:hover {
                    border: 1px solid rgba(10, 132, 255, 0.8);
                    background: rgba(42, 42, 46, 0.85);
                }
                QSpinBox:disabled {
                    background: rgba(38, 38, 42, 0.3);
                    color: rgba(255, 255, 255, 0.3);
                }

                /* SpinBox Inner Edit - Reset to transparent */
                QSpinBox QLineEdit {
                    background: transparent;
                    border: none;
                    margin: 0;
                    padding: 0;
                    min-height: 0;
                }
                QSpinBox QLineEdit:focus {
                    background: transparent;
                    border: none;
                }
            """.replace(
                "{selection_bg}", selection_bg
            ).replace(
                "{selection_text}", selection_text
            )
        else:
            return """
                /* Text Inputs */
                QLineEdit, QTextEdit, QPlainTextEdit {
                    background: rgba(255, 255, 255, 0.7);
                    border: 1px solid rgba(0, 0, 0, 0.1);
                    border-radius: 6px;
                    padding: 3px 8px;
                    min-height: 24px;
                    font-size: 12px;
                    font-weight: 400;
                    margin: 0px;
                    color: rgba(28, 28, 30, 0.9);
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                    border: 1px solid rgba(0, 122, 255, 0.5);
                    background: rgba(255, 255, 255, 0.85);
                }
                QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
                    background: rgba(242, 242, 247, 0.4);
                    color: rgba(60, 60, 67, 0.3);
                }

                /* SpinBox (Container) */
                QSpinBox {
                    background: rgba(255, 255, 255, 0.7);
                    border: 1px solid rgba(0, 0, 0, 0.06);
                    border-radius: 6px;
                    padding: 3px 8px;
                    min-height: 24px;
                    font-size: 12px;
                    margin: 0px;
                    color: rgba(28, 28, 30, 0.9);
                    selection-background-color: {selection_bg};
                    selection-color: {selection_text};
                }
                QSpinBox:focus, QSpinBox:hover {
                    border: 1px solid rgba(0, 122, 255, 0.5);
                    background: rgba(255, 255, 255, 0.85);
                }
                QSpinBox:disabled {
                    background: rgba(242, 242, 247, 0.4);
                    color: rgba(60, 60, 67, 0.3);
                }

                /* SpinBox Inner Edit - Reset to transparent */
                QSpinBox QLineEdit {
                    background: transparent;
                    border: none;
                    margin: 0;
                    padding: 0;
                    min-height: 0;
                }
                QSpinBox QLineEdit:focus {
                    background: transparent;
                    border: none;
                }
            """.replace(
                "{selection_bg}", selection_bg
            ).replace(
                "{selection_text}", selection_text
            )

    @staticmethod
    def get_neumorphism_groupbox_style(theme: str) -> str:
        """获取拟态分组框样式（内嵌效果）"""
        if theme == "dark":
            return """
                QGroupBox {
                    font-weight: 400;
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    margin-top: 18px;
                    padding-top: 10px;
                    font-size: 12px;
                    color: rgba(255, 255, 255, 0.9);
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 14px;
                    padding: 2px 10px;
                    background: transparent;
                    color: rgba(255, 255, 255, 0.5);
                    font-size: 11px;
                }
            """
        else:
            return """
                QGroupBox {
                    font-weight: 400;
                    background: rgba(0, 0, 0, 0.03);
                    border: 1px solid rgba(0, 0, 0, 0.06);
                    border-radius: 12px;
                    margin-top: 18px;
                    padding-top: 10px;
                    font-size: 12px;
                    color: rgba(28, 28, 30, 0.9);
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 14px;
                    padding: 2px 10px;
                    background: transparent;
                    color: rgba(0, 0, 0, 0.5);
                    font-size: 11px;
                }
            """

    @staticmethod
    def get_neumorphism_list_style(theme: str) -> str:
        selection_bg = Colors.get_selection_bg(theme)
        selection_hover_bg = Colors.get_selection_hover_bg(theme)
        selection_text = Colors.get_selection_text(theme)
        """获取拟态列表样式"""
        if theme == "dark":
            return (
                """
                QListWidget {
                    background: rgba(30, 30, 34, 0.5);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    outline: none;
                    padding: 4px;
                }
                QListWidget::item {
                    padding: 10px 12px;
                    border-radius: 8px;
                    margin: 2px 4px;
                    color: rgba(255, 255, 255, 0.85);
                }
                QListWidget::item:selected {
                    background: {selection_bg};
                    color: {selection_text};
                    border: 1px solid rgba(10, 132, 255, 0.42);
                }
                QListWidget::item:hover:!selected {
                    background: {selection_hover_bg};
                }
            """.replace(
                    "{selection_bg}", selection_bg
                )
                .replace("{selection_hover_bg}", selection_hover_bg)
                .replace("{selection_text}", selection_text)
            )
        else:
            return (
                """
                QListWidget {
                    background: rgba(240, 240, 245, 0.4);
                    border: 1px solid rgba(0, 0, 0, 0.05);
                    border-radius: 12px;
                    outline: none;
                    padding: 4px;
                }
                QListWidget::item {
                    padding: 10px 12px;
                    border-radius: 8px;
                    margin: 2px 4px;
                    color: rgba(28, 28, 30, 0.85);
                }
                QListWidget::item:selected {
                    background: {selection_bg};
                    color: {selection_text};
                    border: 1px solid rgba(0, 122, 255, 0.22);
                }
                QListWidget::item:hover:!selected {
                    background: {selection_hover_bg};
                }
            """.replace(
                    "{selection_bg}", selection_bg
                )
                .replace("{selection_hover_bg}", selection_hover_bg)
                .replace("{selection_text}", selection_text)
            )

    @staticmethod
    def get_full_glassmorphism_stylesheet(theme: str) -> str:
        """获取完整的磨砂玻璃拟态样式表（带缓存）"""
        cache_key = (theme, get_scale_percent())
        if cache_key in Glassmorphism._full_stylesheet_cache:
            return Glassmorphism._full_stylesheet_cache[cache_key]
        glass = Glassmorphism
        scrollbar = StyleSheet.get_scrollbar_style(theme)
        slider = StyleSheet.get_slider_style(theme)
        combobox = StyleSheet.get_combobox_style(theme)

        if theme == "dark":
            base = """
                QWidget {
                    background: transparent;
                    color: rgba(255, 255, 255, 0.9);
                    font-size: 13px;
                    font-weight: 400;
                }
                QLabel {
                    background: transparent;
                    color: rgba(255, 255, 255, 0.9);
                    font-size: 13px;
                    font-weight: 400;
                }
                QPushButton {
                    font-size: 13px;
                    font-weight: 400;
                    padding: 0px;
                    text-align: center;
                }
                QLineEdit, QTextEdit, QPlainTextEdit {
                    font-size: 13px;
                    font-weight: 400;
                }
                QCheckBox, QRadioButton {
                    font-size: 13px;
                    font-weight: 400;
                }
                QComboBox {
                    font-size: 13px;
                    font-weight: 400;
                }
                QListWidget {
                    font-size: 13px;
                    font-weight: 400;
                }
                QToolTip {
                    background: rgba(44, 44, 48, 240);
                    color: #ffffff;
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 6px;
                    padding: 4px 8px;
                    font-size: 11px;
                    font-weight: 400;
                }
                QScrollArea {
                    border: none;
                    background: transparent;
                }
                QStatusBar {
                    background: transparent;
                    color: rgba(142, 142, 147, 0.8);
                    font-size: 11px;
                    font-weight: 400;
                }
            """
        else:
            base = """
                QWidget {
                    background: transparent;
                    color: rgba(28, 28, 30, 0.9);
                    font-size: 13px;
                    font-weight: 400;
                }
                QLabel {
                    background: transparent;
                    color: rgba(28, 28, 30, 0.9);
                    font-size: 13px;
                    font-weight: 400;
                }
                QPushButton {
                    font-size: 13px;
                    font-weight: 400;
                    padding: 0px;
                    text-align: center;
                }
                QLineEdit, QTextEdit, QPlainTextEdit {
                    font-size: 13px;
                    font-weight: 400;
                }
                QCheckBox, QRadioButton {
                    font-size: 13px;
                    font-weight: 400;
                }
                QComboBox {
                    font-size: 13px;
                    font-weight: 400;
                }
                QListWidget {
                    font-size: 13px;
                    font-weight: 400;
                }
                QToolTip {
                    background: rgba(255, 255, 255, 240);
                    color: #1c1c1e;
                    border: 1px solid rgba(0, 0, 0, 0.1);
                    border-radius: 6px;
                    padding: 4px 8px;
                    font-size: 11px;
                    font-weight: 400;
                }
                QScrollArea {
                    border: none;
                    background: transparent;
                }
                QStatusBar {
                    background: transparent;
                    color: rgba(142, 142, 147, 0.8);
                    font-size: 11px;
                    font-weight: 400;
                }
            """

        result = scale_qss(
            base
            + glass.get_neumorphism_button_style(theme)
            + glass.get_neumorphism_input_style(theme)
            + glass.get_neumorphism_groupbox_style(theme)
            + glass.get_neumorphism_list_style(theme)
            + scrollbar
            + slider
            + combobox
        )
        Glassmorphism._full_stylesheet_cache[cache_key] = result
        return result


def get_menu_stylesheet(theme: str) -> str:
    selection_bg = Colors.get_selection_bg(theme)
    selection_text = Colors.get_selection_text(theme)
    """获取菜单样式表（用于 QMenu）— 半透明背景配合模糊效果"""
    if theme == "dark":
        css = """
            QMenu {
                background-color: rgba(30, 30, 30, 120);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 12px;
                padding: 6px;
            }
            QMenu::item {
                background-color: transparent;
                color: #ffffff;
                padding: 8px 20px;
                border-radius: 8px;
                margin: 2px 4px;
            }
            QMenu::item:selected {
                background-color: {selection_bg};
                color: {selection_text};
            }
            QMenu::item:disabled {
                color: rgba(255, 255, 255, 110);
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(255, 255, 255, 16);
                margin: 6px 10px;
            }
        """.replace(
            "{selection_bg}", selection_bg
        ).replace(
            "{selection_text}", selection_text
        )
    else:
        css = """
            QMenu {
                background-color: rgba(255, 255, 255, 120);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 12px;
                padding: 6px;
            }
            QMenu::item {
                background-color: transparent;
                color: #1c1c1e;
                padding: 8px 20px;
                border-radius: 8px;
                margin: 2px 4px;
            }
            QMenu::item:selected {
                background-color: {selection_bg};
                color: {selection_text};
            }
            QMenu::item:disabled {
                color: rgba(60, 60, 67, 120);
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(60, 60, 67, 18);
                margin: 6px 10px;
            }
        """.replace(
            "{selection_bg}", selection_bg
        ).replace(
            "{selection_text}", selection_text
        )
    return scale_qss(css)


def get_dialog_stylesheet(theme: str) -> str:
    """获取对话框完整样式表"""
    style = StyleSheet

    from ui.utils.font_manager import get_font_css

    font_family = get_font_css().removeprefix("font-family: ").removesuffix(";")

    if theme == "dark":
        text_primary = Colors.DARK_TEXT_PRIMARY
        text_secondary = Colors.DARK_TEXT_SECONDARY
    else:
        text_primary = Colors.LIGHT_TEXT_PRIMARY
        text_secondary = Colors.LIGHT_TEXT_SECONDARY

    base = f"""
        QWidget {{
            font-family: {font_family};
            font-size: 11px;
            color: {text_primary};
        }}
        QDialog {{
            background: transparent;
        }}
        QLabel {{
            color: {text_primary};
            background: transparent;
            border: none;
        }}
        QLabel#TitleLabel {{
            color: {text_primary};
            margin-bottom: 4px;
        }}
        QLabel#SubtitleLabel {{
            font-size: 10px;
            color: {text_secondary};
        }}
        QCheckBox {{
            spacing: 6px;
            color: {text_primary};
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 3px;
            border: 1px solid {text_secondary};
            background-color: transparent;
        }}
        QCheckBox::indicator:checked {{
            background-color: #007AFF;
            border-color: #007AFF;
            image: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='white'><path d='M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'/></svg>");
        }}
        QRadioButton {{
            spacing: 6px;
            color: {text_primary};
        }}
        QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 8px;
            border: 1px solid {text_secondary};
            background-color: transparent;
        }}
        QRadioButton::indicator:checked {{
            background-color: #007AFF;
            border-color: #007AFF;
            image: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='white'><circle cx='12' cy='12' r='5'/></svg>");
        }}
    """

    return scale_qss(
        base
        + style.get_button_style(theme)
        + style.get_input_style(theme)
        + style.get_scrollbar_style(theme)
        + style.get_combobox_style(theme)
        + style.get_groupbox_style(theme)
        + style.get_slider_style(theme)
    )


def get_button_stylesheet(theme: str) -> str:
    """获取按钮样式表"""
    return scale_qss(StyleSheet.get_button_style(theme))
