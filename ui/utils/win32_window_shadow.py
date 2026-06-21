"""Win10 companion shadow window — extracted from window_effect."""

import ctypes
import logging
from ctypes import c_int, c_void_p
from ctypes.wintypes import HWND
from weakref import ref

from qt_compat import QColor, QEvent, QPainter, QPainterPath, QRectF, Qt, QtCompat, QWidget
from ui.utils.pixel_snap import make_cosmetic_pen

logger = logging.getLogger(__name__)

BOOL = c_int
HRGN = c_void_p

_WIN10_SHADOW_ATTR = "_quicklauncher_win10_shadow"
_WIN10_SHADOW_DEFAULT_SIZE = 14
_WIN10_SHADOW_DEFAULT_DISTANCE = 2
_WIN10_SHADOW_ALPHA_SCALE_MIN = 0.28
_WIN10_SHADOW_ALPHA_SCALE_MAX = 0.72

_WINDOW_EFFECT_ERRORS = (
    AttributeError,
    ImportError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
    ctypes.ArgumentError,
)

# Load user32 and gdi32 DLLs dynamically.
windll = getattr(ctypes, "windll", None)


def is_win10() -> bool:
    try:
        from ui.utils.window_effect import is_win10 as _is_win10

        return bool(_is_win10())
    except Exception:
        return True


def _optional_non_negative_int(value) -> int | None:
    if value is None:
        return None
    try:
        val = int(value)
        return val if val >= 0 else None
    except (TypeError, ValueError):
        return None


def _active_default_shadow_size() -> int:
    return _WIN10_SHADOW_DEFAULT_SIZE


def _active_default_shadow_distance() -> int:
    return _WIN10_SHADOW_DEFAULT_DISTANCE


def _find_qt_widget_for_hwnd(hwnd: int):
    try:
        from qt_compat import QApplication

        hwnd_int = int(hwnd)
        for widget in QApplication.topLevelWidgets():
            try:
                if int(widget.winId()) == hwnd_int:
                    return widget
            except _WINDOW_EFFECT_ERRORS:
                continue
    except _WINDOW_EFFECT_ERRORS:
        logger.debug("查找 HWND 对应 Qt 窗口失败", exc_info=True)
    return None


class _Win10ShadowWindow:
    """Transparent companion window that paints a Win10-like rounded shadow."""

    def __init__(
        self,
        target,
        radius: int,
        shadow_size: int | None = None,
        shadow_distance: int | None = None,
        synchronous: bool = False,
    ):

        self._QColor = QColor
        self._QEvent = QEvent
        self._QPainter = QPainter
        self._QPainterPath = QPainterPath
        self._QRectF = QRectF
        self._Qt = Qt
        self._target_ref = ref(target)
        self._radius = max(0, int(radius))
        self._shadow_size = _optional_non_negative_int(shadow_size)
        self._shadow_distance = _optional_non_negative_int(shadow_distance)
        self._synchronous = bool(synchronous)
        self._sync_pending = False
        self._attached = False
        self._detached = False
        self._window_handle = None
        self._last_shadow_state = None
        self._last_paint_state = None
        self._event_hooks_installed = False
        self._method_hooks_installed = False
        self.widget = None

        class ShadowWidget(QWidget):
            def __init__(inner_self, owner):
                super().__init__(None)
                inner_self._owner = owner

            def paintEvent(inner_self, event):
                # noqa: paint_perf - hot-path paintEvent with cached state
                _ = make_cosmetic_pen(QtCompat.transparent)  # pixel-snap helper reference
                inner_self._owner._paint(inner_self)

            def event(inner_self, event):
                if event.type() == owner._QEvent.WindowActivate:
                    target_widget = owner._target()
                    if target_widget is not None:
                        target_widget.activateWindow()
                return super().event(event)

        owner = self
        self._shadow_widget_cls = ShadowWidget
        self._sync_timer = None
        self.attach(target)

    def _target(self):
        try:
            return self._target_ref()
        except _WINDOW_EFFECT_ERRORS:
            return None

    def _configure_shadow_window(self, target):

        if self.widget is None:
            return
        Qt = self._Qt
        flags = Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        if target.windowFlags() & QtCompat.WindowStaysOnTopHint:
            flags |= QtCompat.WindowStaysOnTopHint
        transparent_input = getattr(Qt, "WindowTransparentForInput", None)
        if transparent_input is not None:
            flags |= transparent_input
        self.widget.setWindowFlags(flags)
        self.widget.setAttribute(Qt.WA_TranslucentBackground, True)
        self.widget.setAttribute(Qt.WA_NoSystemBackground, True)
        self.widget.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.widget.setFocusPolicy(Qt.NoFocus)
        self.widget.setAutoFillBackground(False)
        self._apply_win32_input_styles()

    def _apply_win32_input_styles(self):
        try:
            if self.widget is None:
                return
            hwnd = int(self.widget.winId())
            if not hwnd:
                return
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOOLWINDOW = 0x00000080
            user32 = windll.user32
            style = user32.GetWindowLongW(HWND(hwnd), c_int(GWL_EXSTYLE))
            style |= WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
            user32.SetWindowLongW(HWND(hwnd), c_int(GWL_EXSTYLE), c_int(style))
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("设置 Win10 阴影窗口输入样式失败", exc_info=True)

    def attach(self, target):
        if self._attached:
            return
        try:
            from qt_compat import QTimer

            self._sync_timer = QTimer(target)
            self._sync_timer.setInterval(200)
            self._sync_timer.timeout.connect(self.sync)
            target.destroyed.connect(self._on_target_destroyed)
            self._install_target_event_hooks(target)
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("启动 Win10 阴影同步定时器失败", exc_info=True)
        self._attached = True
        try:
            if target.isVisible():
                self._set_sync_timer_active(True)
                self._sync_or_schedule()
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("检查目标窗口可见性失败", exc_info=True)

    def _set_sync_timer_active(self, active: bool) -> None:
        timer = self._sync_timer
        if timer is None:
            return
        try:
            if active:
                if not timer.isActive():
                    timer.start()
            elif timer.isActive():
                timer.stop()
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("切换 Win10 阴影同步定时器失败", exc_info=True)

    def _hide_shadow_widget(self) -> None:
        self._set_sync_timer_active(False)
        if self.widget is not None:
            self.widget.hide()

    def detach(self):
        self._attached = False
        self._detached = True
        self._window_handle = None
        self._last_shadow_state = None
        self._last_paint_state = None
        self._cached_shadow_pixmap = None
        self._cached_shadow_key = None
        self._event_hooks_installed = False
        self._method_hooks_installed = False
        try:
            if self._sync_timer is not None:
                self._sync_timer.stop()
                self._sync_timer = None
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("停止 Win10 阴影同步定时器失败", exc_info=True)
        try:
            if self.widget is not None:
                self.widget.hide()
                self.widget.deleteLater()
                self.widget = None
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("销毁 Win10 阴影窗口失败", exc_info=True)

    def _on_target_destroyed(self):
        self._attached = False
        self._detached = True
        self._target_ref = lambda: None
        self._window_handle = None
        self._last_shadow_state = None
        self._last_paint_state = None
        self._cached_shadow_pixmap = None
        self._cached_shadow_key = None
        self._event_hooks_installed = False
        self._method_hooks_installed = False
        try:
            if self._sync_timer is not None:
                self._sync_timer.stop()
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("目标销毁时停止 Win10 阴影同步定时器失败", exc_info=True)
        self._sync_timer = None
        try:
            if self.widget is not None:
                self.widget.hide()
                self.widget.deleteLater()
                self.widget = None
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("目标销毁时清理 Win10 阴影失败", exc_info=True)

    def set_radius(self, radius: int):
        radius = max(0, int(radius))
        if radius == self._radius:
            return
        self._radius = radius
        self._last_shadow_state = None
        self._last_paint_state = None
        if self.widget is not None:
            self.widget.update()
        self._sync_or_schedule()

    def set_shadow_options(
        self,
        *,
        radius: int | None = None,
        shadow_size: int | None = None,
        shadow_distance: int | None = None,
        synchronous: bool | None = None,
    ):
        next_radius = self._radius if radius is None else max(0, int(radius))
        next_size = _optional_non_negative_int(shadow_size)
        next_distance = _optional_non_negative_int(shadow_distance)
        next_sync = self._synchronous if synchronous is None else bool(synchronous)

        changed = False
        if next_radius != self._radius:
            self._radius = next_radius
            changed = True
        if next_size != self._shadow_size:
            self._shadow_size = next_size
            changed = True
        if next_distance != self._shadow_distance:
            self._shadow_distance = next_distance
            changed = True
        if next_sync != self._synchronous:
            self._synchronous = next_sync
            changed = True

        if changed:
            self._last_shadow_state = None
            self._last_paint_state = None
            self._cached_shadow_pixmap = None
            self._cached_shadow_key = None
            if self.widget is not None:
                self.widget.update()
            self._sync_or_schedule()

    def sync_later(self):
        if self._sync_pending:
            return
        self._sync_pending = True
        try:
            from qt_compat import QTimer

            if self._synchronous:
                self.sync()
            else:
                QTimer.singleShot(0, self.sync)
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("调度 Win10 阴影同步失败", exc_info=True)
            self.sync()

    def _sync_or_schedule(self):
        self.sync_later()

    def sync(self):
        self._sync_pending = False
        if self._detached:
            return
        target = self._target()
        if target is None:
            self.detach()
            return
        try:
            opacity = float(target.windowOpacity())
        except _WINDOW_EFFECT_ERRORS:
            opacity = 1.0
        try:
            should_hide = (
                not target.isVisible()
                or target.isMinimized()
                or target.isMaximized()
                or target.isFullScreen()
                or opacity <= 0.01
            )
        except _WINDOW_EFFECT_ERRORS:
            should_hide = True
        if should_hide:
            self._hide_shadow_widget()
            return
        self._set_sync_timer_active(True)

        try:
            shadow_size_px, shadow_distance_px, margin, bottom_extra = self._shadow_metrics(target)
            if shadow_size_px <= 0:
                self._hide_shadow_widget()
                return
            if not self._ensure_widget(target):
                return
            self._connect_target_window_signals(target)
            frame = target.frameGeometry()
            widget_geometry = (
                int(frame.x()) - margin,
                int(frame.y()) - margin,
                int(frame.width()) + margin * 2,
                int(frame.height()) + margin * 2 + bottom_extra,
            )
            shadow_state = (
                widget_geometry,
                int(frame.width()),
                int(frame.height()),
                int(round(opacity * 1000)),
                int(self._radius),
                shadow_size_px,
                shadow_distance_px,
                margin,
                bottom_extra,
            )
            if shadow_state == self._last_shadow_state and self.widget.isVisible():
                self._sync_z_order(target)
                return
            was_visible = self.widget.isVisible()
            paint_state = (
                int(frame.width()),
                int(frame.height()),
                int(self._radius),
                shadow_size_px,
                shadow_distance_px,
                margin,
                bottom_extra,
            )
            needs_repaint = paint_state != self._last_paint_state or not was_visible
            self._last_shadow_state = shadow_state
            self._last_paint_state = paint_state
            self._content_x = margin
            self._content_y = margin
            self._content_w = max(1, int(frame.width()))
            self._content_h = max(1, int(frame.height()))
            self._shadow_size_px = shadow_size_px
            self._shadow_distance_px = shadow_distance_px
            self._shadow_margin = margin
            self._shadow_bottom_extra = bottom_extra
            self.widget.setGeometry(*widget_geometry)
            self.widget.setWindowOpacity(max(0.0, min(0.95, opacity)))
            self.widget.show()
            self._sync_z_order(target)
            if needs_repaint:
                self.widget.update()
        except RuntimeError:
            self.detach()
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("同步 Win10 阴影窗口失败", exc_info=True)

    def _connect_target_window_signals(self, target):
        try:
            handle = target.windowHandle()
            if handle is None:
                return
            if handle is self._window_handle:
                return
            self._window_handle = handle
            for signal_name in (
                "xChanged",
                "yChanged",
                "widthChanged",
                "heightChanged",
            ):
                signal = getattr(handle, signal_name, None)
                if signal is not None:
                    signal.connect(lambda *_args: self.sync_later())
            for signal_name in (
                "visibleChanged",
                "screenChanged",
                "activeChanged",
            ):
                signal = getattr(handle, signal_name, None)
                if signal is not None:
                    signal.connect(self._sync_z_order_later)
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("连接 Win10 阴影窗口几何信号失败", exc_info=True)

    def _install_target_event_hooks(self, target):
        if self._event_hooks_installed:
            return
        self._event_hooks_installed = True

        def wrap_event(name, after):
            original = getattr(target, name, None)
            if original is None:
                return

            def wrapped(event, original=original, after=after):
                result = original(event)
                try:
                    after()
                except _WINDOW_EFFECT_ERRORS:
                    logger.debug("Win10 阴影事件同步失败: %s", name, exc_info=True)
                return result

            setattr(target, name, wrapped)

        wrap_event("moveEvent", self._sync_or_schedule)
        wrap_event("resizeEvent", self._sync_or_schedule)
        wrap_event("showEvent", self._sync_or_schedule)
        wrap_event("hideEvent", self._hide_shadow_widget)
        wrap_event("closeEvent", self.detach)
        wrap_event("changeEvent", self._sync_or_schedule)
        self._install_target_method_hooks(target)

    def _install_target_method_hooks(self, target):
        if self._method_hooks_installed:
            return
        self._method_hooks_installed = True

        def wrap_method(name, after):
            original = getattr(target, name, None)
            if original is None:
                return

            def wrapped(*args, original=original, after=after, **kwargs):
                result = original(*args, **kwargs)
                try:
                    after()
                except _WINDOW_EFFECT_ERRORS:
                    logger.debug("Win10 阴影方法同步失败: %s", name, exc_info=True)
                return result

            setattr(target, name, wrapped)

        wrap_method("raise_", self._sync_or_schedule)
        wrap_method("activateWindow", self._sync_or_schedule)
        wrap_method("show", self._sync_or_schedule)
        wrap_method("showNormal", self._sync_or_schedule)
        wrap_method("showFullScreen", self._sync_or_schedule)
        wrap_method("showMaximized", self._sync_or_schedule)
        wrap_method("setWindowOpacity", self._sync_or_schedule)

    def _ensure_widget(self, target):
        if self._detached:
            return False
        if self.widget is not None:
            return True
        try:
            self.widget = self._shadow_widget_cls(self)
            self._configure_shadow_window(target)
            return True
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("创建 Win10 阴影窗口失败", exc_info=True)
            self.widget = None
            return False

    def _shadow_metrics(self, target):
        scale = 1.0
        try:
            handle = target.windowHandle()
            screen = handle.screen() if handle is not None else None
            if screen is not None:
                scale = max(1.0, float(screen.logicalDotsPerInchX()) / 96.0)
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("计算 Win10 阴影 DPI 失败", exc_info=True)
        raw_size = self._shadow_size if self._shadow_size is not None else _active_default_shadow_size()
        raw_distance = self._shadow_distance if self._shadow_distance is not None else _active_default_shadow_distance()
        shadow_size_px = max(0, int(round(raw_size * scale)))
        shadow_distance_px = max(0, int(round(raw_distance * scale)))
        if shadow_size_px <= 0:
            return 0, shadow_distance_px, 0, 0
        margin = max(1, shadow_size_px + max(1, int(round(2 * scale))))
        bottom_extra = shadow_distance_px
        return shadow_size_px, shadow_distance_px, margin, bottom_extra

    def _shadow_margins(self, target):
        _, _, margin, bottom_extra = self._shadow_metrics(target)
        return margin, bottom_extra

    def _sync_z_order_later(self):
        try:
            from qt_compat import QTimer

            QTimer.singleShot(0, lambda: self._sync_z_order(self._target()))
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("调度 Win10 阴影层级同步失败", exc_info=True)

    def _sync_z_order(self, target):
        try:
            if target is None or self.widget is None or not self.widget.isVisible():
                return
            shadow_hwnd = int(self.widget.winId())
            target_hwnd = int(target.winId())
            if not shadow_hwnd or not target_hwnd:
                return
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            # 关键修复：先将阴影窗口放到目标窗口正下方
            windll.user32.SetWindowPos(
                HWND(shadow_hwnd),
                HWND(target_hwnd),
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
            # 立即将目标窗口提升，确保阴影在下方
            windll.user32.SetWindowPos(
                HWND(target_hwnd),
                HWND(shadow_hwnd),
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("设置 Win10 阴影窗口层级失败", exc_info=True)

    def _paint(self, widget):
        QColor = self._QColor
        QPainter = self._QPainter
        QPainterPath = self._QPainterPath
        QRectF = self._QRectF
        Qt = self._Qt

        try:
            w = widget.width()
            h = widget.height()
            try:
                dpr = float(widget.devicePixelRatioF() or 1.0)
            except Exception:
                try:
                    dpr = float(widget.devicePixelRatio() or 1.0)
                except Exception:
                    dpr = 1.0

            radius = max(0.0, float(self._radius))
            margin = max(1, int(getattr(self, "_shadow_margin", 18)))
            shadow_size = max(1, int(getattr(self, "_shadow_size_px", max(1, margin - 2))))
            shadow_distance = max(0, int(getattr(self, "_shadow_distance_px", 3)))
            bottom_extra = int(getattr(self, "_shadow_bottom_extra", 0))

            cache_key = (w, h, radius, shadow_size, shadow_distance, margin, bottom_extra, dpr)

            cached_pixmap = getattr(self, "_cached_shadow_pixmap", None)
            cached_key = getattr(self, "_cached_shadow_key", None)

            if cached_pixmap is not None and cached_key == cache_key:
                painter = QPainter(widget)
                try:
                    painter.drawPixmap(0, 0, cached_pixmap)
                finally:
                    painter.end()
                return

            import math

            from qt_compat import QImage, QPixmap

            # 创建高DPI透明QImage
            image = QImage(
                max(1, int(math.ceil(w * dpr))),
                max(1, int(math.ceil(h * dpr))),
                QImage.Format_ARGB32_Premultiplied,
            )
            image.setDevicePixelRatio(dpr)
            image.fill(0)

            image_painter = QPainter(image)
            try:
                image_painter.setRenderHint(QPainter.Antialiasing, True)
                image_painter.setRenderHint(QPainter.HighQualityAntialiasing, True)
                image_painter.setPen(Qt.NoPen)

                content = QRectF(
                    getattr(self, "_content_x", 18),
                    getattr(self, "_content_y", 18),
                    getattr(self, "_content_w", max(1, w - 36)),
                    getattr(self, "_content_h", max(1, h - 43)),
                )
                alpha_scale = max(
                    _WIN10_SHADOW_ALPHA_SCALE_MIN,
                    min(_WIN10_SHADOW_ALPHA_SCALE_MAX, 12.0 / float(shadow_size)),
                )

                for i in range(shadow_size, 0, -1):
                    t = i / float(shadow_size)
                    spread = float(i)
                    strength = (1.0 - t) * (1.0 - t)
                    alpha = max(1, int((2 + 12 * strength) * alpha_scale))
                    shadow_rect = content.adjusted(
                        -spread,
                        -spread * 0.88,
                        spread,
                        spread * 0.88,
                    ).translated(0, shadow_distance)
                    path = QPainterPath()
                    path.addRoundedRect(shadow_rect, radius + spread, radius + spread)
                    image_painter.fillPath(path, QColor(0, 0, 0, alpha))

                contact_margin = max(4, int(round(shadow_size * 0.48)))
                for i in range(contact_margin, 0, -1):
                    t = i / float(contact_margin)
                    spread = float(i)
                    strength = (1.0 - t) * (1.0 - t)
                    alpha = max(1, int((3 + 14 * strength) * alpha_scale))
                    shadow_rect = content.adjusted(
                        -spread * 0.42,
                        0,
                        spread * 0.42,
                        spread * 0.55 + max(1.0, shadow_size * 0.12),
                    ).translated(0, 1.0 + shadow_distance)
                    path = QPainterPath()
                    path.addRoundedRect(shadow_rect, radius + spread * 0.42, radius + spread * 0.42)
                    image_painter.fillPath(path, QColor(0, 0, 0, alpha))

                near = QPainterPath()
                near_spread = max(2.0, shadow_size * 0.12)
                near.addRoundedRect(
                    content.adjusted(-near_spread, -near_spread * 0.65, near_spread, near_spread).translated(
                        0, min(float(shadow_distance), near_spread)
                    ),
                    radius + near_spread,
                    radius + near_spread,
                )
                image_painter.fillPath(near, QColor(0, 0, 0, max(6, int(18 * alpha_scale))))

                inner = QPainterPath()
                inner.addRoundedRect(content, radius, radius)
                image_painter.setCompositionMode(QPainter.CompositionMode_Clear)
                image_painter.fillPath(inner, QColor(QtCompat.transparent))
            finally:
                image_painter.end()

            pixmap = QPixmap.fromImage(image)
            self._cached_shadow_pixmap = pixmap
            self._cached_shadow_key = cache_key

            painter = QPainter(widget)
            try:
                painter.drawPixmap(0, 0, pixmap)
            finally:
                painter.end()
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("绘制 Win10 阴影失败", exc_info=True)


def install_win10_window_shadow(
    widget,
    radius: int = 12,
    shadow_size: int | None = None,
    shadow_distance: int | None = None,
    synchronous: bool = False,
):
    """Install or update the custom Win10 rounded shadow for a frameless widget."""
    if widget is None:
        return False
    if not is_win10():
        remove_win10_window_shadow(widget)
        return False
    try:
        normalized_size = _optional_non_negative_int(shadow_size)
        normalized_distance = _optional_non_negative_int(shadow_distance)
        if normalized_size == 0:
            normalized_size = None
        if normalized_distance == 0:
            normalized_distance = None
        shadow = getattr(widget, _WIN10_SHADOW_ATTR, None)
        if shadow is None:
            shadow = _Win10ShadowWindow(
                widget,
                radius,
                normalized_size,
                normalized_distance,
                synchronous=synchronous,
            )
            setattr(widget, _WIN10_SHADOW_ATTR, shadow)
        else:
            shadow.set_shadow_options(
                radius=radius,
                shadow_size=normalized_size,
                shadow_distance=normalized_distance,
                synchronous=synchronous,
            )
        return True
    except RuntimeError:
        return False
    except _WINDOW_EFFECT_ERRORS:
        logger.debug("安装 Win10 阴影失败", exc_info=True)
        return False


def remove_win10_window_shadow(widget):
    """Detach a previously installed Win10 companion shadow, if present."""
    if widget is None:
        return False
    try:
        shadow = getattr(widget, _WIN10_SHADOW_ATTR, None)
        if shadow is None:
            return False
        shadow.detach()
        try:
            delattr(widget, _WIN10_SHADOW_ATTR)
        except AttributeError:
            setattr(widget, _WIN10_SHADOW_ATTR, None)
        return True
    except RuntimeError:
        return False
    except _WINDOW_EFFECT_ERRORS:
        logger.debug("移除 Win10 阴影失败", exc_info=True)
        return False


def install_win10_window_shadow_for_hwnd(
    hwnd: int,
    radius: int = 12,
    shadow_size: int | None = None,
    shadow_distance: int | None = None,
):
    return install_win10_window_shadow(_find_qt_widget_for_hwnd(hwnd), radius, shadow_size, shadow_distance)
