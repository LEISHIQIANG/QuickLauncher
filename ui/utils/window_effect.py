import ctypes
import logging
import sys
from ctypes import POINTER, Structure, byref, c_bool, c_int, c_void_p, sizeof, windll
from ctypes.wintypes import DWORD, HWND, ULONG, WCHAR
from weakref import ref

logger = logging.getLogger(__name__)

BOOL = c_int
HRGN = c_void_p

# Windows 版本缓存
_windows_version_cache = None
_WIN10_SHADOW_ATTR = "_quicklauncher_win10_shadow"
_WIN10_SHADOW_DEFAULT_SIZE = 14
_WIN10_SHADOW_DEFAULT_DISTANCE = 2
_WIN10_SHADOW_ALPHA_SCALE_MIN = 0.28
_WIN10_SHADOW_ALPHA_SCALE_MAX = 0.72
_win10_shadow_config_size = None
_win10_shadow_config_distance = None
_WINDOW_EFFECT_ERRORS = (
    AttributeError,
    ImportError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
    ctypes.ArgumentError,
)


class _RTL_OSVERSIONINFOW(Structure):
    _fields_ = [
        ("dwOSVersionInfoSize", DWORD),
        ("dwMajorVersion", DWORD),
        ("dwMinorVersion", DWORD),
        ("dwBuildNumber", DWORD),
        ("dwPlatformId", DWORD),
        ("szCSDVersion", WCHAR * 128),
    ]


def _classify_windows_build(build: int) -> str:
    if build >= 22000:
        return "win11"
    if build >= 10240:
        return "win10"
    return "win7"


def _get_windows_build_from_rtl() -> int | None:
    """Return the real NT build number without compatibility virtualization."""
    try:
        version = _RTL_OSVERSIONINFOW()
        version.dwOSVersionInfoSize = sizeof(version)
        status = windll.ntdll.RtlGetVersion(byref(version))
        if status == 0 and version.dwBuildNumber:
            return int(version.dwBuildNumber)
    except _WINDOW_EFFECT_ERRORS:
        logger.debug("RtlGetVersion failed", exc_info=True)
    return None


def get_windows_version() -> str:
    """获取 Windows 版本信息（带缓存）"""
    global _windows_version_cache
    if _windows_version_cache is not None:
        return _windows_version_cache

    try:
        build = _get_windows_build_from_rtl()
        if build is None:
            version = sys.getwindowsversion()
            build = int(version.build)
        _windows_version_cache = _classify_windows_build(build)
    except _WINDOW_EFFECT_ERRORS:
        logger.debug("get_windows_version failed", exc_info=True)
        _windows_version_cache = "win10"

    return _windows_version_cache


def is_win11() -> bool:
    """检测是否为 Windows 11"""
    return get_windows_version() == "win11"


def is_win10() -> bool:
    """检测是否为 Windows 10"""
    return get_windows_version() == "win10"


def is_glass_background_supported() -> bool:
    """Detect whether the current system supports WDA_EXCLUDEFROMCAPTURE.

    SetWindowDisplayAffinity's WDA_EXCLUDEFROMCAPTURE flag (0x11) is documented
    as supported from Windows 10 2004 (build 19041), but real-world testing
    shows it fails on many Win10 22H2 (build 19045) combinations of GPU drivers,
    remote desktop, and VDI. The DLL side immediately returns
    GLASS_ERROR_DISPLAY_AFFINITY and refuses to start the render thread, which
    triggers tray error bubbles on every popup show.

    We therefore only expose the glass background option on Windows 11
    (build >= 22000). Win10 users will not see the option and any stored
    ``bg_mode="glass"`` config will be silently downgraded to ``"theme"``.

    Returns:
        bool: True when the glass background can be safely enabled.
    """
    return is_win11()


def _qpaint_composition_mode(name: str):
    try:
        from qt_compat import QPainter

        enum = getattr(QPainter, "CompositionMode", None)
        if enum is not None:
            value = getattr(enum, name, None)
            if value is not None:
                return value
            value = getattr(enum, f"CompositionMode_{name}", None)
            if value is not None:
                return value
        return getattr(QPainter, f"CompositionMode_{name}", None)
    except _WINDOW_EFFECT_ERRORS:
        logger.debug("_qpaint_composition_mode failed", exc_info=True)
        return None


def paint_win10_rounded_surface(
    painter,
    widget,
    bg_color,
    border_color,
    radius: int,
    *,
    inset: float = 1.0,
    min_bg_alpha: int = 248,
    max_border_alpha: int = 220,
):
    """Paint a Win10-friendly opaque rounded surface with antialiased edges.

    Win10 does not have Win11's DWM-rounded frameless windows. The cleanest
    result for Qt transparent windows is per-pixel alpha painting: clear the
    backing store, draw an almost opaque rounded path, and avoid 1-bit masks
    or GDI window regions.
    """
    try:
        from qt_compat import QColor, QPainterPath, QPen, QRectF, Qt, QtCompat

        painter.setRenderHint(QtCompat.Antialiasing, True)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing, True)
        painter.setRenderHint(QtCompat.SmoothPixmapTransform, True)

        source_mode = _qpaint_composition_mode("Source")
        source_over_mode = _qpaint_composition_mode("SourceOver")
        if source_mode is not None:
            painter.setCompositionMode(source_mode)
        painter.fillRect(widget.rect(), QColor(Qt.transparent))
        if source_over_mode is not None:
            painter.setCompositionMode(source_over_mode)

        rect = QRectF(widget.rect()).adjusted(inset, inset, -inset, -inset)
        r = max(0.0, float(radius))
        path = QPainterPath()
        path.addRoundedRect(rect, r, r)

        fill = QColor(bg_color)
        fill.setAlpha(max(0, min(255, max(int(fill.alpha()), int(min_bg_alpha)))))
        painter.fillPath(path, fill)

        border = QColor(border_color)
        border.setAlpha(max(0, min(int(border.alpha()), int(max_border_alpha))))
        pen = QPen(border, 1.0)
        pen.setJoinStyle(QtCompat.RoundJoin)
        pen.setCapStyle(QtCompat.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QtCompat.NoBrush)
        painter.drawPath(path)
        return True
    except _WINDOW_EFFECT_ERRORS as exc:
        logger.debug("绘制 Win10 圆角背景失败: %s", exc, exc_info=True)
        return False


def _optional_non_negative_int(value):
    if value is None:
        return None
    try:
        return max(0, int(value))
    except _WINDOW_EFFECT_ERRORS:
        return None


def _shadow_override_value(value):
    value = _optional_non_negative_int(value)
    if value is None or value <= 0:
        return None
    return value


def _active_default_shadow_size() -> int:
    return _win10_shadow_config_size if _win10_shadow_config_size is not None else _WIN10_SHADOW_DEFAULT_SIZE


def _active_default_shadow_distance() -> int:
    if _win10_shadow_config_distance is not None:
        return _win10_shadow_config_distance
    return _WIN10_SHADOW_DEFAULT_DISTANCE


def refresh_win10_window_shadows() -> None:
    """Refresh existing Win10 companion shadows after global defaults change."""
    try:
        from qt_compat import QApplication

        app = QApplication.instance()
        if app is None:
            return
        for widget in QApplication.topLevelWidgets():
            try:
                shadow = getattr(widget, _WIN10_SHADOW_ATTR, None)
                if shadow is None:
                    continue
                shadow._last_shadow_state = None
                shadow._last_paint_state = None
                if shadow.widget is not None:
                    shadow.widget.update()
                shadow.sync_later()
            except _WINDOW_EFFECT_ERRORS:
                logger.debug("刷新 Win10 全局阴影失败", exc_info=True)
    except _WINDOW_EFFECT_ERRORS:
        logger.debug("遍历 Win10 全局阴影失败", exc_info=True)


def configure_win10_window_shadow(shadow_size: int | None = None, shadow_distance: int | None = None) -> bool:
    """Configure global Win10 self-painted shadow defaults.

    ``None`` or ``0`` means automatic defaults. Positive values override the
    defaults for every popup that uses the shared Win10 companion shadow.
    """
    global _win10_shadow_config_size, _win10_shadow_config_distance
    next_size = _shadow_override_value(shadow_size)
    next_distance = _shadow_override_value(shadow_distance)
    if next_size == _win10_shadow_config_size and next_distance == _win10_shadow_config_distance:
        return False
    _win10_shadow_config_size = next_size
    _win10_shadow_config_distance = next_distance
    if is_win10():
        refresh_win10_window_shadows()
    return True


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
        from qt_compat import QColor, QEvent, QPainter, QPainterPath, QRectF, Qt, QWidget

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
        from qt_compat import QtCompat

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
        self._target_ref = lambda: None
        self._window_handle = None
        self._last_shadow_state = None
        self._last_paint_state = None
        self._cached_shadow_pixmap = None
        self._cached_shadow_key = None
        self._event_hooks_installed = False
        self._method_hooks_installed = False
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
        next_synchronous = self._synchronous if synchronous is None else bool(synchronous)
        if (
            next_radius == self._radius
            and next_size == self._shadow_size
            and next_distance == self._shadow_distance
            and next_synchronous == self._synchronous
        ):
            return
        self._radius = next_radius
        self._shadow_size = next_size
        self._shadow_distance = next_distance
        self._synchronous = next_synchronous
        self._last_shadow_state = None
        self._last_paint_state = None
        if self.widget is not None:
            self.widget.update()
        self._sync_or_schedule()

    def _sync_or_schedule(self):
        if self._synchronous:
            self.sync()
        else:
            self.sync_later()

    def sync_later(self):
        if self._sync_pending:
            return
        self._sync_pending = True
        try:
            from qt_compat import QTimer

            target = self._target()
            if target is not None and target.isVisible():
                self._set_sync_timer_active(True)
            QTimer.singleShot(0, self.sync)
        except _WINDOW_EFFECT_ERRORS:
            self._sync_pending = False
            logger.debug("调度 Win10 阴影同步失败", exc_info=True)

    def sync(self):
        self._sync_pending = False
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

            from qt_compat import QImage, QPixmap, Qt

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
                image_painter.fillPath(inner, QColor(Qt.transparent))
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


def install_win10_window_shadow(
    widget,
    radius: int = 12,
    shadow_size: int | None = None,
    shadow_distance: int | None = None,
    synchronous: bool = False,
):
    """Install or update the custom Win10 rounded shadow for a frameless widget.

    ``shadow_size`` and ``shadow_distance`` use ``None`` or ``0`` as auto mode,
    so existing configurations get the default Win11-like shadow instead of
    silently disabling it.
    """
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


class WindowCompositionAttributeData(Structure):
    _fields_ = [
        ("Attribute", DWORD),
        ("Data", c_void_p),
        ("SizeOfData", ULONG),
    ]


class DWM_BLURBEHIND(Structure):
    _fields_ = [("dwFlags", DWORD), ("fEnable", c_bool), ("hRgnBlur", c_void_p), ("fTransitionOnMaximized", c_bool)]


class AccentPolicy(Structure):
    _fields_ = [
        ("AccentState", DWORD),
        ("AccentFlags", DWORD),
        ("GradientColor", DWORD),
        ("AnimationId", DWORD),
    ]


class WindowEffect:
    """Windows 窗口特效工具类 (Acrylic/Blur/Aero)"""

    # 状态常量
    ACCENT_DISABLED = 0
    ACCENT_ENABLE_GRADIENT = 1
    ACCENT_ENABLE_TRANSPARENTGRADIENT = 2
    ACCENT_ENABLE_BLURBEHIND = 3  # 传统 Aero Blur
    ACCENT_ENABLE_ACRYLICBLURBEHIND = 4  # Acrylic (Win10 1709+)
    ACCENT_INVALID_STATE = 5

    # 组合属性常量
    WCA_ACCENT_POLICY = 19

    DWMWCP_DEFAULT = 0
    DWMWCP_DONOTROUND = 1
    DWMWCP_ROUND = 2
    DWMWCP_ROUNDSMALL = 3

    def __init__(self):
        self.user32 = windll.user32
        self.gdi32 = windll.gdi32
        self.dwmapi = windll.dwmapi
        self.SetWindowCompositionAttribute = self.user32.SetWindowCompositionAttribute
        self.SetWindowCompositionAttribute.argtypes = [HWND, POINTER(WindowCompositionAttributeData)]
        self.SetWindowCompositionAttribute.restype = c_int

        try:
            self.user32.IsWindow.argtypes = [HWND]
            self.user32.IsWindow.restype = BOOL
        except _WINDOW_EFFECT_ERRORS as e:
            logger.debug("设置 IsWindow argtypes 失败: %s", e)

        try:
            self.user32.GetDpiForWindow.argtypes = [HWND]
            self.user32.GetDpiForWindow.restype = ctypes.c_uint
        except _WINDOW_EFFECT_ERRORS as e:
            logger.debug("设置 GetDpiForWindow argtypes 失败: %s", e)

        try:
            self.gdi32.CreateRoundRectRgn.argtypes = [c_int, c_int, c_int, c_int, c_int, c_int]
            self.gdi32.CreateRoundRectRgn.restype = HRGN
        except _WINDOW_EFFECT_ERRORS as e:
            logger.debug("设置 CreateRoundRectRgn argtypes 失败: %s", e)

        try:
            self.gdi32.DeleteObject.argtypes = [c_void_p]
            self.gdi32.DeleteObject.restype = BOOL
        except _WINDOW_EFFECT_ERRORS as e:
            logger.debug("设置 DeleteObject argtypes 失败: %s", e)

        try:
            self.user32.SetWindowRgn.argtypes = [HWND, HRGN, BOOL]
            self.user32.SetWindowRgn.restype = c_int
        except _WINDOW_EFFECT_ERRORS as e:
            logger.debug("设置 SetWindowRgn argtypes 失败: %s", e)

        try:
            self.user32.MonitorFromWindow.argtypes = [HWND, DWORD]
            self.user32.MonitorFromWindow.restype = c_void_p
        except _WINDOW_EFFECT_ERRORS as e:
            logger.debug("设置 MonitorFromWindow argtypes 失败: %s", e)

    def is_win11(self):
        """实例方法：检测是否为 Windows 11"""
        return is_win11()

    def is_win10(self):
        """实例方法：检测是否为 Windows 10"""
        return is_win10()

    def _is_window(self, hwnd: int) -> bool:
        try:
            return bool(self.user32.IsWindow(HWND(int(hwnd))))
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("_is_window check failed", exc_info=True)
            return bool(hwnd)

    def _get_dpi_scale(self, hwnd: int):
        """获取窗口当前的 DPI 缩放比例"""
        try:
            hwnd_val = int(hwnd)
            if not self._is_window(hwnd_val):
                return 1.0

            # 1. 尝试 GetDpiForWindow (Win10 1607+)
            dpi = 0
            if hasattr(self.user32, "GetDpiForWindow"):
                dpi = self.user32.GetDpiForWindow(HWND(hwnd_val))

            # 2. 如果 GetDpiForWindow 没拿到或者返回 96 (可能是窗口还未完全切换 DPI 上下文)
            # 尝试通过 MonitorFromWindow 获取
            if dpi <= 96:
                h_monitor = self.user32.MonitorFromWindow(HWND(hwnd_val), 2)  # MONITOR_DEFAULTTONEAREST
                if h_monitor:
                    try:
                        dpi_x = ctypes.c_uint()
                        dpi_y = ctypes.c_uint()
                        # PROCESS_DPI_AWARE = 0
                        windll.shcore.GetDpiForMonitor(h_monitor, 0, byref(dpi_x), byref(dpi_y))
                        if dpi_x.value > 0:
                            dpi = dpi_x.value
                    except _WINDOW_EFFECT_ERRORS as exc:
                        logger.debug("获取显示器DPI失败: %s", exc, exc_info=True)

            if dpi > 0:
                return float(dpi) / 96.0
        except _WINDOW_EFFECT_ERRORS as exc:
            logger.debug("计算DPI缩放失败: %s", exc, exc_info=True)
        return 1.0

    def set_acrylic(
        self, hwnd: int, gradient_color: str = None, enable: bool = True, animation_id: int = 0, blur: bool = True  # type: ignore[assignment]
    ):
        """
        设置亚克力/模糊效果
        :param hwnd: 窗口句柄 (int)
        :param gradient_color: 16进制颜色字符串 (RRGGBB 或 AARRGGBB)，如果为 None 则使用默认
        :param enable: 是否启用
        :param blur: 是否启用模糊 (True=Acrylic, False=Transparent)
        """
        if is_win10() and enable:
            # Win10 的 AccentPolicy/Acrylic 在 Qt 透明无边框窗口上容易和
            # 高 DPI 缩放、窗口区域裁剪叠加出黑色背景或错位遮罩。
            # 该平台改由 Qt paintEvent 绘制半透明背景，Win11 保留原生效果。
            return

        policy = AccentPolicy()

        if not enable:
            policy.AccentState = self.ACCENT_DISABLED
            policy.AccentFlags = 0
            policy.GradientColor = 0
            policy.AnimationId = 0
        else:
            # 根据 blur 参数选择策略
            if blur:
                policy.AccentState = self.ACCENT_ENABLE_ACRYLICBLURBEHIND
            else:
                policy.AccentState = self.ACCENT_ENABLE_TRANSPARENTGRADIENT

            policy.AccentFlags = 2  # 似乎有些标志位，2 比较常用

            # 颜色处理 (Windows 需要 AABBGGRR 格式的 DWORD)
            # 输入通常是 RGB 或 ARGB
            # GradientColor: AABBGGRR

            if gradient_color:
                # 清洗字符串
                gradient_color = gradient_color.lstrip("#")
                if len(gradient_color) == 6:
                    # RRGGBB -> 默认 Alpha 0xCC (204)
                    r = int(gradient_color[0:2], 16)
                    g = int(gradient_color[2:4], 16)
                    b = int(gradient_color[4:6], 16)
                    a = 10  # 默认很透明
                elif len(gradient_color) == 8:
                    # AARRGGBB
                    # 注意：通常配置里的 hex 是 ARGB，但 windows 可能需要 ABGR?
                    # AccentPolicy 的颜色通常是 AABBGGRR
                    # 假设输入是 AARRGGBB (Qt style)
                    a = int(gradient_color[0:2], 16)
                    r = int(gradient_color[2:4], 16)
                    g = int(gradient_color[4:6], 16)
                    b = int(gradient_color[6:8], 16)
                else:
                    a, r, g, b = 10, 255, 255, 255

                # 组合成 AABBGGRR
                col = (a << 24) | (b << 16) | (g << 8) | r
                policy.GradientColor = col
            else:
                # 默认白色，高透明
                policy.GradientColor = (10 << 24) | (255 << 16) | (255 << 8) | 255

            policy.AnimationId = animation_id

        # 准备数据结构
        data = WindowCompositionAttributeData()
        data.Attribute = self.WCA_ACCENT_POLICY
        data.SizeOfData = sizeof(policy)
        data.Data = ctypes.cast(byref(policy), c_void_p)

        if not self._is_window(hwnd):
            return
        self.SetWindowCompositionAttribute(HWND(int(hwnd)), byref(data))

    def set_round_corners(self, hwnd: int, preference=None, enable=None):
        """设置窗口圆角 (Win11 DWM)"""
        try:
            if not self._is_window(hwnd):
                return
            dwmapi = windll.dwmapi
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            if preference is None:
                if enable is None:
                    preference_val = self.DWMWCP_DEFAULT
                else:
                    preference_val = self.DWMWCP_ROUND if enable else self.DWMWCP_DONOTROUND
            else:
                preference_val = int(preference)

            pref = c_int(preference_val)
            dwmapi.DwmSetWindowAttribute(
                HWND(int(hwnd)), DWORD(DWMWA_WINDOW_CORNER_PREFERENCE), byref(pref), sizeof(pref)
            )
        except _WINDOW_EFFECT_ERRORS as exc:
            logger.debug("设置窗口圆角偏好失败: %s", exc, exc_info=True)

    def set_window_region(self, hwnd: int, w: int, h: int, r: int, x: int = 0, y: int = 0):
        """设置窗口圆角裁剪区域 (Win7/legacy)。

        Win10 的 layered/transparent Qt 窗口支持逐像素 alpha。继续叠加
        SetWindowRgn 会把圆角降级为 1-bit GDI 裁剪，边缘必然有锯齿。
        因此 Win10 只用 Qt paintEvent 自绘抗锯齿圆角，Win11 仍走 DWM。

        优化策略：
        1. 使用浮点数精确计算，减少舍入误差
        2. 右边和底边添加额外像素补偿
        3. 圆角半径强制为偶数并适当放大
        4. 使用更大的椭圆直径以获得更平滑的圆角
        """
        try:
            if is_win10():
                return
            if not self._is_window(hwnd):
                return

            # SetWindowRgn 使用窗口客户区坐标。Qt 高 DPI 已经把 QWidget 的
            # width()/height() 映射到该坐标系，不能再次乘显示器 DPI；
            # Win10 上重复缩放会导致实际内容在左上角、外圈出现黑色遮罩。
            x1 = int(round(x))
            y1 = int(round(y))
            x2 = int(round(x + w)) + 1
            y2 = int(round(y + h)) + 1

            # 圆角半径优化：
            # 1. 使用 round 而非 int 截断，保持精度
            # 2. 适当放大圆角半径（+1），使圆角更平滑
            # 3. 确保是偶数，GDI 渲染偶数圆角更平滑
            rr = max(4, int(round(r)) + 1)  # 最小为 4，并额外 +1
            if rr % 2 != 0:
                rr += 1  # 强制偶数

            # 创建圆角区域
            # CreateRoundRectRgn 的最后两个参数是椭圆的宽度和高度（直径）
            # 使用稍大的椭圆直径 (rr * 2 + 2) 以获得更平滑的圆角曲线
            ellipse_diameter = rr * 2 + 2
            hrgn = self.gdi32.CreateRoundRectRgn(x1, y1, x2, y2, ellipse_diameter, ellipse_diameter)
            if not hrgn:
                return

            # 应用窗口区域，redraw=True 立即重绘
            res = self.user32.SetWindowRgn(HWND(int(hwnd)), HRGN(hrgn), BOOL(1))
            if not res:
                # 如果失败，删除区域句柄
                try:
                    self.gdi32.DeleteObject(HRGN(hrgn))
                except _WINDOW_EFFECT_ERRORS as exc:
                    logger.debug("删除GDI对象失败: %s", exc, exc_info=True)
        except _WINDOW_EFFECT_ERRORS as exc:
            logger.debug("设置窗口区域失败: %s", exc, exc_info=True)

    def clear_window_region(self, hwnd: int):
        """清除窗口裁剪区域"""
        try:
            if not self._is_window(hwnd):
                return
            self.user32.SetWindowRgn(HWND(int(hwnd)), HRGN(0), BOOL(1))
        except _WINDOW_EFFECT_ERRORS as exc:
            logger.debug("清除窗口区域失败: %s", exc, exc_info=True)

    def set_aero_blur(self, hwnd: int, enable: bool = True):
        """设置传统 Aero 模糊 (Win7/Win10 早期风格)"""
        if is_win10() and enable:
            return

        policy = AccentPolicy()
        if enable:
            policy.AccentState = self.ACCENT_ENABLE_BLURBEHIND
        else:
            policy.AccentState = self.ACCENT_DISABLED

        data = WindowCompositionAttributeData()
        data.Attribute = self.WCA_ACCENT_POLICY
        data.SizeOfData = sizeof(policy)
        data.Data = ctypes.cast(byref(policy), c_void_p)

        if not self._is_window(hwnd):
            return
        self.SetWindowCompositionAttribute(HWND(int(hwnd)), byref(data))

    def set_dwm_blur_behind(self, hwnd: int, w: int, h: int, r: int, enable: bool = True, x: int = 0, y: int = 0):
        """
        设置 DWM Blur Behind（Win11/旧系统兼容路径）。
        Win10 上 enable=True 会被降级为关闭，避免 Qt 透明窗口黑色遮罩。
        注意：这与 SetWindowCompositionAttribute 不同，是另一种模糊机制

        优化策略：确保与 set_window_region 创建的区域完全一致，避免边缘不对齐
        """
        try:
            if not self._is_window(hwnd):
                return
            dwmapi = windll.dwmapi

            # Constants
            DWM_BB_ENABLE = 0x00000001
            DWM_BB_BLURREGION = 0x00000002

            bb = DWM_BLURBEHIND()
            bb.dwFlags = DWM_BB_ENABLE
            bb.fEnable = enable
            bb.hRgnBlur = None

            if is_win10() and enable:
                # DwmEnableBlurBehindWindow 在 Win10 的透明 Qt 窗口上会把未绘制区域
                # 合成为黑色。这里显式关闭该效果，背景由 Qt 自绘保证兼容性。
                bb.fEnable = False
                dwmapi.DwmEnableBlurBehindWindow(HWND(int(hwnd)), byref(bb))
                return

            if enable and r >= 0:
                bb.dwFlags |= DWM_BB_BLURREGION

                # 使用与 set_window_region 完全相同的坐标计算逻辑。
                x1 = int(round(x))
                y1 = int(round(y))
                x2 = int(round(x + w)) + 1
                y2 = int(round(y + h)) + 1

                # 圆角半径：与 set_window_region 保持一致
                rr = max(4, int(round(r)) + 1)
                if rr % 2 != 0:
                    rr += 1

                # 使用相同的椭圆直径
                ellipse_diameter = rr * 2 + 2
                hrgn = self.gdi32.CreateRoundRectRgn(x1, y1, x2, y2, ellipse_diameter, ellipse_diameter)
                bb.hRgnBlur = hrgn

            dwmapi.DwmEnableBlurBehindWindow(HWND(int(hwnd)), byref(bb))

            # Clean up region
            if bb.hRgnBlur:
                self.gdi32.DeleteObject(bb.hRgnBlur)

        except _WINDOW_EFFECT_ERRORS as exc:
            logger.debug("设置DWM模糊失败: %s", exc, exc_info=True)

    def apply_unified_round_corners(self, hwnd: int, w: int, h: int, r: int = 12):
        """
        应用统一的圆角效果（自动适配 Win10/Win11）

        Win11: 使用 DWM 原生圆角
        Win10: Qt paintEvent 通过 paint_win10_rounded_surface 自绘抗锯齿圆角，
               不使用 GDI SetWindowRgn（会降级为 1-bit 锯齿裁剪）。

        Args:
            hwnd: 窗口句柄
            w: 窗口宽度
            h: 窗口高度
            r: 圆角半径（默认 12px）
        """
        if is_win11():
            # Win11 使用 DWM 原生圆角
            self.set_round_corners(hwnd, enable=True)
        # Win10: 圆角由各窗口 paintEvent → paint_win10_rounded_surface 绘制

    def apply_unified_blur_effect(self, hwnd: int, gradient_color: str = None, enable: bool = True):  # type: ignore[assignment]
        """
        应用统一的模糊效果（自动适配 Win10/Win11）

        Win11: 使用 Acrylic 效果
        Win10: 关闭原生 Blur，交给 Qt 自绘背景

        Args:
            hwnd: 窗口句柄
            gradient_color: 渐变颜色（带透明度）
            enable: 是否启用
        """
        if is_win11():
            # Win11 优先使用 Acrylic
            self.set_acrylic(hwnd, gradient_color, enable, blur=True)
        else:
            # Win10 的原生 blur/accent 与 Qt 透明窗口组合不稳定。
            # 由各窗口 paintEvent 自绘底色，避免黑色遮罩和 DPI 错位。
            self.set_aero_blur(hwnd, False)

    def enable_window_shadow(self, hwnd: int, radius: int = 12):
        """
        为无边框窗口启用原生窗口阴影（自动适配 Win10/Win11）

        Win11 使用 DwmExtendFrameIntoClientArea。Win10 的透明无边框
        Qt 窗口无法稳定拿到 DWM 阴影，因此使用一个跟随目标窗口的
        透明影子窗口，视觉上贴近原生 Win10 阴影并匹配圆角半径。

        Args:
            hwnd: 窗口句柄
            radius: 圆角半径（默认 12px）
        """
        try:
            if not self._is_window(hwnd):
                return False
            if is_win10():
                return install_win10_window_shadow_for_hwnd(hwnd, radius)

            dwmapi = windll.dwmapi

            # 定义 MARGINS 结构
            class MARGINS(Structure):
                _fields_ = [
                    ("cxLeftWidth", c_int),
                    ("cxRightWidth", c_int),
                    ("cyTopHeight", c_int),
                    ("cyBottomHeight", c_int),
                ]

            # 设置边距扩展以启用阴影
            # 使用 -1 可以让整个窗口都扩展到客户区
            margins = MARGINS(-1, -1, -1, -1)

            dwmapi.DwmExtendFrameIntoClientArea.argtypes = [HWND, POINTER(MARGINS)]
            dwmapi.DwmExtendFrameIntoClientArea.restype = c_int
            result = dwmapi.DwmExtendFrameIntoClientArea(HWND(int(hwnd)), byref(margins))

            if result != 0:
                return False

            # Win11 上启用圆角
            if is_win11():
                self.set_round_corners(hwnd, enable=True)

            return True
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("enable_window_shadow failed", exc_info=True)
            return False

    def enable_shadow_for_dialog(self, hwnd: int, radius: int = 12):
        """
        为对话框启用阴影效果（自动适配 Win10/Win11）

        此方法专门用于标准对话框，使用更小的边距扩展。

        Args:
            hwnd: 窗口句柄
            radius: 圆角半径（默认 12px）

        Returns:
            bool: 是否成功启用
        """
        try:
            if not self._is_window(hwnd):
                return False
            if is_win10():
                return install_win10_window_shadow_for_hwnd(hwnd, radius)

            dwmapi = windll.dwmapi

            # 定义 MARGINS 结构
            class MARGINS(Structure):
                _fields_ = [
                    ("cxLeftWidth", c_int),
                    ("cxRightWidth", c_int),
                    ("cyTopHeight", c_int),
                    ("cyBottomHeight", c_int),
                ]

            # 使用 1 像素边距来启用阴影而不影响客户区
            margins = MARGINS(1, 1, 1, 1)

            dwmapi.DwmExtendFrameIntoClientArea.argtypes = [HWND, POINTER(MARGINS)]
            dwmapi.DwmExtendFrameIntoClientArea.restype = c_int
            result = dwmapi.DwmExtendFrameIntoClientArea(HWND(int(hwnd)), byref(margins))

            if result != 0:
                return False

            # Win11 上启用圆角
            if is_win11():
                self.set_round_corners(hwnd, enable=True)

            return True
        except _WINDOW_EFFECT_ERRORS:
            logger.debug("enable_shadow_for_dialog failed", exc_info=True)
            return False


# 全局共享实例，避免重复创建
_window_effect_instance = None


def get_window_effect() -> WindowEffect:
    """获取共享的 WindowEffect 实例"""
    global _window_effect_instance
    if _window_effect_instance is None:
        _window_effect_instance = WindowEffect()
    return _window_effect_instance


def enable_window_shadow_and_round_corners(widget, radius: int = 12, force_region: bool = False):
    """
    为 Qt 窗口启用阴影和圆角效果的便捷函数

    这是一个高级封装，自动处理 Win10/Win11 的差异：
    - Win11: 使用 DWM 原生圆角 + 阴影
    - Win10: 对于标准带标题栏的窗口，完全跳过（保持系统原生外观）
             对于无边框窗口（force_region=True），使用区域裁剪实现圆角

    Args:
        widget: Qt 窗口对象 (QWidget/QDialog/QMainWindow)
        radius: 圆角半径（默认 12px）
        force_region: 是否强制使用区域裁剪（仅用于无边框窗口）

    Returns:
        bool: 是否成功应用

    Usage:
        from ui.utils.window_effect import enable_window_shadow_and_round_corners

        class MyDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                # ... setup UI ...

            def showEvent(self, event):
                super().showEvent(event)
                enable_window_shadow_and_round_corners(self)
    """
    try:
        # 获取窗口句柄
        hwnd = int(widget.winId())
        if not hwnd:
            return False

        effect = get_window_effect()

        if is_win11():
            # Win11: 启用 DWM 阴影和原生圆角
            shadow_ok = effect.enable_shadow_for_dialog(hwnd, radius)
            return shadow_ok
        else:
            # Win10: 对于标准带标题栏的对话框，完全跳过区域裁剪和阴影效果
            # 因为区域裁剪会与系统窗口边框产生冲突，导致边缘显示不完整
            # 只有当 force_region=True（即无边框窗口）时才应用区域裁剪
            if not force_region:
                # 标准对话框，保持系统原生外观，不做任何修改
                return True

            try:
                w = widget.width()
                h = widget.height()
                if w > 0 and h > 0:
                    install_win10_window_shadow(widget, radius)
                    # Win10: 圆角由 paintEvent → paint_win10_rounded_surface 自绘，
                    # 不使用 SetWindowRgn（1-bit 锯齿）。显式关闭 DWM blur 避免黑色遮罩。
                    effect.set_dwm_blur_behind(hwnd, w, h, radius, enable=False)
                    try:
                        widget.update()
                    except _WINDOW_EFFECT_ERRORS as exc:
                        logger.debug("刷新Win10窗口区域失败: %s", exc, exc_info=True)
                    return True
            except _WINDOW_EFFECT_ERRORS as exc:
                logger.debug("应用Win10窗口区域裁剪失败: %s", exc, exc_info=True)
            return False
    except _WINDOW_EFFECT_ERRORS:
        logger.debug("enable_window_shadow_and_round_corners failed", exc_info=True)
        return False


def enable_acrylic_for_config_window(widget, theme: str = "dark", blur_amount: int = 30, radius: int = 12):
    """
    为配置窗口启用磨砂玻璃 Acrylic 效果

    此函数专门为配置窗口优化，提供适合 UI 的模糊效果参数。
    Win10 下只做窗口区域裁剪，不启用 DWM/Acrylic。

    Args:
        widget: Qt 窗口对象
        theme: 主题 ("dark" 或 "light")
        blur_amount: 透明度/模糊程度 (0-255)，默认 30 表示高透明度（更明显的模糊）
        radius: 圆角半径 (默认 12px)，仅 Win10 使用

    Returns:
        bool: 是否成功应用
    """
    try:
        hwnd = int(widget.winId())
        if not hwnd:
            return False

        effect = get_window_effect()

        # Windows Acrylic API 需要 AARRGGBB 格式
        if theme == "dark":
            # 深色主题：深灰色 (#1c1c1e)
            r, g, b = 0x1C, 0x1C, 0x1E
        else:
            # 浅色主题：浅灰色 (#f2f2f7)
            r, g, b = 0xF2, 0xF2, 0xF7

        if is_win11():
            # Win11: 保持原有逻辑 (Win11 效果很好)
            # 使用较低的 alpha 值获得更好的磨砂效果
            alpha = max(30, min(blur_amount, 80))
            gradient_color = f"{alpha:02x}{r:02x}{g:02x}{b:02x}"

            # Application unified blur (Acrylic)
            effect.apply_unified_blur_effect(hwnd, gradient_color, enable=True)
        else:
            # Win10: 只保留窗口区域裁剪。原生 DWM blur/accent 会在 Qt 透明
            # 无边框窗口上产生黑色遮罩或 DPI 错位，底色交给 paintEvent 自绘。
            install_win10_window_shadow(widget, radius)
            w = widget.width()
            h = widget.height()
            if w > 0 and h > 0:
                # Win10: paintEvent → paint_win10_rounded_surface 绘制抗锯齿圆角，
                # 不使用 GDI SetWindowRgn
                pass
            effect.set_dwm_blur_behind(hwnd, 0, 0, 0, enable=False)
            try:
                widget.update()
            except _WINDOW_EFFECT_ERRORS as exc:
                logger.debug("刷新窗口区域失败: %s", exc, exc_info=True)

        return True
    except _WINDOW_EFFECT_ERRORS:
        logger.exception("应用窗口效果失败")
        return False


def force_activate_window(hwnd: int):
    """
    极度强化版的窗口激活函数 (v2)

    综合了：
    1. AttachThreadInput (线程输入挂接)
    2. ShowWindow (恢复显示)
    3. HWND_TOPMOST 瞬时转换 (层级置顶)
    4. 虚拟按键欺骗 (绕过 SetForegroundWindow 限制)
    5. SwitchToThisWindow (系统深度激活)
    """
    if not hwnd:
        return False

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # 1. 基础状态恢复
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        else:
            user32.ShowWindow(hwnd, 5)  # SW_SHOW

        # 2. 线程上下文准备
        foreground_hwnd = user32.GetForegroundWindow()
        user32.GetWindowThreadProcessId(hwnd, None)
        current_thread = kernel32.GetCurrentThreadId()
        foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None) if foreground_hwnd else 0

        # 3. 线程输入挂接 (突破 SetForegroundWindow 限制的关键)
        attached = False
        if foreground_thread and foreground_thread != current_thread:
            attached = bool(user32.AttachThreadInput(foreground_thread, current_thread, True))

        try:
            # 4. 暴力切换 Z-Order (瞬时置顶)
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)  # HWND_TOPMOST
            user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)  # HWND_NOTOPMOST

            # 5. 调用系统前台切换
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            user32.SetActiveWindow(hwnd)

            # 6. 使用深度激活 API
            if hasattr(user32, "SwitchToThisWindow"):
                user32.SwitchToThisWindow(hwnd, True)

        finally:
            if attached:
                user32.AttachThreadInput(foreground_thread, current_thread, False)

        # 8. 最后确认归位到 Top (非 TopMost)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)  # HWND_TOP

        return user32.GetForegroundWindow() == hwnd
    except _WINDOW_EFFECT_ERRORS:
        logger.debug("force_activate_window failed", exc_info=True)
        return False
