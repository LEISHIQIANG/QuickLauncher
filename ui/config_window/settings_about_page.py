"""About settings page builder."""

import logging
import os

from core import APP_VERSION
from core.i18n import tr
from qt_compat import (
    QFrame,
    QHBoxLayout,
    QIcon,
    QLabel,
    Qt,
    QtCompat,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)


class AboutCardFrame(QFrame):
    """用于关于页面的高级玻璃拟态卡片容器。"""

    def __init__(self, theme="dark", parent=None):
        super().__init__(parent)
        self.setObjectName("AboutCardFrame")
        self.update_theme(theme)

    def update_theme(self, theme):
        self.setStyleSheet("""
            #AboutCardFrame {
                background: transparent;
                border: none;
            }
        """)


class AboutQuoteFrame(QFrame):
    """带有左侧高对比度呼吸渐变/纯色点缀条的优雅简介卡片。"""

    def __init__(self, theme="dark", parent=None):
        super().__init__(parent)
        self.setObjectName("AboutQuoteFrame")
        self.update_theme(theme)

    def update_theme(self, theme):
        self.setStyleSheet("""
            #AboutQuoteFrame {
                background: transparent;
                border: none;
            }
        """)


# 结构化卡片展示数据定义
SECTION_DATA = {
    "基本操作": [
        {
            "title": "呼出弹窗",
            "points": [
                "在任意位置按下鼠标中键，弹窗会按设置显示在鼠标附近",
                "支持普通中键、特殊应用中的 Ctrl + 中键，以及全局热键 fallback",
            ],
        },
        {
            "title": "隐藏弹窗",
            "points": [
                "再次按下鼠标中键，或点击弹窗外部的任意区域",
                "按下 Esc 键，或在启动项目后自动隐藏（可在弹窗交互中开关）",
            ],
        },
        {
            "title": "搜索和执行",
            "points": [
                "弹窗打开后直接输入关键字进行模糊匹配（支持名称、别名、标签）",
                "支持快捷网页搜索：g (Google)、b (Baidu)、y (Yandex)、e (Bing)",
                "斜杠命令模式：输入 / 快速执行系统动作，如 /config、/quit 等",
            ],
        },
        {
            "title": "锁定与翻页",
            "points": [
                "右键点击弹窗空白区或右上角图钉，弹窗将不会自动隐藏",
                "支持鼠标滚轮滚动或左右方向键（←/→）进行流畅的分类翻页",
            ],
        },
    ],
    "添加与管理": [
        {
            "title": "拖拽添加（推荐）",
            "points": [
                "将程序、文件、文件夹或快捷方式直接拖入弹窗或设置窗口中",
                "支持桌面、文件资源管理器、开始菜单拖拽，支持一键批量拖入",
            ],
        },
        {
            "title": "五类快捷入口",
            "points": [
                "<b>快捷方式</b>：配置启动参数、工作目录、以及管理员运行权限",
                "<b>网址与目录</b>：支持延迟测试，使用默认或指定浏览器及命令行参数",
                "<b>命令与快捷键</b>：运行 CMD、Python 脚本以及录制发送复杂组合键",
            ],
        },
        {
            "title": "批量管理与重定向",
            "points": [
                "支持 Ctrl/Shift 多选图标进行批量删除、移动、启用与禁用（支持撤销）",
                "提供独立图标仓库，在图标路径失效时支持在目录中自动重定向",
            ],
        },
    ],
    "分类与同步": [
        {
            "title": "分类与 Dock 栏",
            "points": [
                "左侧分类栏支持新建、重命名、上下拖拽重排与快速删除",
                "提供专用常驻 Dock 分类，用于放置高频全局快捷入口",
            ],
        },
        {
            "title": "物理文件夹同步",
            "points": [
                "拖入本地文件夹即可自动生成动态分类，增量同步 Lnk 与 Exe 文件",
                "物理同步监听文件新增、删除与重命名，防止手动拖放引起的冲突",
            ],
        },
    ],
    "高级功能": [
        {
            "title": "命令与网址变量",
            "points": [
                "支持 {{clipboard}}、{{input}}、{{date}}、{{time}} 等丰富环境变量",
                "支持 {{selected_text}}，配合 :q 安全引用规则，实现选中即处理",
            ],
        },
        {
            "title": "高级物理反馈",
            "points": [
                "<b>文件投递</b>：支持将任意文件拖到快捷图标上，调用对应程序打开",
                "<b>触控调节</b>：Ctrl/Shift + 鼠标滚轮精细微调弹窗背景与图标透明度",
                "<b>轻睡眠模式</b>：双击 Alt 临时暂停热键弹窗，支持内存整理与睡眠保护",
            ],
        },
    ],
    "配置管理": [
        {
            "title": "完整环境备份",
            "points": [
                "导出独立配置包，完美备份所有设置、分类、本地图标、背景等资源",
                "适合在新机上瞬间恢复工作环境，或将配置轻松回滚到之前备份",
            ],
        },
        {
            "title": "社交化分享配置",
            "points": [
                "可单独导出网址或命令分类，自动隐藏本地敏感路径生成分享包",
                "导入分享配置时会自动建立隔离的「导入图标」分类，极度安全",
            ],
        },
    ],
    "使用技巧": [
        {
            "title": "按键防冲突机制",
            "points": [
                "自定义防冲突进程列表（如 CAD、3D 建模、大型游戏或设计软件）",
                "在此类全屏或特定应用中，必须使用 Ctrl + 中键呼出，完美防误触",
            ],
        },
        {
            "title": "后台无感与托盘",
            "points": [
                "支持开机静默自启动，并可选择彻底隐藏托盘图标实现完全无感后台",
                "托盘菜单支持一键查看精细运行日志、快捷配置同步、重启或安全退出",
            ],
        },
    ],
}


def _generate_html_content(items, theme):
    """根据主题渲染高规格排版的 RichText HTML 内容。"""
    title_color = "#ffffff" if theme == "dark" else "#1c1c1e"
    desc_color = "#a1a1a6" if theme == "dark" else "#555559"
    bullet_color = "#ff9500"

    html = "<div style=\"font-family: 'Segoe UI', 'Microsoft YaHei UI'; padding: 4px 6px;\">"
    for idx, item in enumerate(items):
        title = tr(item["title"])
        points = [tr(point) for point in item["points"]]

        margin_top = "0px" if idx == 0 else "12px"

        html += f'<div style="margin-top: {margin_top};">'
        # 子项标题 (✦ 点缀)
        html += f'<div style="font-size: 13px; font-weight: 400; color: {title_color}; margin-bottom: 4px;">'
        html += f'<span style="color: {bullet_color}; margin-right: 6px;">✦</span>{title}</div>'

        # 点描述
        html += f'<div style="font-size: 12px; color: {desc_color}; line-height: 1.6; padding-left: 14px;">'
        for pt in points:
            html += f'<div style="margin-bottom: 2px;">• {pt}</div>'
        html += "</div></div>"

    html += "</div>"
    return html


def _generate_intro_html(theme):
    """简介卡片富文本排版。"""
    text_color = "#d1d1d6" if theme == "dark" else "#3a3a3c"
    return f"""
    <div style="font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 13px; color: {text_color}; line-height: 1.6;">
        {tr("QuickLauncher 是一款面向 Windows 桌面的极速启动与轻量自动化效率工具。")}<br/><br/>
        {tr("按下鼠标中键即可快速呼出启动面板，集中管理常用程序、文件夹、网址、命令和快捷键；")}
        {tr("同时支持搜索、Dock、分类同步、拖拽投递、智能排序、配置备份和高度自定义外观。")}
    </div>
    """


class SettingsAboutPageMixin:
    def _setup_about_page(self, page):
        self.theme = "dark"

        # 尝试从 DataManager 读取当前主题，或者跟随 Mixin 环境
        if hasattr(self, "data_manager"):
            self.theme = self.data_manager.get_settings().theme

        # 1. 软件信息头部区域
        layout, group = page.add_group(tr("关于 QuickLauncher"))
        layout.setContentsMargins(0, 0, 0, 0)

        header_card = AboutCardFrame(self.theme, group)
        header_card_layout = QHBoxLayout(header_card)
        header_card_layout.setContentsMargins(16, 16, 16, 16)
        header_card_layout.setSpacing(16)

        # 尝试加载图标
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            icon_path = os.path.join(base_dir, "assets", "app.ico")
            if not os.path.exists(icon_path):
                icon_path = os.path.join(base_dir, "app.ico")

            if os.path.exists(icon_path):
                icon_label = QLabel(header_card)
                icon_label.setFixedSize(64, 64)
                pixmap = QIcon(icon_path).pixmap(64, 64)
                if pixmap and not pixmap.isNull():
                    icon_label.setPixmap(pixmap.scaled(64, 64, QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation))
                    header_card_layout.addWidget(icon_label)
        except Exception:
            logger.debug("加载关于页图标失败", exc_info=True)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(0)
        title_layout.setContentsMargins(0, 0, 0, 0)

        # 联动生成标题与胶囊 Badge
        title_lbl = QLabel(header_card)
        title_lbl.setTextFormat(Qt.RichText)
        title_lbl.setWordWrap(True)
        title_layout.addWidget(title_lbl)

        # 联动生成软件口号
        slogan_lbl = QLabel(header_card)
        slogan_lbl.setTextFormat(Qt.RichText)
        slogan_lbl.setWordWrap(True)
        title_layout.addWidget(slogan_lbl)

        # 联动生成开发者精致 Badge
        developer_lbl = QLabel(header_card)
        developer_lbl.setTextFormat(Qt.RichText)
        developer_lbl.setOpenExternalLinks(True)  # 允许点击链接直接跳转浏览器
        title_layout.addWidget(developer_lbl)

        header_card_layout.addLayout(title_layout)
        header_card_layout.addStretch()
        layout.addWidget(header_card)

        # 保存组件引用以便动态主题切换
        page._header_card = header_card
        page._title_lbl = title_lbl
        page._slogan_lbl = slogan_lbl
        page._developer_lbl = developer_lbl

        # 2. 软件简介 quote 卡片
        layout, group = page.add_group(tr("软件简介"))
        layout.setContentsMargins(0, 0, 0, 0)
        intro_card = AboutQuoteFrame(self.theme, group)
        intro_layout = QVBoxLayout(intro_card)
        # 用 Qt 原生 layout margin 来控制左右上下的安全呼吸间距，绝对防止 PyQt RichText 对 HTML padding 属性的裁剪缺陷
        intro_layout.setContentsMargins(18, 14, 18, 14)

        intro_lbl = QLabel(intro_card)
        intro_lbl.setTextFormat(Qt.RichText)
        intro_lbl.setWordWrap(True)
        intro_layout.addWidget(intro_lbl)
        layout.addWidget(intro_card)

        page._intro_group = group
        page._intro_card = intro_card
        page._intro_lbl = intro_lbl

        # 3. 遍历渲染 6 大功能卡片
        page._feature_cards = []
        page._feature_lbls = []
        page._feature_card_data = []

        for section_title, items in SECTION_DATA.items():
            layout, group = page.add_group(tr(section_title))
            layout.setContentsMargins(0, 0, 0, 0)

            card = AboutCardFrame(self.theme, group)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 12, 12, 12)

            lbl = QLabel(card)
            lbl.setTextFormat(Qt.RichText)
            lbl.setWordWrap(True)
            card_layout.addWidget(lbl)

            layout.addWidget(card)

            # 保存到引用管理器以支持主题响应
            page._feature_cards.append(card)
            page._feature_lbls.append(lbl)
            page._feature_card_data.append((section_title, items))

        # 4. 精致极简底栏区 (作者与开源信息)
        layout, group = page.add_group(tr("作者信息"))
        layout.setContentsMargins(0, 0, 0, 0)
        footer_card = AboutCardFrame(self.theme, group)
        footer_layout = QHBoxLayout(footer_card)
        footer_layout.setContentsMargins(16, 10, 16, 10)
        # 左侧：开发者
        left_lbl = QLabel(footer_card)
        left_lbl.setTextFormat(Qt.RichText)
        left_lbl.setWordWrap(False)
        footer_layout.addWidget(left_lbl)

        footer_layout.addStretch()

        # 中间：许可证
        center_lbl = QLabel(footer_card)
        center_lbl.setTextFormat(Qt.RichText)
        center_lbl.setWordWrap(False)
        center_lbl.setAlignment(Qt.AlignCenter)
        footer_layout.addWidget(center_lbl)

        footer_layout.addStretch()

        # 右侧：感谢
        right_lbl = QLabel(footer_card)
        right_lbl.setTextFormat(Qt.RichText)
        right_lbl.setWordWrap(False)
        footer_layout.addWidget(right_lbl)

        layout.addWidget(footer_card)

        page._footer_card = footer_card
        page._footer_lbl = left_lbl
        page._center_footer_lbl = center_lbl
        page._right_footer_lbl = right_lbl

        # 5. 主题与睡眠/唤醒钩子修补，实现动态主题适配
        original_apply_theme = page.apply_theme

        def custom_apply_theme(theme):
            original_apply_theme(theme)
            self._update_about_page_theme(page, theme)

        page.apply_theme = custom_apply_theme

        # 首次创建时主动应用当前主题渲染
        self._update_about_page_theme(page, self.theme)

    def _update_about_page_theme(self, page, theme):
        """动态渲染所有卡片、边框及 RichText 文本以适应新主题。"""
        # 1. 更新卡片背景与边框 QSS
        if hasattr(page, "_header_card") and page._header_card:
            page._header_card.update_theme(theme)
        if hasattr(page, "_intro_card") and page._intro_card:
            page._intro_card.update_theme(theme)
        if hasattr(page, "_footer_card") and page._footer_card:
            page._footer_card.update_theme(theme)
        if hasattr(page, "_feature_cards"):
            for card in page._feature_cards:
                card.update_theme(theme)

        # 针对 "软件简介" 组的特殊左侧边栏高亮处理 (代替之前的 AboutQuoteFrame 左边框)
        if hasattr(page, "_intro_group") and page._intro_group:
            bg_color = "rgba(255, 255, 255, 0.05)" if theme == "dark" else "rgba(0, 0, 0, 0.03)"
            border_color = "rgba(255, 255, 255, 0.08)" if theme == "dark" else "rgba(0, 0, 0, 0.06)"
            text_color = "rgba(255, 255, 255, 0.9)" if theme == "dark" else "rgba(28, 28, 30, 0.9)"
            page._intro_group.setStyleSheet(f"""
                QGroupBox {{
                    background-color: {bg_color};
                    border: 1px solid {border_color};
                    border-radius: 12px;
                    color: {text_color};
                    margin-top: 18px;
                    padding-top: 10px;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 14px;
                    padding: 2px 10px;
                    background: transparent;
                    color: {text_color};
                    font-weight: 400;
                }}
            """)

        # 2. 渲染特定主题的文字与 Badge 标记
        title_color = "#ffffff" if theme == "dark" else "#1c1c1e"
        desc_color = "#a1a1a6" if theme == "dark" else "#636366"
        version_color = "#ffffff" if theme == "dark" else "#3a3a3c"
        dev_badge_bg = "rgba(255, 149, 0, 0.15)"
        dev_badge_color = "#ff9500"

        if hasattr(page, "_title_lbl") and page._title_lbl:
            title_html = f"""
            <div style="font-family: 'Segoe UI', 'Microsoft YaHei UI'; margin-bottom: 4px;">
                <span style="font-size: 22px; font-weight: 400; color: {title_color};">QuickLauncher</span>
                <span style="font-size: 13px; font-weight: 400; color: {version_color}; margin-left: 8px; vertical-align: middle;">v{APP_VERSION}</span>
            </div>
            """
            page._title_lbl.setText(title_html)

        if hasattr(page, "_slogan_lbl") and page._slogan_lbl:
            slogan_html = f"""
            <div style="font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 12px; color: {desc_color}; margin-bottom: 8px;">
                {tr("Windows 极速快捷启动与轻量自动化效率工具")}
            </div>
            """
            page._slogan_lbl.setText(slogan_html)

        if hasattr(page, "_developer_lbl") and page._developer_lbl:
            dev_html = f"""
            <div style="font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 11px; line-height: 1.3;">
                <span style="display: inline-block; background-color: {dev_badge_bg}; color: {dev_badge_color}; padding: 2px 6px; border-radius: 4px; font-weight: 400; border: 1.0px solid rgba(255, 149, 0, 0.3);">⚡ {tr("开发者: NAYTON")}</span><br/>
                <a href="https://github.com/LEISHIQIANG/QuickLauncher"
                   style="color: {dev_badge_color}; font-size: 11px; text-decoration: none;"
                >GitHub.com/LEISHIQIANG/QuickLauncher</a>
            </div>
            """
            page._developer_lbl.setText(dev_html)

        if hasattr(page, "_intro_lbl") and page._intro_lbl:
            page._intro_lbl.setText(_generate_intro_html(theme))

        if hasattr(page, "_feature_lbls") and hasattr(page, "_feature_card_data"):
            for lbl, (_section_title, data) in zip(page._feature_lbls, page._feature_card_data):
                lbl.setText(_generate_html_content(data, theme))

        if hasattr(page, "_footer_lbl") and page._footer_lbl:
            left_html = f"""<div style="font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 12px; color: {desc_color};">⚡ {tr("开发者: NAYTON")}</div>"""
            page._footer_lbl.setText(left_html)

        if hasattr(page, "_center_footer_lbl") and page._center_footer_lbl:
            center_html = f"""<div style="font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 12px; color: {desc_color}; text-align: center;">{tr("开源协议：MIT License")}</div>"""
            page._center_footer_lbl.setText(center_html)

        if hasattr(page, "_right_footer_lbl") and page._right_footer_lbl:
            right_html = f"""<div style="font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 12px; color: {desc_color}; text-align: right;">⭐ {tr("感谢您的支持！")}</div>"""
            page._right_footer_lbl.setText(right_html)
