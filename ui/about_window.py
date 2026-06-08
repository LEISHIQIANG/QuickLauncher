"""About QuickLauncher dialog - text-only, no icon, no scrollbar, no frames."""

from __future__ import annotations

from core import APP_VERSION
from core.i18n import tr
from qt_compat import QLabel
from ui.themed_tool_window import ThemedToolWindow
from ui.utils.font_manager import get_qfont
from ui.utils.ui_scale import font_px, sp, scale_qss

_ABOUT_SECTIONS = [
    (
        "简介",
        (
            "QuickLauncher 是一款面向 Windows 桌面的快速启动与轻量自动化工具。"
            "按下鼠标中键呼出启动面板，集中管理常用程序、文件夹、网址、命令和快捷键；"
            "支持搜索、Dock、分类同步、拖拽投递、智能排序、配置备份和高度自定义外观。"
        ),
    ),
    (
        "基本操作",
        (
            "中键呼出弹窗，再次中键 / Esc / 点击外部区域即隐藏；"
            "输入关键字模糊搜索名称、别名和标签，Enter 执行、方向键切换；"
            "右键锁定弹窗防止自动隐藏，滚轮或 ←→ 翻页切换分类。"
        ),
    ),
    (
        "快捷方式",
        (
            "四类快捷方式：启动程序或文件（支持参数、工作目录、管理员运行），"
            "打开文件夹，访问网址（支持指定浏览器和延迟测试），"
            "运行命令（CMD / PowerShell / Python / 内置命令，支持变量解析），"
            "录制快捷键（区分左右修饰键、测试发送）。"
        ),
    ),
    (
        "分类与同步",
        (
            "左侧分类栏可创建、重命名、拖拽排序；Dock 分类放置高频项目；"
            "拖入物理文件夹自动导入 .lnk 和 .exe，支持手动或自动同步。"
        ),
    ),
    (
        "高级功能",
        (
            "命令变量：{{clipboard}}、{{input}}、{{date}}、{{time}} 等动态替换；"
            "拖放文件到图标即用该程序打开；Ctrl + 滚轮调节背景透明度；"
            "Alt + 双击暂停/恢复中键弹窗；轻睡眠、图标缓存清理等稳定性辅助。"
        ),
    ),
    (
        "配置管理",
        (
            "支持完整配置包的导出、导入和分享；"
            "自动保存最近 20 次配置快照，可随时回滚；"
            "图标路径失效时自动在同目录重定向修复。"
        ),
    ),
]


class AboutWindow(ThemedToolWindow):
    """纯文本关于窗口，无图标，无滚动条，无底框，高度自适应。"""

    def __init__(self, theme: str = "light", parent=None):
        super().__init__(tr("关于 QuickLauncher"), theme=theme, parent=parent)
        self.setFixedWidth(sp(560))
        self.setMinimumWidth(sp(400))
        self.root_layout.setContentsMargins(sp(12), 0, 0, sp(12))
        self.content_layout.setContentsMargins(0, 0, sp(12), 0)
        self.button_layout.setContentsMargins(0, 0, sp(12), 0)
        self.icon_label.setVisible(False)
        self.set_subtitle("")
        self.content_layout.setSpacing(sp(4))
        self._setup_about_ui()
        self._apply_content_theme()
        self._fit_to_content()

    def _setup_about_ui(self):
        title = QLabel("QuickLauncher")
        title.setObjectName("about_title")
        title.setFont(get_qfont(14, 400))
        self.content_layout.addWidget(title)

        version = QLabel(tr("版本 {version}", version=APP_VERSION))
        version.setObjectName("about_version")
        version.setFont(get_qfont(12, 400))
        self.content_layout.addWidget(version)

        for section_title, body in _ABOUT_SECTIONS:
            hdr = QLabel(tr(section_title))
            hdr.setObjectName("about_section")
            hdr.setFont(get_qfont(12, 400))
            self.content_layout.addWidget(hdr)

            body_label = QLabel(tr(body))
            body_label.setObjectName("about_body")
            body_label.setWordWrap(True)
            body_label.setFont(get_qfont(12, 400))
            self.content_layout.addWidget(body_label)

    def _apply_content_theme(self):
        theme = self._theme
        if theme == "dark":
            title_color = "rgba(255, 255, 255, 0.95)"
            version_color = "rgba(255, 255, 255, 0.4)"
            section_color = "rgba(255, 255, 255, 0.72)"
            body_color = "rgba(255, 255, 255, 0.55)"
        else:
            title_color = "rgba(28, 28, 30, 0.95)"
            version_color = "rgba(60, 60, 67, 0.45)"
            section_color = "rgba(28, 28, 30, 0.68)"
            body_color = "rgba(60, 60, 67, 0.6)"

        for widget in self.findChildren(QLabel):
            name = widget.objectName()
            if name == "about_title":
                widget.setStyleSheet(f"color: {title_color}; background: transparent; font-weight: 400;")
            elif name == "about_version":
                widget.setStyleSheet(scale_qss(f"color: {version_color}; background: transparent; padding-left: 2px;"))
            elif name == "about_section":
                widget.setStyleSheet(
                    scale_qss(f"color: {section_color}; background: transparent; font-weight: 400; margin-top: 6px;")
                )
            elif name == "about_body":
                widget.setStyleSheet(
                    scale_qss(f"color: {body_color}; background: transparent; padding-left: 4px; line-height: 1.55;")
                )

    def _fit_to_content(self):
        self.updateGeometry()

        # 测量内容区可用宽度（固定宽度减去左右边距和间距）
        root_margins = self.root_layout.contentsMargins()
        content_margins = self.content_layout.contentsMargins()
        available_w = (
            sp(560) - root_margins.left() - root_margins.right() - content_margins.left() - content_margins.right()
        )

        total_h = 0
        spacing = self.content_layout.spacing()
        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            widget = item.widget()
            if widget is None:
                continue
            if hasattr(widget, "wordWrap") and widget.wordWrap():
                h = widget.heightForWidth(available_w)
            else:
                h = widget.sizeHint().height()
            total_h += h
            if i > 0:
                total_h += spacing

        # 加上根布局边距、标题栏等 chrome 高度
        chrome_h = self.root_layout.contentsMargins().top() + self.root_layout.contentsMargins().bottom()
        title_h = self.title_label.sizeHint().height()
        close_h = self.close_btn_top.sizeHint().height()
        chrome_h += max(title_h, close_h) + self.root_layout.spacing() * 3
        # 再加上 button_layout（空的隐藏占位）
        chrome_h += self.button_layout.contentsMargins().top() + self.button_layout.contentsMargins().bottom()

        self.setFixedHeight(total_h + chrome_h)
