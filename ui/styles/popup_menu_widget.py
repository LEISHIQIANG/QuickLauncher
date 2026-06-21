"""PopupMenu widget - extracted from style."""

from __future__ import annotations

import logging

from qt_compat import (
    QApplication,
    QColor,
    QCursor,
    QEvent,
    QPainter,
    QPainterPath,
    QPoint,
    QPushButton,
    QRectF,
    Qt,
    QtCompat,
    QTimer,
    QVBoxLayout,
    QWidget,
)
from ui.styles.design_tokens import BorderScale, SurfaceScale
from ui.styles.window_chrome import apply_custom_window_chrome
from ui.utils.pixel_snap import make_cosmetic_pen
from ui.utils.ui_scale import scale_qss, sp
from ui.utils.window_effect import paint_win10_rounded_surface

logger = logging.getLogger(__name__)


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

    _active_popups = set()  # type: ignore[var-annotated]
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
        self._sub_items_widgets = []  # type: ignore[var-annotated]
        self._submenu_expanded = False

        # 按钮样式
        self._btn_style_dark = scale_qss(
            "QPushButton{background:transparent;border-radius: 0; border:none;padding:6px 14px;margin:0px;min-height:20px;"
            "border-radius:6px;color:rgba(255,255,255,0.88);font-size:12px;text-align:left;"
            "font-family:'Microsoft YaHei UI','Microsoft YaHei','Segoe UI Variable Text','Segoe UI',sans-serif;font-weight:400;}"
            "QPushButton:hover{background:rgba(255,255,255,0.105);color:rgba(255,255,255,0.98);}"
            "QPushButton:pressed{background:rgba(255,255,255,0.16);}"
            "QPushButton:disabled{color:rgba(255,255,255,0.42);}"
        )
        self._btn_style_light = scale_qss(
            "QPushButton{background:transparent;border-radius: 0; border:none;padding:6px 14px;margin:0px;min-height:20px;"
            "border-radius:6px;color:rgba(28,28,30,0.88);font-size:12px;text-align:left;"
            "font-family:'Microsoft YaHei UI','Microsoft YaHei','Segoe UI Variable Text','Segoe UI',sans-serif;font-weight:400;}"
            "QPushButton:hover{background:rgba(0,0,0,0.055);color:rgba(28,28,30,0.96);}"
            "QPushButton:pressed{background:rgba(0,0,0,0.095);}"
            "QPushButton:disabled{color:rgba(60,60,67,0.42);}"
        )
        # 子菜单项缩进样式
        self._sub_btn_style_dark = scale_qss(
            "QPushButton{background:transparent;border-radius: 0; border:none;padding:6px 14px 6px 30px;margin:0px;min-height:20px;"
            "border-radius:6px;color:rgba(255,255,255,0.74);font-size:12px;text-align:left;"
            "font-family:'Microsoft YaHei UI','Microsoft YaHei','Segoe UI Variable Text','Segoe UI',sans-serif;font-weight:400;}"
            "QPushButton:hover{background:rgba(255,255,255,0.105);color:rgba(255,255,255,0.96);}"
            "QPushButton:pressed{background:rgba(255,255,255,0.16);}"
        )
        self._sub_btn_style_light = scale_qss(
            "QPushButton{background:transparent;border-radius: 0; border:none;padding:6px 14px 6px 30px;margin:0px;min-height:20px;"
            "border-radius:6px;color:rgba(28,28,30,0.68);font-size:12px;text-align:left;"
            "font-family:'Microsoft YaHei UI','Microsoft YaHei','Segoe UI Variable Text','Segoe UI',sans-serif;font-weight:400;}"
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

            return is_win10()  # type: ignore[no-any-return]
        except Exception as exc:
            logger.debug("判断菜单阴影策略失败: %s", exc, exc_info=True)
            return False

    def _install_win10_companion_shadow(self) -> bool:
        if not self._uses_win10_companion_shadow():
            return False
        try:
            from ui.utils.window_effect import install_win10_window_shadow

            return install_win10_window_shadow(  # type: ignore[no-any-return]
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
                bg = QColor(SurfaceScale.bg_glass_dark_win10 if win10 else SurfaceScale.bg_glass_dark_win11)
                return bg, QColor(BorderScale.subtle_dark)
            return (
                QColor(SurfaceScale.bg_glass_light_win10 if win10 else SurfaceScale.bg_glass_light_win11),
                QColor(BorderScale.subtle_light),
            )
        if blur_applied:
            if theme == "dark":
                bg = QColor(BorderScale.strong_dark)
                bg.setAlpha(120)
                border = QColor(BorderScale.strong_dark)
                border.setAlpha(38)
                return bg, border
            bg = QColor(QtCompat.white)
            bg.setAlpha(120)
            border = QColor(QtCompat.black)
            border.setAlpha(20)
            return bg, border
        if theme == "dark":
            bg = QColor(SurfaceScale.bg_chrome_dark)
            border = QColor(QtCompat.white)
            border.setAlpha(int(0.1 * 255))
            return bg, border
        bg = QColor(QtCompat.white)
        bg.setAlpha(220)
        border = QColor(QtCompat.black)
        border.setAlpha(int(0.08 * 255))
        return bg, border

    def paintEvent(self, event):
        # noqa: paint_perf - hot-path paintEvent with cached state
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
        painter.fillRect(self.rect(), QColor(QtCompat.transparent))
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
        pen = make_cosmetic_pen(border, 1)
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
