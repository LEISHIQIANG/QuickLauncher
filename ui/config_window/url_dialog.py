"""
URL编辑对话框
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core import ShortcutItem, ShortcutType
from qt_compat import (
    QCheckBox,
    QColor,
    QFileDialog,
    QFont,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QPainter,
    QPixmap,
    QPushButton,
    QtCompat,
    QThread,
    QTimer,
    QVBoxLayout,
    pyqtSignal,
)
from ui.styles.style import Glassmorphism

from .base_dialog import BaseDialog
from .icon_browse_helper import choose_custom_icon
from .theme_helper import get_small_checkbox_stylesheet


class UrlLatencyTestThread(QThread):
    finished_signal = pyqtSignal(dict)

    def __init__(self, url: str, input_values: dict | None = None, parent=None):
        super().__init__(parent)
        self.url = url
        self.input_values = input_values or {}
        self._suppress_signal = False

    def suppress_result_signal(self):
        self._suppress_signal = True

    def run(self):
        try:
            from core.shortcut_url_exec import UrlExecutionMixin

            result = UrlExecutionMixin.test_url_latency(self.url, self.input_values, timeout_ms=5000)
        except Exception as e:
            result = {
                "success": False,
                "latency_ms": -1,
                "color": "red",
                "error": f"无法测试: {e}",
                "url": "",
                "timeout_ms": 5000,
            }
        if not self._suppress_signal:
            result["request_id"] = getattr(self, "request_id", 0)
            self.finished_signal.emit(result)


class UrlIconFetchThread(QThread):
    finished_signal = pyqtSignal(dict)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self._suppress_signal = False

    def suppress_result_signal(self):
        self._suppress_signal = True

    def run(self):
        try:
            from core.favicon_cache import fetch_favicon

            icon_path = fetch_favicon(self.url, force_refresh=True)
            result = {
                "success": bool(icon_path),
                "icon_path": icon_path or "",
                "error": "" if icon_path else "未获取到可用图标",
            }
        except Exception as e:
            result = {
                "success": False,
                "icon_path": "",
                "error": f"自动获取失败: {e}",
            }
        if not self._suppress_signal:
            result["request_id"] = getattr(self, "request_id", 0)
            self.finished_signal.emit(result)


class UrlDialog(BaseDialog):
    """URL编辑对话框"""
    _orphaned_threads = []

    def __init__(self, parent=None, shortcut: ShortcutItem = None):
        super().__init__(parent)
        self.shortcut = shortcut or ShortcutItem(type=ShortcutType.URL)
        self._custom_icon_path = self.shortcut.icon_path or ""
        self._dialog_finished = False

        self.setWindowTitle("编辑打开网址" if shortcut else "添加打开网址")
        self.setMinimumWidth(420)
        self._latency_thread = None
        self._latency_request_id = 0
        self._latency_result_state = ("muted", "未测试")
        self._has_auto_tested = False
        self._icon_fetch_thread = None
        self._icon_fetch_request_id = 0

        self._setup_window_icon()
        self._setup_ui()
        self._load_data()
        self._apply_theme()

    def _setup_window_icon(self):
        """设置窗口图标"""
        from .base_dialog import BaseDialog
        if BaseDialog._is_compiled():
            return
        try:
            pixmap = QPixmap(64, 64)
            pixmap.fill(QtCompat.transparent)
            painter = QPainter(pixmap)
            try:
                painter.setRenderHint(QtCompat.Antialiasing)
                font = QFont("Segoe UI Emoji", 40)
                font.setStyleHint(QFont.StyleHint.SansSerif)
                painter.setFont(font)
                painter.setPen(QColor(100, 149, 237))
                painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "🌐")
            finally:
                painter.end()
            self.setWindowIcon(QIcon(pixmap))
        except Exception:
            pass

    def _apply_theme(self):
        """应用主题"""
        self._apply_theme_colors()
        theme = self.theme

        # 预览框样式
        if theme == "dark":
            self.icon_preview.setStyleSheet("""
                QLabel {
                    background-color: rgba(255, 255, 255, 0.1);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 10px;
                }
            """)
        else:
            self.bg_color = "#f2f2f7"
            self.border_color = "rgba(0, 0, 0, 0.1)"

            # 预览框样式
            self.icon_preview.setStyleSheet("""
                QLabel {
                    background-color: rgba(0, 0, 0, 0.05);
                    border: 1px solid rgba(0, 0, 0, 0.05);
                    border-radius: 10px;
                }
            """)

        # 使用与主配置窗口一致的 Glassmorphism 样式
        base_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
        border_color = "rgba(255, 255, 255, 0.06)" if theme == "dark" else "rgba(0, 0, 0, 0.04)"
        title_color = "rgba(255, 255, 255, 0.6)" if theme == "dark" else "rgba(0, 0, 0, 0.5)"

        custom_style = base_style + f"""
            QDialog {{ background: transparent; border: none; }}
            QGroupBox {{
                border: 1px solid {border_color};
                border-radius: 6px;
                margin-top: 16px;
                padding-top: 8px;
                font-weight: 400;
                font-size: 13px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: -9px;
                top: -3px;
                color: {title_color};
                font-size: 13px;
            }}
        """
        self.setStyleSheet(custom_style)

        # 按钮使用扁平操作按钮样式（与主配置窗口底部四按钮一致）
        flat_btn_style = Glassmorphism.get_flat_action_button_style(theme)
        for btn in [self._browse_browser_btn, self._clear_browser_btn,
                     self._auto_icon_btn,
                     self._browse_icon_btn, self._clear_icon_btn,
                     self._cancel_btn, self._ok_btn, self._latency_btn]:
            btn.setStyleSheet(flat_btn_style)
        for btn in getattr(self, "_url_var_buttons", []):
            btn.setStyleSheet(flat_btn_style)

        # 应用复选框样式
        cb_style = get_small_checkbox_stylesheet(theme)
        self.invert_theme_cb.setStyleSheet(cb_style)
        self.invert_current_cb.setStyleSheet(cb_style)
        self._apply_latency_result_style(*self._latency_result_state)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 10, 10)  # 特殊页边距：复杂编辑窗口保持 10px

        # 顶部标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("编辑打开网址" if self.shortcut.name else "添加打开网址")
        title_label.setStyleSheet("font-size: 12px; font-weight: 400; color: gray;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 基本信息
        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout(basic_group)
        basic_layout.setSpacing(6)
        basic_layout.setContentsMargins(8, 0, 8, 8)

        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(6)
        self.name_edit.setPlaceholderText("最多6个字符")
        basic_layout.addRow("名称:", self.name_edit)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("例如: https://www.google.com/search?q={input}")
        self.url_edit.textChanged.connect(self._update_icon_preview)
        self.url_edit.textChanged.connect(self._reset_latency_result)
        basic_layout.addRow("网址:", self.url_edit)

        latency_layout = QHBoxLayout()
        latency_layout.setSpacing(6)
        self._latency_btn = QPushButton("测试延迟")
        self._latency_btn.setFixedHeight(26)
        self._latency_btn.clicked.connect(self._test_url_latency)
        latency_layout.addWidget(self._latency_btn)
        self._latency_result_label = QLabel("未测试")
        self._latency_result_label.setMinimumHeight(20)
        self._latency_result_label.setStyleSheet("font-size: 12px; color: rgba(128, 128, 128, 0.9);")
        latency_layout.addWidget(self._latency_result_label)
        latency_layout.addStretch()
        basic_layout.addRow("延迟:", latency_layout)

        var_layout = QHBoxLayout()
        var_layout.setSpacing(6)
        self._url_var_buttons = []
        for text, token in (
            ("输入", "{input}"),
            ("剪贴板", "{clipboard}"),
            ("日期", "{date}"),
            ("时间", "{time}"),
        ):
            var_btn = QPushButton(text)
            var_btn.setFixedHeight(26)
            var_btn.clicked.connect(lambda checked=False, value=token: self._insert_url_variable(value))
            var_layout.addWidget(var_btn)
            self._url_var_buttons.append(var_btn)
        var_layout.addStretch()
        basic_layout.addRow("参数:", var_layout)

        layout.addWidget(basic_group)

        browser_group = QGroupBox("浏览器")
        browser_layout = QFormLayout(browser_group)
        browser_layout.setSpacing(6)
        browser_layout.setContentsMargins(8, 0, 8, 8)

        browser_path_layout = QHBoxLayout()
        browser_path_layout.setSpacing(6)
        self.browser_path_edit = QLineEdit()
        self.browser_path_edit.setPlaceholderText("留空使用系统默认浏览器")
        browser_path_layout.addWidget(self.browser_path_edit, 1)

        self._browse_browser_btn = QPushButton("浏览...")
        self._browse_browser_btn.clicked.connect(self._browse_browser)
        browser_path_layout.addWidget(self._browse_browser_btn)

        self._clear_browser_btn = QPushButton("清除")
        self._clear_browser_btn.clicked.connect(self._clear_browser)
        browser_path_layout.addWidget(self._clear_browser_btn)
        browser_layout.addRow("路径:", browser_path_layout)

        self.browser_args_edit = QLineEdit()
        self.browser_args_edit.setPlaceholderText("可选，例如 --profile-directory=Default {url}")
        browser_layout.addRow("参数:", self.browser_args_edit)
        layout.addWidget(browser_group)

        # 图标设置
        icon_group = QGroupBox("图标")
        icon_layout = QHBoxLayout(icon_group)
        icon_layout.setSpacing(6)
        icon_layout.setContentsMargins(6, 0, 6, 6)

        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(32, 32)
        self.icon_preview.setAlignment(QtCompat.AlignCenter)
        # 样式在 _apply_theme 中设置
        icon_layout.addWidget(self.icon_preview)

        icon_path_layout = QVBoxLayout()
        icon_path_layout.setSpacing(6)

        self.icon_path_edit = QLineEdit()
        self.icon_path_edit.setPlaceholderText("可选，自定义图标路径")
        self.icon_path_edit.setReadOnly(True)
        icon_path_layout.addWidget(self.icon_path_edit)

        icon_btn_layout = QHBoxLayout()
        icon_btn_layout.setSpacing(6)

        auto_icon_btn = QPushButton("自动获取")
        auto_icon_btn.clicked.connect(self._auto_fetch_icon)
        icon_btn_layout.addWidget(auto_icon_btn)
        self._auto_icon_btn = auto_icon_btn

        browse_icon_btn = QPushButton("选择图标...")
        browse_icon_btn.clicked.connect(self._browse_icon)
        icon_btn_layout.addWidget(browse_icon_btn)
        self._browse_icon_btn = browse_icon_btn

        clear_icon_btn = QPushButton("清除")
        clear_icon_btn.clicked.connect(self._clear_icon)
        icon_btn_layout.addWidget(clear_icon_btn)
        self._clear_icon_btn = clear_icon_btn

        icon_btn_layout.addStretch()
        icon_path_layout.addLayout(icon_btn_layout)

        # 图标反转选项（紧凑垂直排列，在清除按钮右侧）
        invert_v_layout = QVBoxLayout()
        invert_v_layout.setSpacing(2)
        invert_v_layout.setContentsMargins(0, 0, 0, 0)
        self.invert_theme_cb = QCheckBox("随主题反转")
        self.invert_theme_cb.setStyleSheet("""
            QCheckBox { font-size: 5px; spacing: 2px; }
            QCheckBox::indicator { width: 6px; height: 6px; border-radius: 1px; border: 1px solid #888; background: transparent; }
            QCheckBox::indicator:checked { background: #0A84FF; border-color: #0A84FF; }
        """)
        self.invert_current_cb = QCheckBox("当前反转")
        self.invert_current_cb.setStyleSheet("""
            QCheckBox { font-size: 5px; spacing: 2px; }
            QCheckBox::indicator { width: 6px; height: 6px; border-radius: 1px; border: 1px solid #888; background: transparent; }
            QCheckBox::indicator:checked { background: #0A84FF; border-color: #0A84FF; }
        """)
        self.invert_current_cb.setEnabled(False)
        self.invert_theme_cb.stateChanged.connect(self._on_invert_theme_changed)
        invert_v_layout.addWidget(self.invert_theme_cb)
        invert_v_layout.addWidget(self.invert_current_cb)
        icon_btn_layout.addLayout(invert_v_layout)

        icon_layout.addLayout(icon_path_layout, 1)
        layout.addWidget(icon_group)

        layout.addStretch()

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(80, 32)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        self._cancel_btn = cancel_btn

        ok_btn = QPushButton("确定")
        ok_btn.setFixedSize(80, 32)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)
        self._ok_btn = ok_btn

        layout.addLayout(btn_layout)

    def _load_data(self):
        """加载数据"""
        self.name_edit.setText(self.shortcut.name or "")
        self.url_edit.setText(self.shortcut.url or "")
        self.browser_path_edit.setText(getattr(self.shortcut, "preferred_browser_path", "") or "")
        self.browser_args_edit.setText(getattr(self.shortcut, "preferred_browser_args", "") or "")

        if self._custom_icon_path:
            self.icon_path_edit.setText(self._custom_icon_path)

        # 加载反转设置
        self.invert_theme_cb.setChecked(self.shortcut.icon_invert_with_theme)
        self.invert_current_cb.setChecked(self.shortcut.icon_invert_current)

        self._update_icon_preview()

    def _insert_url_variable(self, text: str):
        cursor = self.url_edit.cursorPosition()
        current = self.url_edit.text()
        self.url_edit.setText(current[:cursor] + text + current[cursor:])
        self.url_edit.setCursorPosition(cursor + len(text))
        self.url_edit.setFocus()

    def _reset_latency_result(self, *args):
        if getattr(self, "_latency_thread", None) and self._latency_thread.isRunning():
            return
        self._set_latency_result("未测试", "muted")

    def _test_url_latency(self):
        if getattr(self, "_dialog_finished", False) or not self.isVisible():
            return
        url = self.url_edit.text().strip()
        if not url:
            self.url_edit.setFocus()
            self._set_latency_result("-1 网址为空", "red")
            return

        if getattr(self, "_latency_thread", None) and self._latency_thread.isRunning():
            return

        self._latency_request_id += 1
        self._latency_btn.setEnabled(False)
        self._set_latency_result("测试中...", "muted")
        self._latency_thread = UrlLatencyTestThread(url, {"input": "test"}, parent=None)
        self._latency_thread.request_id = self._latency_request_id
        self._latency_thread.finished_signal.connect(self._show_latency_result)
        self._latency_thread.start()

    def _show_latency_result(self, result: dict):
        if getattr(self, "_dialog_finished", False) or not self.isVisible():
            return
        if result.get("request_id") != getattr(self, "_latency_request_id", 0):
            return

        current_url, current_error = self._normalize_latency_target(self.url_edit.text().strip())
        if current_error:
            self._set_latency_result("未测试", "muted")
            self._latency_btn.setEnabled(True)
            self._latency_thread = None
            return
        if current_url and result.get("url") and current_url != result.get("url"):
            self._set_latency_result("未测试", "muted")
            self._latency_btn.setEnabled(True)
            self._latency_thread = None
            return

        latency_ms = int(result.get("latency_ms", -1))
        color = result.get("color") or "red"
        error = result.get("error") or ""

        if latency_ms < 0:
            if "超时" in error:
                text = "超时"
            else:
                text = "无法访问"
            if error and "无法访问" not in text and "超时" not in text:
                text = f"{text} ({error})"
        else:
            text = f"延迟 {latency_ms} ms"
            if error:
                text = f"{text} ({error})"

        self._set_latency_result(text, color)
        self._latency_btn.setEnabled(True)
        self._latency_thread = None

    def _set_latency_result(self, text: str, color: str):
        self._latency_result_state = (color, text)
        self._apply_latency_result_style(color, text)

    def _apply_latency_result_style(self, color: str, text: str):
        theme = getattr(self, "theme", "dark")
        palette = {
            "green": "#16A34A",
            "yellow": "#D97706",
            "red": "#DC2626",
            "muted": "rgba(0, 0, 0, 0.45)",
        }
        dark_palette = {
            "green": "#4ADE80",
            "yellow": "#FBBF24",
            "red": "#F87171",
            "muted": "rgba(255, 255, 255, 0.45)",
        }
        fg = (dark_palette if theme == "dark" else palette).get(color, "gray")

        display_text = text
        if text == "未测试":
            display_text = "未测试"
        elif text == "测试中...":
            display_text = "●  测试中..."
        else:
            if not text.startswith("●"):
                display_text = f"●  {text}"

        self._latency_result_label.setText(display_text)
        self._latency_result_label.setStyleSheet(
            f"font-size: 12px; color: {fg}; background-color: transparent; border: none; padding: 2px 4px;"
        )

    def _normalize_latency_target(self, raw_url: str) -> tuple[str, str]:
        try:
            from core.shortcut_url_exec import UrlExecutionMixin
            return UrlExecutionMixin._prepare_url(raw_url, {"input": "test"})
        except Exception as e:
            return "", str(e)

    def _browse_browser(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择浏览器",
            "",
            "可执行文件 (*.exe);;所有文件 (*.*)",
        )
        if file_path:
            self.browser_path_edit.setText(file_path)

    def _clear_browser(self):
        self.browser_path_edit.clear()
        self.browser_args_edit.clear()

    def _auto_fetch_icon(self):
        url = self.url_edit.text().strip()
        if not url:
            self.url_edit.setFocus()
            return

        if getattr(self, "_icon_fetch_thread", None) and self._icon_fetch_thread.isRunning():
            return

        self._icon_fetch_request_id += 1
        self._auto_icon_btn.setEnabled(False)
        self._auto_icon_btn.setText("获取中...")
        self._icon_fetch_thread = UrlIconFetchThread(url, parent=None)
        self._icon_fetch_thread.request_id = self._icon_fetch_request_id
        self._icon_fetch_thread.finished_signal.connect(self._show_auto_icon_result)
        self._icon_fetch_thread.start()

    def _show_auto_icon_result(self, result: dict):
        if getattr(self, "_dialog_finished", False) or not self.isVisible():
            return
        if result.get("request_id") != getattr(self, "_icon_fetch_request_id", 0):
            return

        icon_path = result.get("icon_path") or ""
        if icon_path and os.path.exists(icon_path):
            self._custom_icon_path = icon_path
            self.icon_path_edit.setText(icon_path)
            self.invert_theme_cb.setChecked(False)
            self.invert_current_cb.setChecked(False)
            self._update_icon_preview()
            self._auto_icon_btn.setText("自动获取")
        else:
            self._auto_icon_btn.setText("未获取到")
            QTimer.singleShot(1200, self._restore_auto_icon_button)

        self._auto_icon_btn.setEnabled(True)
        self._icon_fetch_thread = None

    def _restore_auto_icon_button(self):
        if getattr(self, "_dialog_finished", False) or not self.isVisible():
            return
        self._auto_icon_btn.setText("自动获取")

    def _update_icon_preview(self):
        """更新图标预览"""
        pixmap = None

        # 1. 尝试加载自定义图标
        if self._custom_icon_path and os.path.exists(self._custom_icon_path):
            try:
                from core.icon_extractor import IconExtractor
                pixmap = IconExtractor.from_file(self._custom_icon_path, 48)
            except Exception:
                pass

        # 3. 默认图标
        if not pixmap or pixmap.isNull():
            pixmap = self._create_url_icon(48)

        # 应用反转
        if self.invert_theme_cb.isChecked() and self.invert_current_cb.isChecked() and pixmap and not pixmap.isNull():
            from core.icon_extractor import IconExtractor
            pixmap = IconExtractor.invert_pixmap(pixmap)

        # 缩放到预览尺寸
        if pixmap and not pixmap.isNull():
            pixmap = pixmap.scaled(32, 32, QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)

        self.icon_preview.setPixmap(pixmap)

    def _create_url_icon(self, size: int) -> QPixmap:
        """创建URL图标"""
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCompat.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)

        # 使用更柔和的颜色
        painter.setBrush(QColor(60, 160, 120))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        painter.drawRoundedRect(margin, margin, size - margin*2, size - margin*2, 8, 8)

        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI Symbol", size // 3)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "🌐")

        painter.end()
        return pixmap

    def _browse_icon(self):
        """浏览图标文件"""
        file_path = choose_custom_icon(self, "选择图标")

        if file_path:
            self._custom_icon_path = file_path
            self.icon_path_edit.setText(file_path)
            self.invert_theme_cb.setChecked(False)
            self.invert_current_cb.setChecked(False)
            self._update_icon_preview()

    def _clear_icon(self):
        """清除自定义图标"""
        self._custom_icon_path = ""
        self.icon_path_edit.clear()
        self.invert_theme_cb.setChecked(False)
        self.invert_current_cb.setChecked(False)
        self._update_icon_preview()

    def _on_invert_theme_changed(self, state):
        """随主题反转勾选变化"""
        self.invert_current_cb.setEnabled(bool(state))
        if not state:
            self.invert_current_cb.setChecked(False)
        self._update_icon_preview()

    def _on_ok(self):
        """确定"""
        name = self.name_edit.text().strip()
        url = self.url_edit.text().strip()

        if not name:
            self.name_edit.setFocus()
            return

        if not url:
            self.url_edit.setFocus()
            return

        try:
            from core.shortcut_url_exec import UrlExecutionMixin
            _, error = UrlExecutionMixin._prepare_url(url, {"input": "test"})
            if error:
                self.url_edit.setFocus()
                return
        except Exception:
            pass

        self.accept()

    def get_shortcut(self) -> ShortcutItem:
        """获取快捷方式"""
        self.shortcut.name = self.name_edit.text().strip()[:6]
        self.shortcut.url = self.url_edit.text().strip()
        self.shortcut.preferred_browser_path = self.browser_path_edit.text().strip()
        self.shortcut.preferred_browser_args = self.browser_args_edit.text().strip()
        self.shortcut.icon_path = self._custom_icon_path
        self.shortcut.type = ShortcutType.URL
        self.shortcut.icon_invert_with_theme = self.invert_theme_cb.isChecked()
        self.shortcut.icon_invert_current = self.invert_current_cb.isChecked()
        if self.invert_theme_cb.isChecked():
            self.shortcut.icon_invert_theme_when_set = getattr(self, 'theme', 'dark')
        return self.shortcut

    def done(self, result):
        self._dialog_finished = True
        self._cleanup_background_threads()
        super().done(result)

    def _cleanup_background_threads(self):
        for attr, slot in (
            ("_latency_thread", self._show_latency_result),
            ("_icon_fetch_thread", self._show_auto_icon_result),
        ):
            thread = getattr(self, attr, None)
            if thread is None:
                continue
            try:
                thread.finished_signal.disconnect(slot)
            except Exception:
                pass
            try:
                thread.suppress_result_signal()
            except Exception:
                pass
            if thread.isRunning():
                thread.wait(500)
            if thread.isRunning():
                try:
                    thread.terminate()
                    thread.wait(200)
                except Exception:
                    pass
            if thread.isRunning():
                try:
                    thread.setParent(None)
                    self._orphaned_threads.append(thread)
                    thread.finished.connect(lambda t=thread, cls=type(self): cls._forget_orphaned_thread(t))
                    thread.finished.connect(thread.deleteLater)
                except Exception:
                    pass
                setattr(self, attr, None)
            else:
                try:
                    thread.deleteLater()
                except Exception:
                    pass
                setattr(self, attr, None)

    @classmethod
    def _forget_orphaned_thread(cls, thread):
        try:
            cls._orphaned_threads.remove(thread)
        except ValueError:
            pass

    def showEvent(self, event):
        """显示时进行延迟测试"""
        super().showEvent(event)

        # 打开窗口时，如果有已填入的网址，且未自动测试过，则自动进行一次延迟测试
        if not getattr(self, "_has_auto_tested", False):
            self._has_auto_tested = True
            url = self.url_edit.text().strip()
            if url:
                # 延迟一小段时间触发，使窗口动画和加载更流畅
                QTimer.singleShot(400, self._test_url_latency)
