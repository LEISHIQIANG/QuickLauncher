"""
主题助手 - 统一管理对话框主题
"""

import logging
import os
import tempfile

from qt_compat import QBrush, QColor, QPainter, QPen, QPixmap, QRectF, QtCompat
from ui.utils.ui_scale import sp, scale_qss

logger = logging.getLogger(__name__)

# 内存缓存，避免重复文件系统访问
_icon_path_cache = {}


def log_error(msg):
    try:
        with open("debug_crash.log", "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        logger.debug("写入调试日志文件失败", exc_info=True)


def get_temp_icon_dir():
    try:
        # Use a local temp directory to avoid permission issues
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        temp_dir = os.path.join(base_dir, "temp_icons")
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
        return temp_dir
    except Exception:
        return tempfile.gettempdir()


def _get_cached_icon_path(cache_key: str) -> str:
    """从缓存获取图标路径"""
    return _icon_path_cache.get(cache_key, "")


def _set_cached_icon_path(cache_key: str, path: str):
    """缓存图标路径"""
    _icon_path_cache[cache_key] = path


def create_ios_radio_icon(checked: bool, theme: str) -> str:
    """创建 iOS 风格单选图标"""
    try:
        # 基础尺寸 14x14，应用缩放
        base_s = 14
        s = sp(base_s)
        scale_tag = f"s{s}"
        filename = f"ios_radio_thick_v6_{theme}_{'on' if checked else 'off'}_{scale_tag}.png"
        cache_key = f"radio_{filename}"

        # 先检查内存缓存
        cached = _get_cached_icon_path(cache_key)
        if cached:
            return cached

        # 使用系统临时目录，与 settings_panel 保持一致
        temp_dir = get_temp_icon_dir()
        file_path = os.path.join(temp_dir, filename)

        if os.path.exists(file_path):
            normalized_path = file_path.replace("\\", "/")
            _set_cached_icon_path(cache_key, normalized_path)
            return normalized_path

        pixmap = QPixmap(s, s)
        if pixmap.isNull():
            log_error("Failed to create QPixmap in create_ios_radio_icon")
            return ""

        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        try:
            if not painter.isActive():
                log_error("Painter not active in create_ios_radio_icon")
                return ""

            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            if checked:
                # Blue fill with white dot
                painter.setPen(QtCompat.NoPen)
                painter.setBrush(QBrush(QColor("#007AFF")))  # iOS System Blue
                painter.drawEllipse(0, 0, s, s)

                painter.setBrush(QBrush(QColor("#FFFFFF")))
                # 调整中间白点大小 (proportional to base)
                dot_s = max(4, sp(6))
                painter.drawEllipse(QRectF((s - dot_s) / 2, (s - dot_s) / 2, dot_s, dot_s))
            else:
                # High contrast off state
                if theme == "dark":
                    border_color = "#8E8E93"  # System Gray
                    fill_color = "#3A3A3C"  # System Gray 6
                else:
                    border_color = "#C7C7CC"  # Light Gray
                    fill_color = "#FFFFFF"  # White

                # 填充完整个椭圆（消除四角透明）
                painter.setPen(QtCompat.NoPen)
                painter.setBrush(QBrush(QColor(fill_color)))
                painter.drawEllipse(0, 0, s, s)
                # 再画边框
                pen = QPen(QColor(border_color), 1.5)
                pen.setJoinStyle(QtCompat.RoundJoin)
                pen.setCapStyle(QtCompat.RoundCap)
                painter.setPen(pen)
                painter.setBrush(QtCompat.NoBrush)
                painter.drawEllipse(1, 1, s - 2, s - 2)  # inset
        finally:
            painter.end()

        if not pixmap.save(file_path):
            log_error(f"Failed to save icon to {file_path}")
            return ""

        normalized_path = file_path.replace("\\", "/")
        _set_cached_icon_path(cache_key, normalized_path)
        return normalized_path
    except Exception:
        logger.exception("创建单选按钮图标失败")
        return ""


def create_ios_switch_icon(checked: bool, theme: str) -> str:
    """创建 iOS 风格开关图标"""
    try:
        # 基础尺寸 29x18，应用缩放
        base_w, base_h = 29, 18
        w, h = sp(base_w), sp(base_h)
        scale_tag = f"s{w}x{h}"
        filename = f"ios_switch_thick_v6_{theme}_{'on' if checked else 'off'}_{scale_tag}.png"
        cache_key = f"switch_{filename}"

        # 先检查内存缓存
        cached = _get_cached_icon_path(cache_key)
        if cached:
            return cached

        temp_dir = get_temp_icon_dir()
        file_path = os.path.join(temp_dir, filename)

        if os.path.exists(file_path):
            normalized_path = file_path.replace("\\", "/")
            _set_cached_icon_path(cache_key, normalized_path)
            return normalized_path

        pixmap = QPixmap(w, h)
        if pixmap.isNull():
            log_error("Failed to create QPixmap in create_ios_switch_icon")
            return ""

        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        try:
            if not painter.isActive():
                log_error("Painter not active in create_ios_switch_icon")
                return ""

            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            if checked:
                bg_color = QColor("#007AFF")  # Changed to Blue from iOS Green
                knob_x = w - h + 2
            else:
                if theme == "dark":
                    bg_color = QColor("#48484A")
                else:
                    bg_color = QColor("#E9E9EA")  # Light Gray
                knob_x = 2

            # Draw track
            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(bg_color))
            painter.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)

            # Draw border for off state if needed for contrast
            if not checked:
                if theme == "dark":
                    pen = QPen(QColor("#8E8E93"), 1)
                else:
                    pen = QPen(QColor("#D1D1D6"), 1)
                pen.setJoinStyle(QtCompat.RoundJoin)
                pen.setCapStyle(QtCompat.RoundCap)
                painter.setPen(pen)
                painter.setBrush(QtCompat.NoBrush)
                painter.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)

            # Draw knob
            knob_size = h - 4
            pen = QPen(QColor(0, 0, 0, 50), 1)
            pen.setJoinStyle(QtCompat.RoundJoin)
            pen.setCapStyle(QtCompat.RoundCap)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor("#FFFFFF")))
            # Add shadow/border to knob
            painter.drawEllipse(QRectF(knob_x, 2, knob_size, knob_size))

        finally:
            painter.end()

        if not pixmap.save(file_path):
            log_error(f"Failed to save icon to {file_path}")
            return ""

        normalized_path = file_path.replace("\\", "/")
        _set_cached_icon_path(cache_key, normalized_path)
        return normalized_path
    except Exception:
        logger.exception("创建开关图标失败")
        return ""


def create_ios_checkbox_icon(checked: bool, theme: str) -> str:
    """创建 iOS 风格复选框图标 (圆角矩形)"""
    try:
        base_s = 14
        s = sp(base_s)
        scale_tag = f"s{s}"
        filename = f"ios_check_thick_v7_{theme}_{'on' if checked else 'off'}_{scale_tag}.png"
        cache_key = f"checkbox_{filename}"

        # 先检查内存缓存
        cached = _get_cached_icon_path(cache_key)
        if cached:
            return cached

        temp_dir = get_temp_icon_dir()
        file_path = os.path.join(temp_dir, filename)

        if os.path.exists(file_path):
            normalized_path = file_path.replace("\\", "/")
            _set_cached_icon_path(cache_key, normalized_path)
            return normalized_path

        pixmap = QPixmap(s, s)
        if pixmap.isNull():
            log_error("Failed to create QPixmap in create_ios_checkbox_icon")
            return ""

        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        try:
            if not painter.isActive():
                log_error("Painter not active in create_ios_checkbox_icon")
                return ""

            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.HighQualityAntialiasing)

            if checked:
                # Blue fill with checkmark
                painter.setPen(QtCompat.NoPen)
                painter.setBrush(QBrush(QColor("#007AFF")))
                cr = max(2, sp(3))
                painter.drawRoundedRect(QRectF(0, 0, s, s), cr, cr)

                # Draw checkmark (scaled proportionally from base 14)
                painter.setPen(QPen(QColor("#FFFFFF"), 1.5))
                painter.setBrush(QtCompat.NoBrush)
                ratio = s / 14.0 if s != 14 else 1.0
                path = [(3 * ratio, 7 * ratio), (6 * ratio, 10 * ratio), (11 * ratio, 4 * ratio)]
                for i in range(len(path) - 1):
                    p1 = path[i]
                    p2 = path[i + 1]
                    painter.drawLine(int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1]))
            else:
                # High contrast off state
                if theme == "dark":
                    border_color = "#8E8E93"
                    fill_color = "#3A3A3C"
                else:
                    border_color = "#C7C7CC"
                    fill_color = "#FFFFFF"

                # 濉厖瀹屾暣涓渾瑙掔煩褰紙瑕嗙洊鍏ㄩ儴鍍忕礌锛屾秷闄ゅ洓瑙掗€忔槑锛?
                # 填充完整圆角矩形（覆盖全部像素，消除四角透明）
                painter.setPen(QtCompat.NoPen)
                painter.setBrush(QBrush(QColor(fill_color)))
                cr = max(2, sp(3))
                painter.drawRoundedRect(QRectF(0, 0, s, s), cr, cr)
                # 再画边框
                pen = QPen(QColor(border_color), 1.5)
                pen.setJoinStyle(QtCompat.RoundJoin)
                pen.setCapStyle(QtCompat.RoundCap)
                painter.setPen(pen)
                painter.setBrush(QtCompat.NoBrush)
                painter.drawRoundedRect(QRectF(1, 1, s - 2, s - 2), cr, cr)  # inset
        finally:
            painter.end()

        if not pixmap.save(file_path):
            log_error(f"Failed to save icon to {file_path}")
            return ""

        normalized_path = file_path.replace("\\", "/")
        _set_cached_icon_path(cache_key, normalized_path)
        return normalized_path
    except Exception:
        logger.exception("创建复选框图标失败")
        return ""


def get_radio_stylesheet(theme: str) -> str:
    """获取 iOS 风格单选按钮样式表"""
    radio_on = create_ios_radio_icon(True, theme)
    radio_off = create_ios_radio_icon(False, theme)

    return scale_qss(f"""
        QRadioButton {{
            font-size: 12px;
            spacing: 8px;
            color: {"#ffffff" if theme == "dark" else "#333333"};
        }}
        QRadioButton::indicator {{
            width: 14px;
            height: 14px;
            border: none;
            background: transparent;
        }}
        QRadioButton::indicator:unchecked {{
            image: url("{radio_off}");
        }}
        QRadioButton::indicator:checked {{
            image: url("{radio_on}");
        }}
    """)


def get_checkbox_stylesheet(theme: str) -> str:
    """获取 iOS 风格复选框样式表"""
    check_on = create_ios_checkbox_icon(True, theme)
    check_off = create_ios_checkbox_icon(False, theme)

    return scale_qss(f"""
        QCheckBox {{
            font-size: 12px;
            spacing: 8px;
            color: {"#ffffff" if theme == "dark" else "#333333"};
        }}
        QCheckBox::indicator {{
            width: 14px;
            height: 14px;
            border: none;
            background: transparent;
        }}
        QCheckBox::indicator:unchecked {{
            image: url("{check_off}");
        }}
        QCheckBox::indicator:checked {{
            image: url("{check_on}");
        }}
    """)


def get_small_checkbox_stylesheet(theme: str) -> str:
    """获取小尺寸复选框样式表（用于图标反转选项）"""
    check_on = create_ios_checkbox_icon(True, theme)
    check_off = create_ios_checkbox_icon(False, theme)

    return scale_qss(f"""
        QCheckBox {{
            font-size: 10px;
            spacing: 4px;
            color: {"#ffffff" if theme == "dark" else "#333333"};
        }}
        QCheckBox::indicator {{
            width: 11px;
            height: 11px;
            border: none;
            background: transparent;
        }}
        QCheckBox::indicator:unchecked {{
            image: url("{check_off}");
        }}
        QCheckBox::indicator:checked {{
            image: url("{check_on}");
        }}
    """)


def get_compact_checkbox_stylesheet(theme: str) -> str:
    """获取紧凑复选框样式表（11px字号，匹配按钮文字大小）"""
    check_on = create_ios_checkbox_icon(True, theme)
    check_off = create_ios_checkbox_icon(False, theme)

    return scale_qss(f"""
        QCheckBox {{
            font-size: 11px;
            spacing: 6px;
            color: {"#ffffff" if theme == "dark" else "#333333"};
        }}
        QCheckBox::indicator {{
            width: 13px;
            height: 13px;
            border: none;
            background: transparent;
        }}
        QCheckBox::indicator:unchecked {{
            image: url("{check_off}");
        }}
        QCheckBox::indicator:checked {{
            image: url("{check_on}");
        }}
    """)


def get_indicator_only_checkbox_stylesheet(theme: str) -> str:
    """复选框样式表 — 只设置指示器图片，不覆盖文字大小和颜色。"""
    check_on = create_ios_checkbox_icon(True, theme)
    check_off = create_ios_checkbox_icon(False, theme)

    return scale_qss(f"""
        QCheckBox::indicator {{
            width: 11px;
            height: 11px;
            border: none;
        }}
        QCheckBox::indicator:unchecked {{
            image: url("{check_off}");
        }}
        QCheckBox::indicator:checked {{
            image: url("{check_on}");
        }}
    """)


def get_switch_stylesheet(theme: str) -> str:
    switch_on = create_ios_switch_icon(True, theme)
    switch_off = create_ios_switch_icon(False, theme)

    return scale_qss(f"""
        QCheckBox {{
            font-size: 12px;
            spacing: 8px;
            color: {"#ffffff" if theme == "dark" else "#333333"};
        }}
        QCheckBox::indicator {{
            width: 29px;
            height: 18px;
            border: none;
            background: transparent;
        }}
        QCheckBox::indicator:unchecked {{
            image: url("{switch_off}");
        }}
        QCheckBox::indicator:checked {{
            image: url("{switch_on}");
        }}
    """)


def get_dialog_stylesheet(theme: str) -> str:
    """获取对话框样式表"""
    from ui.styles.style import get_dialog_stylesheet as get_base_dialog_stylesheet

    return get_base_dialog_stylesheet(theme)


def apply_theme_to_dialog(dialog, theme: str):
    """应用主题到对话框 - 使用磨砂玻璃拟态风格"""
    try:
        from ui.styles.style import Glassmorphism

        # 结合拟态样式和对话框专用样式
        glassmorphism_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
        dialog_extra = get_dialog_stylesheet(theme)
        dialog.setStyleSheet(glassmorphism_style + dialog_extra)
    except ImportError:
        # 回退到基础样式
        dialog.setStyleSheet(get_dialog_stylesheet(theme))
