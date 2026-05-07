"""
主题助手 - 统一管理对话框主题
"""


import os
import tempfile
import traceback
from qt_compat import QPixmap, QPainter, QColor, QBrush, QPen, QRectF, QtCompat

# 内存缓存，避免重复文件系统访问
_icon_path_cache = {}

def log_error(msg):
    try:
        with open("debug_crash.log", "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except:
        pass

def get_temp_icon_dir():
    try:
        # Use a local temp directory to avoid permission issues
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        temp_dir = os.path.join(base_dir, "temp_icons")
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
        return temp_dir
    except:
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
        # 尺寸缩小为原来的 0.8 倍 (18x18 -> 14x14)
        s = 14
        # 使用新文件名 (thick border version)
        filename = f"ios_radio_thick_v6_{theme}_{'on' if checked else 'off'}.png"
        cache_key = f"radio_{filename}"
        
        # 先检查内存缓存
        cached = _get_cached_icon_path(cache_key)
        if cached:
            return cached
        
        # 使用系统临时目录，与 settings_panel 保持一致
        temp_dir = get_temp_icon_dir()
        file_path = os.path.join(temp_dir, filename)
        
        if os.path.exists(file_path):
            normalized_path = file_path.replace('\\', '/')
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
            
            if checked:
                # Blue fill with white dot
                painter.setPen(QtCompat.NoPen)
                painter.setBrush(QBrush(QColor("#007AFF"))) # iOS System Blue
                painter.drawEllipse(0, 0, s, s)
                
                painter.setBrush(QBrush(QColor("#FFFFFF")))
                # 调整中间白点大小
                dot_s = 6  
                painter.drawEllipse(QRectF((s-dot_s)/2, (s-dot_s)/2, dot_s, dot_s))
            else:
                # High contrast off state
                if theme == "dark":
                    border_color = "#8E8E93" # System Gray
                    fill_color = "#3A3A3C"   # System Gray 6
                else:
                    border_color = "#C7C7CC" # Light Gray
                    fill_color = "#FFFFFF"   # White
                
                painter.setPen(QPen(QColor(border_color), 1.5))
                painter.setBrush(QBrush(QColor(fill_color)))
                painter.drawEllipse(1, 1, s-2, s-2) # inset
        finally:
            painter.end()
            
        if not pixmap.save(file_path):
            log_error(f"Failed to save icon to {file_path}")
            return ""
        
        normalized_path = file_path.replace('\\', '/')
        _set_cached_icon_path(cache_key, normalized_path)
        return normalized_path
    except Exception as e:
        log_error(f"Error creating radio icon: {e}\n{traceback.format_exc()}")
        return ""

def create_ios_switch_icon(checked: bool, theme: str) -> str:
    """创建 iOS 风格开关图标"""
    try:
        # 尺寸缩小为原来的 0.8 倍 (36x22 -> 29x18)
        w, h = 29, 18
        # 使用新文件名 (thick border version)
        filename = f"ios_switch_thick_v6_{theme}_{'on' if checked else 'off'}.png"
        cache_key = f"switch_{filename}"
        
        # 先检查内存缓存
        cached = _get_cached_icon_path(cache_key)
        if cached:
            return cached
        
        temp_dir = get_temp_icon_dir()
        file_path = os.path.join(temp_dir, filename)
        
        if os.path.exists(file_path):
            normalized_path = file_path.replace('\\', '/')
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
            
            if checked:
                bg_color = QColor("#007AFF") # Changed to Blue from iOS Green
                knob_x = w - h + 2
            else:
                if theme == "dark":
                    bg_color = QColor("#48484A")
                else:
                    bg_color = QColor("#E9E9EA") # Light Gray
                knob_x = 2
                
            # Draw track
            painter.setPen(QtCompat.NoPen)
            painter.setBrush(QBrush(bg_color))
            painter.drawRoundedRect(0, 0, w, h, h/2, h/2)
            
            # Draw border for off state if needed for contrast
            if not checked:
                 if theme == "dark":
                     painter.setPen(QPen(QColor("#8E8E93"), 1))
                 else:
                     painter.setPen(QPen(QColor("#D1D1D6"), 1))
                 painter.setBrush(QtCompat.NoBrush)
                 painter.drawRoundedRect(0, 0, w, h, h/2, h/2)

            # Draw knob
            knob_size = h - 4
            painter.setPen(QPen(QColor(0, 0, 0, 50), 1))
            painter.setBrush(QBrush(QColor("#FFFFFF")))
            # Add shadow/border to knob
            painter.drawEllipse(QRectF(knob_x, 2, knob_size, knob_size))
            
        finally:
            painter.end()

        if not pixmap.save(file_path):
            log_error(f"Failed to save icon to {file_path}")
            return ""

        normalized_path = file_path.replace('\\', '/')
        _set_cached_icon_path(cache_key, normalized_path)
        return normalized_path
    except Exception as e:
        log_error(f"Error creating switch icon: {e}\n{traceback.format_exc()}")
        return ""


def create_ios_checkbox_icon(checked: bool, theme: str) -> str:
    """创建 iOS 风格复选框图标 (圆角矩形)"""
    try:
        s = 14
        filename = f"ios_check_thick_v6_{theme}_{'on' if checked else 'off'}.png"
        cache_key = f"checkbox_{filename}"
        
        # 先检查内存缓存
        cached = _get_cached_icon_path(cache_key)
        if cached:
            return cached
        
        temp_dir = get_temp_icon_dir()
        file_path = os.path.join(temp_dir, filename)
        
        if os.path.exists(file_path):
            normalized_path = file_path.replace('\\', '/')
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
            
            if checked:
                # Blue fill with checkmark
                painter.setPen(QtCompat.NoPen)
                painter.setBrush(QBrush(QColor("#007AFF")))
                painter.drawRoundedRect(0, 0, s, s, 3, 3)
                
                # Draw checkmark
                painter.setPen(QPen(QColor("#FFFFFF"), 1.5))
                painter.setBrush(QtCompat.NoBrush)
                # Checkmark coordinates (approx)
                path = [(3, 7), (6, 10), (11, 4)]
                for i in range(len(path) - 1):
                    p1 = path[i]
                    p2 = path[i+1]
                    painter.drawLine(p1[0], p1[1], p2[0], p2[1])
            else:
                # High contrast off state
                if theme == "dark":
                    border_color = "#8E8E93"
                    fill_color = "#3A3A3C"
                else:
                    border_color = "#C7C7CC"
                    fill_color = "#FFFFFF"
                
                painter.setPen(QPen(QColor(border_color), 1.5))
                painter.setBrush(QBrush(QColor(fill_color)))
                painter.drawRoundedRect(1, 1, s-2, s-2, 3, 3) # inset
        finally:
            painter.end()
            
        if not pixmap.save(file_path):
            log_error(f"Failed to save icon to {file_path}")
            return ""

        normalized_path = file_path.replace('\\', '/')
        _set_cached_icon_path(cache_key, normalized_path)
        return normalized_path
    except Exception as e:
        log_error(f"Error creating checkbox icon: {e}\n{traceback.format_exc()}")
        return ""

def get_radio_stylesheet(theme: str) -> str:
    """获取 iOS 风格单选按钮样式表"""
    radio_on = create_ios_radio_icon(True, theme)
    radio_off = create_ios_radio_icon(False, theme)
    
    return f"""
        QRadioButton {{
            font-size: 12px;
            spacing: 8px;
            color: {'#ffffff' if theme == 'dark' else '#333333'};
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
    """

def get_checkbox_stylesheet(theme: str) -> str:
    """获取 iOS 风格复选框样式表"""
    check_on = create_ios_checkbox_icon(True, theme)
    check_off = create_ios_checkbox_icon(False, theme)
    
    return f"""
        QCheckBox {{
            font-size: 12px;
            spacing: 8px;
            color: {'#ffffff' if theme == 'dark' else '#333333'};
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
    """

def get_small_checkbox_stylesheet(theme: str) -> str:
    """获取小尺寸复选框样式表（用于图标反转选项）"""
    check_on = create_ios_checkbox_icon(True, theme)
    check_off = create_ios_checkbox_icon(False, theme)

    return f"""
        QCheckBox {{
            font-size: 10px;
            spacing: 4px;
            color: {'#ffffff' if theme == 'dark' else '#333333'};
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
    """

def get_switch_stylesheet(theme: str) -> str:
    switch_on = create_ios_switch_icon(True, theme)
    switch_off = create_ios_switch_icon(False, theme)
    
    return f"""
        QCheckBox {{
            font-size: 12px;
            spacing: 8px;
            color: {'#ffffff' if theme == 'dark' else '#333333'};
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
    """

def get_dialog_stylesheet(theme: str) -> str:
    """获取对话框样式表"""
    
    if theme == "dark":
        return ("""
            QDialog {
                background-color: rgba(28, 28, 30, 0.8);
                color: #ffffff;
            }
            QGroupBox {
                font-weight: 400;
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                margin-top: 14px;
                padding-top: 6px;
                font-size: 11px;
                color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 2px;
                padding: 0 6px;
                background-color: transparent;
                color: #8e8e93;
            }
            QLabel {
                color: #ffffff;
                background: transparent;
            }
            QLineEdit, QPlainTextEdit, QTextEdit {
                background-color: rgba(190, 190, 197, 0.22);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                padding: 6px 8px;
                color: #ffffff;
            }
            QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {
                border: 1px solid rgba(10, 132, 255, 0.8);
                background-color: rgba(190, 190, 197, 0.30);
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: transparent;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #0A84FF;
                border-radius: 2px;
            }
            QSlider::add-page:horizontal {
                background: #555555;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
                border: 1px solid rgba(0, 0, 0, 60);
            }
            QSlider::handle:horizontal:hover {
                background: #f2f2f7;
            }
            QPushButton {
                background-color: rgba(190, 190, 197, 0.25);
                border: 1px solid rgba(255, 255, 255, 26);
                border-radius: 10px;
                padding: 6px 10px;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: rgba(200, 200, 207, 0.35);
            }
            QPushButton:pressed {
                background-color: rgba(190, 190, 197, 0.30);
            }
            QPushButton:default {
                background-color: #0A84FF;
                border: 1px solid #0A84FF;
                color: #ffffff;
            }
            QComboBox {
                background-color: rgba(190, 190, 197, 0.22);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
                padding: 6px 10px;
                color: #ffffff;
            }
            QComboBox:hover {
                border: 1px solid #0A84FF;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #aaaaaa;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: rgba(75, 75, 80, 245);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 10px;
                padding: 4px;
                selection-background-color: #0A84FF;
                selection-color: #ffffff;
                color: #ffffff;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                padding: 6px 10px;
                border-radius: 6px;
                margin: 2px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: rgba(10, 132, 255, 0.5);
                color: #ffffff;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #0A84FF;
                color: #ffffff;
            }
            
            /* File Dialog Specifics */
            QTreeView, QListView {
                background-color: rgba(190, 190, 197, 0.18);
                border: 1px solid rgba(255, 255, 255, 0.12);
                color: #ffffff;
                outline: none;
            }
            QTreeView::item:selected, QListView::item:selected {
                background-color: #0A84FF;
                color: #ffffff;
            }
            QTreeView::item:hover, QListView::item:hover {
                background-color: rgba(255, 255, 255, 18);
            }
            QHeaderView::section {
                background-color: rgba(190, 190, 197, 0.15);
                color: #ffffff;
                padding: 4px;
                border: none;
                border-right: 1px solid rgba(255, 255, 255, 0.12);
                border-bottom: 1px solid rgba(255, 255, 255, 0.12);
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 10px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(199, 199, 204, 140);
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
            QToolButton {
                background-color: transparent;
                border: none;
                border-radius: 8px;
                color: #ffffff;
                padding: 4px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 16);
            }
            QToolButton:pressed {
                background-color: rgba(255, 255, 255, 12);
            }
        """ + get_switch_stylesheet(theme) + get_radio_stylesheet(theme))
    else:
        # 浅色主题
        return ("""
            QDialog {
                background-color: rgba(242, 242, 247, 0.7);
                color: #1c1c1e;
            }
            QGroupBox {
                font-weight: 400;
                background-color: rgba(255, 255, 255, 0.3);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 10px;
                margin-top: 14px;
                padding-top: 6px;
                font-size: 11px;
                color: #1c1c1e;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 2px;
                padding: 0 6px;
                background-color: transparent;
                color: #8e8e93;
            }
            QLabel {
                color: #1c1c1e;
                background: transparent;
            }
            QLineEdit, QPlainTextEdit, QTextEdit {
                background-color: rgba(255, 255, 255, 0.4);
                border: 1px solid rgba(0, 0, 0, 0.1);
                border-radius: 9px;
                padding: 6px 8px;
                color: #1c1c1e;
            }
            QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {
                border: 1px solid rgba(0, 122, 255, 0.6);
                background-color: rgba(255, 255, 255, 0.6);
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: transparent;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #007AFF;
                border-radius: 2px;
            }
            QSlider::add-page:horizontal {
                background: #D1D1D6;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
                border: 1px solid rgba(0, 0, 0, 40);
            }
            QSlider::handle:horizontal:hover {
                background: #f2f2f7;
            }
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #f2f2f7);
                border: 1px solid #d1d1d6;
                border-radius: 9px;
                padding: 6px 10px;
                color: #1c1c1e;
            }
            QPushButton:hover {
                background-color: #ffffff;
            }
            QPushButton:pressed {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f2f2f7, stop:1 #ffffff);
            }
            QPushButton:default {
                background-color: #007AFF;
                border: 1px solid #007AFF;
                color: #ffffff;
            }
            QPushButton:default:hover {
                background-color: #0A84FF;
                border: 1px solid #0A84FF;
            }
            QComboBox {
                background-color: rgba(255, 255, 255, 0.4);
                border: 1px solid rgba(0, 0, 0, 0.1);
                border-radius: 9px;
                padding: 6px 10px;
                color: #1c1c1e;
            }
            QComboBox:hover {
                border: 1px solid #007AFF;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #666666;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                border: 1px solid #d1d1d6;
                selection-background-color: #f2f2f7;
                selection-color: #1c1c1e;
                color: #1c1c1e;
                outline: none;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #f2f2f7;
                color: #1c1c1e;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #e5e5ea;
                color: #1c1c1e;
            }
            
            /* File Dialog Specifics */
            QTreeView, QListView {
                background-color: #ffffff;
                border: 1px solid #d1d1d6;
                color: #1c1c1e;
                outline: none;
            }
            QTreeView::item:selected, QListView::item:selected {
                background-color: #007AFF;
                color: #ffffff;
            }
            QTreeView::item:hover, QListView::item:hover {
                background-color: #f2f2f7;
            }
            QHeaderView::section {
                background-color: #f2f2f7;
                color: #1c1c1e;
                padding: 4px;
                border: none;
                border-right: 1px solid #e5e5ea;
                border-bottom: 1px solid #e5e5ea;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 10px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #c7c7cc;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
            QToolButton {
                background-color: transparent;
                border: none;
                border-radius: 8px;
                color: #1c1c1e;
                padding: 4px;
            }
            QToolButton:hover {
                background-color: #f2f2f7;
            }
            QToolButton:pressed {
                background-color: #e5e5ea;
            }
        """ + get_switch_stylesheet(theme) + get_radio_stylesheet(theme))


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

