"""动作链编辑对话框 — 左右两栏布局，卡片式步骤，风险分析，测试运行。"""

from __future__ import annotations

import copy
import logging
import os

from core import ShortcutItem, ShortcutType
from core.i18n import tr
from core.shortcut_icon_helpers import default_folder_icon_path, shortcut_uses_folder_icon
from qt_compat import (
    QCheckBox,
    QColor,
    QEvent,
    QFont,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPainter,
    QPixmap,
    QPlainTextEdit,
    QPushButton,
    QRectF,
    QScrollArea,
    Qt,
    QTabWidget,
    QtCompat,
    QVBoxLayout,
    QWidget,
)
from ui.styles.style import Colors, Glassmorphism, PopupMenu
from ui.utils.ui_scale import scale_qss, sp

from .base_dialog import BaseDialog
from .chain_canvas import ChainCanvasWidget, NodePropertyPanel, canvas_from_steps, processor_library_items
from .chain_dialog_bindings import ChainDialogBindingsMixin
from .chain_dialog_close_animation import ChainDialogCloseAnimationMixin
from .chain_dialog_module_bar import GrasshopperGroupWidget, make_module_button
from .chain_dialog_risk import ChainDialogRiskMixin
from .chain_dialog_step_card import StepCardWidget
from .chain_dialog_test_runner import ChainDialogTestRunnerMixin
from .icon_browse_helper import choose_custom_icon
from .theme_helper import get_compact_checkbox_stylesheet, get_small_checkbox_stylesheet

logger = logging.getLogger(__name__)

# 状态颜色
_STATUS_COLORS = {"ok": "#4CAF50", "failed": "#F44336", "skipped": "#9E9E9E"}


class ChainDialog(
    ChainDialogBindingsMixin,
    ChainDialogRiskMixin,
    ChainDialogTestRunnerMixin,
    ChainDialogCloseAnimationMixin,
    BaseDialog,
):
    """动作链编辑对话框 — 左右两栏布局。

    The dialog composes four behaviour mixins
    (:class:`ChainDialogBindingsMixin`, :class:`ChainDialogRiskMixin`,
    :class:`ChainDialogTestRunnerMixin`,
    :class:`ChainDialogCloseAnimationMixin`) so the bulk of the
    feature logic lives outside this file — see the
    ``chain_dialog_*.py`` modules.
    """

    def __init__(self, parent=None, shortcut: ShortcutItem | None = None):
        super().__init__(parent)
        self.shortcut = shortcut or ShortcutItem(type=ShortcutType.CHAIN, name=tr("动作链"))
        self._steps = copy.deepcopy(list(getattr(self.shortcut, "chain_steps", []) or []))
        self._available = self._collect_available_shortcuts()
        self._canvas_data = copy.deepcopy(getattr(self.shortcut, "chain_canvas", {}) or {})
        self._selected_index = -1
        self._binding_loading = False
        self._test_thread = None
        self._last_test_result = None
        self._closing_with_animation = False
        self._pending_done_result = None
        self._close_anim_timer = None
        self._close_anim_generation = 0

        self.setWindowTitle(tr("编辑动作链") if shortcut else tr("新建动作链"))
        self.setMinimumSize(sp(760), sp(620))

        self._setup_ui()
        self._apply_theme()
        self._load_data()
        self._refresh_risk_analysis()

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Wheel:  # type: ignore[unused-ignore, attr-defined]
            # 获取当前活动的 Tab 页面
            active_page = self.module_tabs.currentWidget()
            if active_page:
                scroll_area = active_page.findChild(QScrollArea)
                if scroll_area:
                    hbar = scroll_area.horizontalScrollBar()
                    if hbar and hbar.isEnabled():
                        # 获取滚轮滚动的垂直 delta (大多数鼠标垂直滚动)
                        delta = event.angleDelta().y()
                        if delta == 0:
                            # 兼容某些水平滚动的触控板
                            delta = event.angleDelta().x()

                        # 换算为滚动步长并进行横向滚动
                        num_steps = delta / 120.0
                        # 每次滚动 4 个单步，横向滚动极其顺滑
                        scroll_amount = hbar.singleStep() * 4
                        hbar.setValue(int(hbar.value() - num_steps * scroll_amount))
                        event.accept()
                        return True
        return super().eventFilter(watched, event)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(sp(4))
        root.setContentsMargins(sp(8), sp(8), sp(8), sp(8))

        # 顶部标题
        self.title_label = QLabel(tr("编辑动作链") if self.shortcut.name else tr("新建动作链"))
        self.title_label.setStyleSheet(
            scale_qss(
                "font-size: 12px; font-weight: 400; color: gray; font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;"
            )
        )
        root.addWidget(self.title_label)

        self.module_tabs = self._build_module_bar()
        root.addWidget(self.module_tabs)
        root.addLayout(self._build_quick_add_bar())

        # 安装事件过滤器，使用滚轮在标题栏和标签栏上滚动时进行横向滚动
        self.title_label.installEventFilter(self)
        self.module_tabs.installEventFilter(self)
        if self.module_tabs.tabBar():
            self.module_tabs.tabBar().installEventFilter(self)

        # 节点画布两栏：画布 / 属性与结果
        body = QHBoxLayout()
        body.setSpacing(sp(8))
        body.addLayout(self._build_canvas_panel(), 6)
        body.addLayout(self._build_right_panel(), 2)
        root.addLayout(body, 1)

        from qt_compat import QSizePolicy

        btn_row = QHBoxLayout()
        btn_row.setSpacing(sp(8))

        # 左侧测试运行
        ops_layout = QHBoxLayout()
        ops_layout.setSpacing(sp(4))
        ops_layout.setContentsMargins(0, 0, 0, 0)
        self.test_btn = QPushButton(tr("测试运行"))
        self.test_btn.clicked.connect(self._run_test)
        self.clear_run_btn = QPushButton(tr("清除结果"))
        self.clear_run_btn.clicked.connect(self._clear_run_results)
        for b in (self.test_btn, self.clear_run_btn):
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            ops_layout.addWidget(b, 1)
        btn_row.addLayout(ops_layout, 6)

        # 右侧：取消/保存，stretch 2
        right_btn_layout = QHBoxLayout()
        right_btn_layout.setContentsMargins(0, 0, 0, 0)
        right_btn_layout.addStretch()
        self._cancel_btn = QPushButton(tr("取消"))
        self._cancel_btn.clicked.connect(self.reject)
        self._save_btn = QPushButton(tr("保存"))
        self._save_btn.clicked.connect(self.accept)
        right_btn_layout.addWidget(self._cancel_btn)
        right_btn_layout.addWidget(self._save_btn)
        btn_row.addLayout(right_btn_layout, 2)

        root.addLayout(btn_row)

    def _build_quick_add_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(sp(6))
        row.setContentsMargins(0, 0, 0, 0)
        label = QLabel(tr("搜索添加:"))
        self.quick_add_edit = QLineEdit()
        self.quick_add_edit.setPlaceholderText(tr("输入电池、快捷方式、命令或网址名称"))
        self.quick_add_edit.textChanged.connect(self._refresh_quick_add_hint)
        self.quick_add_edit.returnPressed.connect(self._quick_add_first_match)
        self.quick_add_hint = QLabel("")
        self.quick_add_hint.setMinimumWidth(sp(180))
        self.quick_add_hint.setStyleSheet(scale_qss("color: rgba(128,128,128,180); font-size: 11px;"))
        self.quick_add_btn = QPushButton(tr("添加"))
        self.quick_add_btn.clicked.connect(self._quick_add_first_match)
        row.addWidget(label)
        row.addWidget(self.quick_add_edit, 1)
        row.addWidget(self.quick_add_hint)
        row.addWidget(self.quick_add_btn)
        return row

    def _build_module_bar(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setFixedHeight(sp(138))
        self._module_buttons = []  # type: ignore[var-annotated]

        theme = "dark"
        try:
            parent = self.parent()
            data_manager = getattr(parent, "data_manager", None)
            if data_manager is not None:
                settings = data_manager.get_settings()
                if settings is not None:
                    theme = settings.theme
        except Exception as exc:
            logger.debug("读取动作链对话框主题失败: %s", exc, exc_info=True)

        self.file_btn = QPushButton()
        self.folder_btn = QPushButton()
        self.url_btn = QPushButton()
        self.hotkey_btn = QPushButton()
        self.cmd_btn = QPushButton()
        self.processor_btn = QPushButton()

        # QL图标 Tab（始终排在首位）
        tabs.addTab(self._ql_icons_page(theme), tr("QL图标"))

        # ── 从 processor_definitions() 按 category 自动生成标签页 ──
        from core.chain_processors import processor_definitions as _all_defs

        _CATEGORY_TAB_ORDER = [
            "输入与调试",
            "逻辑",
            "文本",
            "数学与列表",
            "数学扩展",
            "网络与结构化",
            "文件与路径",
            "图像",
            "日期时间",
            "编码解码",
            "数据验证",
            "加密哈希",
            "颜色处理",
            "集合操作",
            "字典操作",
            "字符串格式化",
            "数据压缩",
            "环境变量",
            "系统信息",
            "网络工具",
        ]

        _CATEGORY_TAB_LABEL = {
            "输入与调试": "输入调试",
            "数学与列表": "列表数学",
            "数学扩展": "数学扩展",
            "网络与结构化": "结构化",
            "文件与路径": "文件路径",
            "编码解码": "编码解码",
            "数据验证": "数据验证",
            "加密哈希": "加密哈希",
            "颜色处理": "颜色",
            "集合操作": "集合",
            "字典操作": "字典",
            "字符串格式化": "格式化",
            "数据压缩": "压缩",
            "环境变量": "环境变量",
            "系统信息": "系统",
            "网络工具": "网络",
        }

        by_category: dict[str, list[str]] = {}
        for d in _all_defs():
            by_category.setdefault(d.category, []).append(d.id)

        seen: set[str] = set()
        for cat in _CATEGORY_TAB_ORDER:
            if cat not in by_category:
                continue
            pids = by_category[cat]
            label = _CATEGORY_TAB_LABEL.get(cat, cat)
            if len(pids) <= 12:
                tabs.addTab(
                    self._processor_page(tr(cat), pids, theme),
                    tr(label),
                )
            else:
                tabs.addTab(
                    self._grouped_processor_page(tr(cat), pids, theme),
                    tr(label),
                )
            seen.add(cat)

        for cat in sorted(by_category):
            if cat in seen:
                continue
            pids = by_category[cat]
            label = _CATEGORY_TAB_LABEL.get(cat, cat)
            if len(pids) <= 12:
                tabs.addTab(
                    self._processor_page(tr(cat), pids, theme),
                    tr(label),
                )
            else:
                tabs.addTab(
                    self._grouped_processor_page(tr(cat), pids, theme),
                    tr(label),
                )

        return tabs

    def _ql_icons_page(self, theme: str) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # type: ignore[unused-ignore, attr-defined]
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # type: ignore[unused-ignore, attr-defined]
        scroll.setFrameShape(QFrame.NoFrame)

        bar = QWidget()
        bar.setFixedHeight(sp(102))
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(sp(12), 0, sp(12), 0)
        layout.setSpacing(sp(18))  # 组团之间采用 18px 优雅间距区分，实现另起一列的清晰视效

        # 分组组团数据提取
        urls = [it for it in self._available if it.type == ShortcutType.URL]
        commands = [it for it in self._available if it.type == ShortcutType.COMMAND]
        apps = [
            it for it in self._available if it.type in (ShortcutType.FILE, ShortcutType.FOLDER, ShortcutType.HOTKEY)
        ]

        def create_sep():
            sep = QFrame()
            sep.setFrameShape(QFrame.VLine)
            if theme == "dark":
                sep.setStyleSheet(
                    scale_qss(
                        "QFrame { background-color: rgba(255, 255, 255, 0.08); min-width: 1px; max-width: 1px; margin: 6px 0px; border: none; }"
                    )
                )
            else:
                sep.setStyleSheet(
                    scale_qss(
                        "QFrame { background-color: rgba(0, 0, 0, 0.06); min-width: 1px; max-width: 1px; margin: 6px 0px; border: none; }"
                    )
                )
            return sep

        # 1. 网址组团
        url_group = GrasshopperGroupWidget(tr("网址"), theme)
        for item in urls:
            btn = self._make_module_button(item.name or item.id, lambda _=False, it=item: self._add_step(it))
            url_group.add_button(btn)
        if not urls:
            lbl = QLabel(tr("暂无网址"))
            lbl.setStyleSheet(scale_qss("color: #888; font-size: 10px; padding: 4px;"))
            url_group.grid_layout.addWidget(lbl, 0, 0)
        layout.addWidget(url_group)

        layout.addWidget(create_sep())

        # 2. 命令组团
        cmd_group = GrasshopperGroupWidget(tr("命令"), theme)
        for item in commands:
            btn = self._make_module_button(item.name or item.id, lambda _=False, it=item: self._add_step(it))
            cmd_group.add_button(btn)
        if not commands:
            lbl = QLabel(tr("暂无命令"))
            lbl.setStyleSheet(scale_qss("color: #888; font-size: 10px; padding: 4px;"))
            cmd_group.grid_layout.addWidget(lbl, 0, 0)
        layout.addWidget(cmd_group)

        layout.addWidget(create_sep())

        # 3. 快捷方式组团
        app_group = GrasshopperGroupWidget(tr("快捷方式"), theme)
        for item in apps:
            btn = self._make_module_button(item.name or item.id, lambda _=False, it=item: self._add_step(it))
            app_group.add_button(btn)
        if not apps:
            lbl = QLabel(tr("暂无快捷方式"))
            lbl.setStyleSheet(scale_qss("color: #888; font-size: 10px; padding: 4px;"))
            app_group.grid_layout.addWidget(lbl, 0, 0)
        layout.addWidget(app_group)

        layout.addStretch()
        scroll.setWidget(bar)
        outer.addWidget(scroll)
        return page

    def _processor_page(self, title: str, processor_ids: list[str], theme: str) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # type: ignore[unused-ignore, attr-defined]
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # type: ignore[unused-ignore, attr-defined]
        scroll.setFrameShape(QFrame.NoFrame)

        bar = QWidget()
        bar.setFixedHeight(sp(102))
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(sp(12), 0, sp(12), 0)
        layout.setSpacing(sp(18))  # 组团之间采用 18px 优雅间距区分，实现另起一列的清晰视效

        if not processor_ids:
            # 提示无电池，契合后期补齐的设计
            lbl = QLabel(tr("暂无可添加处理器电池"))
            lbl.setStyleSheet(scale_qss("color: #888; font-size: 11px; padding: 12px; font-style: italic;"))
            layout.addWidget(lbl)
        else:
            group = GrasshopperGroupWidget(title, theme)
            for pid in processor_ids:
                from core.chain_processors import processor_title

                p_title = processor_title(pid)
                btn = self._make_module_button(
                    p_title, lambda _=False, target_pid=pid: self._add_processor_node(target_pid)
                )
                group.add_button(btn)
            layout.addWidget(group)

        layout.addStretch()
        scroll.setWidget(bar)
        outer.addWidget(scroll)
        return page

    def _grouped_processor_page(self, title: str, processor_ids: list[str], theme: str, group_size: int = 8) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # type: ignore[unused-ignore, attr-defined]
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # type: ignore[unused-ignore, attr-defined]
        scroll.setFrameShape(QFrame.NoFrame)

        bar = QWidget()
        bar.setFixedHeight(sp(102))
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(sp(12), 0, sp(12), 0)
        layout.setSpacing(sp(18))

        def create_sep():
            sep = QFrame()
            sep.setFrameShape(QFrame.VLine)
            if theme == "dark":
                sep.setStyleSheet(
                    scale_qss(
                        "QFrame { background-color: rgba(255, 255, 255, 0.08); min-width: 1px; max-width: 1px; margin: 6px 0px; border: none; }"
                    )
                )
            else:
                sep.setStyleSheet(
                    scale_qss(
                        "QFrame { background-color: rgba(0, 0, 0, 0.06); min-width: 1px; max-width: 1px; margin: 6px 0px; border: none; }"
                    )
                )
            return sep

        from core.chain_processors import processor_title

        for i in range(0, len(processor_ids), group_size):
            chunk = processor_ids[i : i + group_size]
            if i > 0:
                layout.addWidget(create_sep())
            group = GrasshopperGroupWidget(title, theme)
            for pid in chunk:
                p_title = processor_title(pid)
                btn = self._make_module_button(
                    p_title, lambda _=False, target_pid=pid: self._add_processor_node(target_pid)
                )
                group.add_button(btn)
            layout.addWidget(group)

        layout.addStretch()
        scroll.setWidget(bar)
        outer.addWidget(scroll)
        return page

    def _make_module_button(self, title: str, callback) -> QPushButton:
        btn = make_module_button(title, callback)
        self._module_buttons.append(btn)
        return btn

    def _build_left_panel(self) -> QVBoxLayout:
        left = QVBoxLayout()
        left.setSpacing(sp(4))

        # 基本设置
        basic = QGroupBox(tr("基本设置"))
        form = QVBoxLayout(basic)
        form.setSpacing(sp(4))
        form.setContentsMargins(sp(8), sp(4), sp(8), sp(6))

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(tr("名称:")))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("动作链名称"))
        name_row.addWidget(self.name_edit, 1)
        form.addLayout(name_row)

        result_row = QHBoxLayout()
        result_row.addWidget(QLabel(tr("结果显示:")))
        self._result_checks: dict[str, QCheckBox] = {}
        for key in ("none", "small", "medium", "large"):
            label_map = {"none": tr("无"), "small": tr("小"), "medium": tr("中"), "large": tr("大")}
            cb = QCheckBox(label_map[key])
            cb.setStyleSheet(scale_qss("QCheckBox { font-size: 12px; spacing: 3px; }"))
            cb.toggled.connect(lambda checked, k=key: self._on_result_check(k, checked))
            result_row.addWidget(cb)
            self._result_checks[key] = cb
        self._result_checks["medium"].setChecked(True)  # 默认 medium
        result_row.addStretch()
        form.addLayout(result_row)

        left.addWidget(basic)

        # 图标设置
        self._custom_icon_path = getattr(self.shortcut, "icon_path", "") or ""
        icon_group = QGroupBox(tr("图标"))
        icon_layout = QHBoxLayout(icon_group)
        icon_layout.setSpacing(sp(6))
        icon_layout.setContentsMargins(sp(6), 0, sp(6), sp(6))

        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(sp(32), sp(32))
        self.icon_preview.setAlignment(QtCompat.AlignCenter)
        self.icon_preview.setStyleSheet(
            scale_qss(
                "QLabel { background-color: rgba(255, 255, 255, 0.1); "
                "border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; }"
            )
        )
        icon_layout.addWidget(self.icon_preview)

        icon_right_layout = QVBoxLayout()
        icon_right_layout.setSpacing(sp(6))

        self.icon_edit = QLineEdit()
        self.icon_edit.setPlaceholderText(tr("留空则使用默认图标"))
        self.icon_edit.setReadOnly(True)
        icon_right_layout.addWidget(self.icon_edit)

        icon_btn_layout = QHBoxLayout()
        icon_btn_layout.setSpacing(sp(8))

        browse_icon_btn = QPushButton(tr("选择图标..."))
        browse_icon_btn.clicked.connect(self._browse_icon)
        icon_btn_layout.addWidget(browse_icon_btn)
        self._browse_icon_btn = browse_icon_btn

        clear_icon_btn = QPushButton(tr("清除"))
        clear_icon_btn.clicked.connect(self._clear_icon)
        icon_btn_layout.addWidget(clear_icon_btn)
        self._clear_icon_btn = clear_icon_btn

        icon_btn_layout.addStretch()

        # 图标反转选项（并排排列）
        self.invert_light_cb = QCheckBox(tr("浅色反转"))
        self.invert_dark_cb = QCheckBox(tr("深色反转"))
        icon_btn_layout.addWidget(self.invert_light_cb)
        icon_btn_layout.addWidget(self.invert_dark_cb)

        icon_right_layout.addLayout(icon_btn_layout)
        icon_layout.addLayout(icon_right_layout, 1)

        left.addWidget(icon_group)

        # 节点库
        library_group = QGroupBox(tr("节点库"))
        library_layout = QVBoxLayout(library_group)
        library_layout.setContentsMargins(sp(6), sp(4), sp(6), sp(6))
        type_row = QHBoxLayout()
        self.file_btn = QPushButton(tr("应用"))
        self.file_btn.clicked.connect(lambda: self._show_type_menu(ShortcutType.FILE))
        self.cmd_btn = QPushButton(tr("命令"))
        self.cmd_btn.clicked.connect(lambda: self._show_type_menu(ShortcutType.COMMAND))
        self.hotkey_btn = QPushButton(tr("热键"))
        self.hotkey_btn.clicked.connect(lambda: self._show_type_menu(ShortcutType.HOTKEY))
        self.url_btn = QPushButton(tr("网址"))
        self.url_btn.clicked.connect(lambda: self._show_type_menu(ShortcutType.URL))
        for btn in (self.file_btn, self.cmd_btn, self.hotkey_btn, self.url_btn):
            type_row.addWidget(btn)
        library_layout.addLayout(type_row)

        self.processor_list = QListWidget()
        for processor_id, title in processor_library_items():
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, processor_id)  # type: ignore[unused-ignore, attr-defined]
            self.processor_list.addItem(item)
        self.processor_list.itemDoubleClicked.connect(self._add_processor_from_item)
        library_layout.addWidget(QLabel(tr("处理节点")))
        library_layout.addWidget(self.processor_list, 1)
        add_processor_btn = QPushButton(tr("添加处理节点"))
        add_processor_btn.clicked.connect(self._add_selected_processor)
        library_layout.addWidget(add_processor_btn)
        self.processor_btn = add_processor_btn

        left.addWidget(library_group, 1)

        return left

    def _build_canvas_panel(self) -> QVBoxLayout:
        center = QVBoxLayout()
        center.setSpacing(sp(4))
        canvas_group = QGroupBox(tr("节点画布"))
        canvas_layout = QVBoxLayout(canvas_group)
        canvas_layout.setContentsMargins(sp(4), sp(4), sp(4), sp(4))
        self.canvas_widget = ChainCanvasWidget(self._shortcut_map(), self)
        self.canvas_widget.canvas_changed.connect(self._on_canvas_changed)
        self.canvas_widget.selection_changed.connect(self._on_canvas_selection_changed)
        canvas_layout.addWidget(self.canvas_widget)
        center.addWidget(canvas_group, 1)
        return center

    def _build_right_panel(self) -> QVBoxLayout:
        right = QVBoxLayout()
        right.setSpacing(sp(4))

        self.property_tabs = QTabWidget()
        self.property_panel = NodePropertyPanel(self)
        self.property_panel.args_changed.connect(self._on_property_args_changed)
        self.property_panel.disconnect_requested.connect(self._on_disconnect_requested)
        self.property_panel.delete_requested.connect(self._remove_step)
        self.property_panel.edit_source_requested.connect(self._edit_selected_node_source)
        self.property_tabs.addTab(self.property_panel, tr("节点属性"))
        self.property_tabs.addTab(self._build_chain_property_panel(), tr("动作链属性"))
        right.addWidget(self.property_tabs, 1)

        result_group = QGroupBox(tr("执行结果"))
        result_layout = QVBoxLayout(result_group)
        result_layout.setContentsMargins(sp(6), sp(4), sp(6), sp(6))

        self.result_view = QPlainTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setFrameShape(QFrame.NoFrame)
        result_layout.addWidget(self.result_view)

        right.addWidget(result_group)
        return right

    def _build_chain_property_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(sp(6), sp(6), sp(6), sp(6))
        layout.setSpacing(sp(6))

        basic = QGroupBox(tr("基本设置"))
        form = QVBoxLayout(basic)
        form.setSpacing(sp(4))
        form.setContentsMargins(sp(8), sp(4), sp(8), sp(6))

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(tr("名称:")))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("动作链名称"))
        name_row.addWidget(self.name_edit, 1)
        form.addLayout(name_row)

        result_row = QHBoxLayout()
        result_row.addWidget(QLabel(tr("结果显示:")))
        self._result_checks: dict[str, QCheckBox] = {}  # type: ignore[no-redef]
        for key in ("none", "small", "medium", "large"):
            label_map = {"none": tr("无"), "small": tr("小"), "medium": tr("中"), "large": tr("大")}
            cb = QCheckBox(label_map[key])
            cb.toggled.connect(lambda checked, k=key: self._on_result_check(k, checked))
            result_row.addWidget(cb)
            self._result_checks[key] = cb
        self._result_checks["medium"].setChecked(True)
        result_row.addStretch()
        form.addLayout(result_row)
        layout.addWidget(basic)

        self._custom_icon_path = getattr(self.shortcut, "icon_path", "") or ""
        icon_group = QGroupBox(tr("图标"))
        icon_layout = QVBoxLayout(icon_group)
        icon_layout.setSpacing(sp(6))
        icon_layout.setContentsMargins(sp(6), sp(4), sp(6), sp(6))

        preview_row = QHBoxLayout()
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(sp(32), sp(32))
        self.icon_preview.setAlignment(QtCompat.AlignCenter)
        self.icon_preview.setStyleSheet(
            scale_qss(
                "QLabel { background-color: rgba(255, 255, 255, 0.1); "
                "border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; }"
            )
        )
        preview_row.addWidget(self.icon_preview)
        self.icon_edit = QLineEdit()
        self.icon_edit.setPlaceholderText(tr("留空则使用默认图标"))
        self.icon_edit.setReadOnly(True)
        preview_row.addWidget(self.icon_edit, 1)
        icon_layout.addLayout(preview_row)

        icon_btn_layout = QHBoxLayout()
        self._browse_icon_btn = QPushButton(tr("选择图标..."))
        self._browse_icon_btn.clicked.connect(self._browse_icon)
        self._clear_icon_btn = QPushButton(tr("清除"))
        self._clear_icon_btn.clicked.connect(self._clear_icon)
        icon_btn_layout.addWidget(self._browse_icon_btn)
        icon_btn_layout.addWidget(self._clear_icon_btn)
        icon_layout.addLayout(icon_btn_layout)

        invert_row = QHBoxLayout()
        invert_row.setContentsMargins(0, 0, 0, 0)
        self.invert_light_cb = QCheckBox(tr("浅色反转"))
        self.invert_dark_cb = QCheckBox(tr("深色反转"))
        invert_row.addWidget(self.invert_light_cb)
        invert_row.addWidget(self.invert_dark_cb)
        invert_row.addStretch()
        icon_layout.addLayout(invert_row)
        layout.addWidget(icon_group)

        layout.addStretch()
        return panel

    # ── 主题 ────────────────────────────────────────────────

    def _apply_theme(self):
        self._apply_theme_colors()
        theme = self.theme

        base_style = Glassmorphism.get_full_glassmorphism_stylesheet(theme)
        border_color = "rgba(255, 255, 255, 0.06)" if theme == "dark" else "rgba(0, 0, 0, 0.04)"
        title_color = "rgba(255, 255, 255, 0.6)" if theme == "dark" else "rgba(0, 0, 0, 0.5)"
        text_primary = "#FFFFFF" if theme == "dark" else "#1C1C1E"
        input_bg = "rgba(255, 255, 255, 0.08)" if theme == "dark" else "rgba(255, 255, 255, 0.8)"
        tip_bg = "rgba(44, 44, 48, 240)" if theme == "dark" else "rgba(255, 255, 255, 240)"
        tip_fg = "#ffffff" if theme == "dark" else "#1c1c1e"
        tip_border = "rgba(255, 255, 255, 0.15)" if theme == "dark" else "rgba(0, 0, 0, 0.1)"
        selection_bg = Colors.get_selection_bg(theme)
        selection_text = Colors.get_selection_text(theme)

        custom = base_style + scale_qss(
            f"""
            QDialog {{ background: transparent; border: none; }}
            QLabel, QCheckBox, QGroupBox, QLineEdit, QSpinBox, QPushButton, QTabWidget {{
                font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
                font-weight: 400;
            }}
            QToolTip {{
                background: {tip_bg};
                color: {tip_fg};
                border: 1px solid {tip_border};
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 400;
            }}
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
            QLineEdit {{
                background-color: {input_bg};
                border: 1px solid {border_color};
                border-radius: 10px;
                color: {text_primary};
                font-size: 13px;
                padding: 4px 8px;
                selection-background-color: {selection_bg};
                selection-color: {selection_text};
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QSpinBox {{
                background-color: {input_bg};
                border: 1px solid {border_color};
                border-radius: 6px;
                color: {text_primary};
                font-size: 12px;
                padding: 2px 4px;
            }}
            QTabWidget::pane {{
                border: 1px solid {border_color};
                border-radius: 6px;
                top: -1px;
            }}
            QTabBar::tab {{
                color: {text_primary};
                padding: 5px 10px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }}
            QTabBar::tab:selected {{
                background-color: {input_bg};
            }}
        """
        )
        self._tip_stylesheet = scale_qss(
            f"QToolTip {{ background: {tip_bg}; color: {tip_fg}; border: 1px solid {tip_border}; border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 400; }}"
        )
        self.setStyleSheet(custom)

        # 按钮复用扁平操作按钮样式
        refined_button_font = scale_qss(
            """
            QPushButton {
                font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
                font-size: 12px;
                font-weight: 400;
                min-height: 22px;
            }
        """
        )
        flat_btn_style = Glassmorphism.get_flat_action_button_style(theme) + refined_button_font
        for btn in (
            self.file_btn,
            self.folder_btn,
            self.cmd_btn,
            self.hotkey_btn,
            self.url_btn,
            self.processor_btn,
            self.test_btn,
            self.clear_run_btn,
            self.quick_add_btn,
            self._browse_icon_btn,
            self._clear_icon_btn,
            self._cancel_btn,
            self._save_btn,
        ):
            btn.setStyleSheet(flat_btn_style)

        # 菜单栏按钮使用更小且更精致的文字大小以防文本截断，契合 Grasshopper 风格
        module_button_font = scale_qss(
            """
            QPushButton {
                font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
                font-size: 10px;
                font-weight: 400;
                min-height: 18px;
                padding: 1px 2px;
                margin: 0px;
            }
        """
        )
        module_btn_style = Glassmorphism.get_flat_action_button_style(theme) + module_button_font
        for btn in getattr(self, "_module_buttons", []):
            btn.setStyleSheet(module_btn_style)
            btn.raise_()  # 确保文字和按钮图层始终处于最前方，防止被其他容器或背景遮挡
        # 测试按钮用强调色
        # 所有复选框统一使用 get_small_checkbox_stylesheet
        cb_style = get_small_checkbox_stylesheet(theme)
        for cb in self._result_checks.values():
            cb.setStyleSheet(cb_style)
        self.invert_light_cb.setStyleSheet(get_compact_checkbox_stylesheet(theme))
        self.invert_dark_cb.setStyleSheet(get_compact_checkbox_stylesheet(theme))

        # result_view 透明背景，文字直接显示在分栏框里
        self.result_view.setStyleSheet(
            scale_qss(
                f"QPlainTextEdit {{ background: transparent; border: none; "
                f"color: {text_primary}; font-size: 12px; padding: 8px; "
                f"font-family: 'Cascadia Code', 'Consolas', monospace; }}"
            )
        )
        # viewport 必须用 palette 强制上色，否则 BaseDialog 透明背景会让点击时闪白
        from qt_compat import QPalette

        vp = self.result_view.viewport()
        pal = self.result_view.palette()
        bg_color = QColor(28, 28, 30) if theme == "dark" else QColor(242, 242, 247)
        bg_color.setAlpha(120)
        pal.setColor(QPalette.Base, bg_color)
        self.result_view.setPalette(pal)
        vp.setAutoFillBackground(True)

    # ── 数据加载 ─────────────────────────────────────────────

    def _on_result_check(self, key: str, checked: bool):
        """互斥复选：选中一个时取消其他。"""
        if not checked:
            # 防止全部取消，至少保留一个
            if not any(cb.isChecked() for cb in self._result_checks.values()):
                self._result_checks[key].setChecked(True)
            return
        for k, cb in self._result_checks.items():
            if k != key:
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)

    def _get_result_window_value(self) -> str:
        for key, cb in self._result_checks.items():
            if cb.isChecked():
                return key
        return "medium"

    def _load_data(self):
        self.name_edit.setText(self.shortcut.name or tr("动作链"))
        crw = getattr(self.shortcut, "chain_result_window", "medium")
        if crw in self._result_checks:
            self._result_checks[crw].setChecked(True)
        # 图标
        self._custom_icon_path = getattr(self.shortcut, "icon_path", "") or ""
        if self._custom_icon_path:
            self.icon_edit.setText(self._custom_icon_path)
        self.invert_light_cb.setChecked(getattr(self.shortcut, "icon_invert_light", False))
        self.invert_dark_cb.setChecked(getattr(self.shortcut, "icon_invert_dark", False))
        self._update_icon_preview()
        canvas = copy.deepcopy(getattr(self.shortcut, "chain_canvas", {}) or {})
        if not canvas:
            canvas = canvas_from_steps(self._steps, self._shortcut_map())
        self.canvas_widget.set_canvas(canvas)
        self._sync_steps_from_canvas()
        self._refresh_properties()

    # ── 图标操作 ─────────────────────────────────────────────

    def _browse_icon(self):
        file_path = choose_custom_icon(self, tr("选择图标"))
        if file_path:
            self._custom_icon_path = file_path
            self.icon_edit.setText(file_path)
            self._update_icon_preview()

    def _clear_icon(self):
        self._custom_icon_path = ""
        self.icon_edit.clear()
        self._update_icon_preview()

    def _update_icon_preview(self):
        pixmap = None
        if self._custom_icon_path:
            try:
                from core.icon_extractor import IconExtractor

                if "," in self._custom_icon_path or os.path.exists(self._custom_icon_path):
                    pixmap = IconExtractor.from_file(self._custom_icon_path, 48)
            except Exception as exc:
                logger.debug("加载自定义图标失败: %s", exc, exc_info=True)
        if not pixmap or pixmap.isNull():
            pixmap = self._create_chain_icon(48)
        _current_theme = getattr(self, "theme", "dark")
        _need_invert = (
            self.invert_light_cb.isChecked() if _current_theme == "light" else self.invert_dark_cb.isChecked()
        )
        if _need_invert and pixmap and not pixmap.isNull():
            try:
                from core.icon_extractor import IconExtractor

                pixmap = IconExtractor.invert_pixmap(pixmap)
            except Exception as exc:
                logger.debug("反转图标失败: %s", exc, exc_info=True)
        if pixmap and not pixmap.isNull():
            pixmap = pixmap.scaled(sp(32), sp(32), QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
        self.icon_preview.setPixmap(pixmap)

    def _create_chain_icon(self, size: int) -> QPixmap:
        pixmap = QPixmap(size, size)
        pixmap.fill(QtCompat.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QtCompat.Antialiasing)
        painter.setRenderHint(QtCompat.HighQualityAntialiasing)
        painter.setBrush(QColor(180, 100, 50))
        painter.setPen(QtCompat.NoPen)
        margin = size // 8
        painter.drawRoundedRect(QRectF(margin, margin, size - margin * 2, size - margin * 2), 6, 6)
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI Symbol", size // 3)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCompat.AlignCenter, "⛓")  # ⚓ chain symbol
        painter.end()
        return pixmap

    def _collect_available_shortcuts(self) -> list[ShortcutItem]:
        parent = self.parent()
        data_manager = getattr(parent, "data_manager", None)
        data = getattr(data_manager, "data", None)
        result = []
        for folder in list(getattr(data, "folders", []) or []):
            for item in list(getattr(folder, "items", []) or []):
                if item.id == self.shortcut.id or item.type in (ShortcutType.CHAIN, ShortcutType.BATCH_LAUNCH):
                    continue
                result.append(item)
        return result

    def _shortcut_map(self) -> dict[str, ShortcutItem]:
        return {item.id: item for item in self._available}

    # ── 图标加载 ─────────────────────────────────────────────

    def _load_step_icon(self, shortcut: ShortcutItem | None) -> QPixmap | None:
        """加载快捷方式的图标，返回 QPixmap；无图标返回 None。"""
        if shortcut is None:
            return None
        icon_path = getattr(shortcut, "icon_path", "") or ""
        target_path = getattr(shortcut, "target_path", "") or ""
        try:
            import os

            from core.icon_extractor import IconExtractor

            source_size = 64
            if icon_path:
                if "," in icon_path or os.path.exists(icon_path):
                    pm = IconExtractor.from_file(icon_path, source_size, return_image=False)
                    if pm and not pm.isNull():
                        return pm  # type: ignore[unused-ignore, no-any-return]
            # 文件夹类型默认图标
            if not icon_path and shortcut_uses_folder_icon(shortcut.type, target_path):
                folder_ico = default_folder_icon_path()
                if folder_ico:
                    pm = IconExtractor.from_file(folder_ico, source_size, return_image=False)
                    if pm and not pm.isNull():
                        return pm  # type: ignore[unused-ignore, no-any-return]
            if target_path:
                if os.path.exists(target_path):
                    pm = IconExtractor.extract(target_path, target_path, source_size, return_image=False)
                    if pm and not pm.isNull():
                        return pm  # type: ignore[unused-ignore, no-any-return]
        except Exception as exc:
            logger.debug("获取快捷方式图标失败: %s", exc, exc_info=True)
        return None

    # ── 卡片刷新 ─────────────────────────────────────────────

    def _refresh_cards(self):
        if hasattr(self, "canvas_widget"):
            self._sync_steps_from_canvas()
            self._refresh_properties()
            return
        # 清除旧卡片（保留 stretch）
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        smap = self._shortcut_map()
        cb_style = next((cb.styleSheet() for cb in self._result_checks.values() if cb.styleSheet()), "")
        for i, step in enumerate(self._steps):
            sid = step.get("shortcut_id", "")
            target = smap.get(sid)
            name = getattr(target, "name", sid) if target else sid
            stype = getattr(target, "type", ShortcutType.FILE) if target else ShortcutType.FILE
            icon = self._load_step_icon(target)
            card = StepCardWidget(i, step, name, stype, icon, parent=self._cards_container)
            card.clicked.connect(self._on_card_clicked)
            card.step_changed.connect(self._on_step_changed)
            # 应用复选框样式（与其他复选框一致）
            card.set_checkbox_style(cb_style)
            # 插入到 stretch 之前
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

        # 选中状态
        self._update_selection()
        self._load_selected_binding_fields()

    def _on_step_changed(self, index: int):
        """卡片内联控件变更 → 同步到 _steps 数据。"""
        if not (0 <= index < len(self._steps)):
            return
        # 找到对应卡片
        card = self._find_card(index)
        if card is None:
            return
        self._steps[index]["delay_ms"] = card._delay_spin.value()
        self._steps[index]["stop_on_error"] = card._stop_cb.isChecked()
        self._steps[index]["enabled"] = card._enabled_cb.isChecked()
        self._refresh_risk_analysis()

    def _find_card(self, index: int) -> StepCardWidget | None:
        if not hasattr(self, "_cards_layout"):
            return None
        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, StepCardWidget) and w.step_index == index:
                return w
        return None

    def _update_selection(self):
        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, StepCardWidget):
                w.set_selected(w.step_index == self._selected_index)

    def _on_card_clicked(self, index: int):
        self._selected_index = index
        self._update_selection()
        self._load_selected_binding_fields()

    def _on_canvas_changed(self):
        self._sync_steps_from_canvas()
        self._refresh_risk_analysis()
        self._refresh_properties()

    def _on_canvas_selection_changed(self, node_id: str):
        nodes = sorted(self.canvas_widget.get_canvas().get("nodes", []), key=lambda n: int(n.get("order", 0) or 0))
        self._selected_index = next((i for i, node in enumerate(nodes) if str(node.get("id") or "") == node_id), -1)
        self._refresh_properties()

    def _sync_steps_from_canvas(self):
        if hasattr(self, "canvas_widget"):
            self._steps = self.canvas_widget.compile_steps()

    def _refresh_properties(self):
        if not hasattr(self, "property_panel") or not hasattr(self, "canvas_widget"):
            return
        node = self.canvas_widget.selected_node()
        if node is None:
            self.property_panel.load_node(None, [], {})
            return
        input_ports = self.canvas_widget.input_ports_for_node(node)
        node_id = str(node.get("id") or "")
        connections = {}
        for port in input_ports:
            port_connections = self.canvas_widget.incoming_connections(node_id, port)
            if port_connections:
                connections[port] = "\n".join(
                    self.canvas_widget.connection_source_label(connection) for connection in port_connections
                )
        self.property_panel.load_node(node, input_ports, connections)

    def _on_property_args_changed(self, args: dict):
        self.canvas_widget.update_selected_args(args)
        self._sync_steps_from_canvas()
        self._refresh_risk_analysis()

    def _on_disconnect_requested(self, node_id: str, port_id: str):
        self.canvas_widget.disconnect_input(node_id, port_id)
        self._sync_steps_from_canvas()
        self._refresh_properties()
        self._refresh_risk_analysis()

    def _edit_selected_node_source(self):
        self.canvas_widget.edit_selected_source()
        self._sync_steps_from_canvas()
        self._refresh_properties()
        self._refresh_risk_analysis()

    # ── 步骤操作 ─────────────────────────────────────────────

    def _show_type_menu(self, stype: ShortcutType):
        """显示指定类型的快捷方式菜单。"""
        filtered = [it for it in self._available if it.type == stype]
        if not filtered:
            return
        menu = PopupMenu(theme=getattr(self, "theme", "dark"), parent=self)
        for item in filtered:
            menu.add_action(item.name or item.id, lambda it=item: self._add_step(it))
        # 定位到对应按钮下方
        btn_map = {
            ShortcutType.FILE: self.file_btn,
            ShortcutType.COMMAND: self.cmd_btn,
            ShortcutType.HOTKEY: self.hotkey_btn,
            ShortcutType.URL: self.url_btn,
        }
        btn = btn_map.get(stype, self.file_btn)
        menu.popup(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _quick_add_candidates(self) -> list[dict]:
        candidates = []
        try:
            from core.chain_processors import processor_definitions

            for definition in processor_definitions():
                candidates.append(
                    {
                        "kind": "processor",
                        "id": definition.id,
                        "title": definition.title,
                        "subtitle": definition.category,
                        "search": " ".join(
                            [
                                definition.id,
                                definition.title,
                                definition.category,
                                definition.description,
                            ]
                        ).lower(),
                    }
                )
        except Exception:
            logger.debug("加载动作链电池搜索候选失败", exc_info=True)
        for item in self._available:
            type_label = getattr(getattr(item, "type", ""), "value", str(getattr(item, "type", "")))
            candidates.append(
                {
                    "kind": "shortcut",
                    "id": getattr(item, "id", ""),
                    "title": getattr(item, "name", "") or getattr(item, "id", ""),
                    "subtitle": type_label,
                    "item": item,  # type: ignore[dict-item]
                    "search": " ".join(
                        [
                            str(getattr(item, "id", "")),
                            str(getattr(item, "name", "")),
                            str(getattr(item, "alias", "")),
                            str(type_label),
                        ]
                    ).lower(),
                }
            )
        return candidates

    def _quick_add_matches(self, query: str) -> list[dict]:
        query = str(query or "").strip().lower()
        if not query:
            return []
        tokens = [part for part in query.split() if part]
        matches = []
        for candidate in self._quick_add_candidates():
            haystack = str(candidate.get("search") or "")
            title = str(candidate.get("title") or "").lower()
            item_id = str(candidate.get("id") or "").lower()
            if all(token in haystack for token in tokens):
                score = 20
                if title.startswith(query):
                    score += 30
                if item_id.startswith(query):
                    score += 20
                if candidate.get("kind") == "processor":
                    score += 5
                matches.append((score, candidate))
        matches.sort(key=lambda pair: (-pair[0], str(pair[1].get("title") or "")))
        return [candidate for _, candidate in matches]

    def _refresh_quick_add_hint(self):
        matches = self._quick_add_matches(self.quick_add_edit.text())
        if not matches:
            self.quick_add_hint.setText(tr("无匹配"))
            self.quick_add_btn.setEnabled(False)
            return
        first = matches[0]
        label = tr("电池") if first.get("kind") == "processor" else tr("快捷方式")
        self.quick_add_hint.setText(f"{label}: {first.get('title', '')}")
        self.quick_add_btn.setEnabled(True)

    def _quick_add_first_match(self):
        matches = self._quick_add_matches(self.quick_add_edit.text())
        if not matches:
            return
        first = matches[0]
        if first.get("kind") == "processor":
            self._add_processor_node(str(first.get("id") or ""))
        else:
            item = first.get("item")
            if isinstance(item, ShortcutItem):
                self._add_step(item)
        self.quick_add_edit.clear()
        self.quick_add_hint.setText("")

    def _add_step(self, target: ShortcutItem):
        self.canvas_widget.add_shortcut_node(target)
        self._sync_steps_from_canvas()
        self._selected_index = len(self._steps) - 1
        self._refresh_risk_analysis()

    def _add_processor_node(self, processor_id: str):
        if processor_id:
            self.canvas_widget.add_processor_node(processor_id)
            self._sync_steps_from_canvas()
            self._refresh_risk_analysis()

    def _add_selected_processor(self):
        self._add_processor_node("text_template")

    def _remove_step(self):
        self.canvas_widget.remove_selected_node()
        self._sync_steps_from_canvas()
        self._selected_index = min(self._selected_index, len(self._steps) - 1)
        self._refresh_risk_analysis()
        self._refresh_properties()

    def _move_step(self, delta: int):
        canvas = self.canvas_widget.get_canvas()
        nodes = sorted(canvas.get("nodes", []), key=lambda n: int(n.get("order", 0) or 0))
        new_idx = self._selected_index + delta
        if not (0 <= self._selected_index < len(nodes) and 0 <= new_idx < len(nodes)):
            return
        nodes[self._selected_index], nodes[new_idx] = nodes[new_idx], nodes[self._selected_index]
        for index, node in enumerate(nodes, start=1):
            node["order"] = index
            node["x"] = float((index - 1) * sp(220))
        self._selected_index = new_idx
        canvas["nodes"] = nodes
        self.canvas_widget.set_canvas(canvas)
        self._sync_steps_from_canvas()
        self._refresh_risk_analysis()

    def _show_step_context_menu(self, index: int, global_pos):
        if not (0 <= index < len(self._steps)):
            return
        step = self._steps[index]
        menu = PopupMenu(theme=getattr(self, "theme", "dark"), parent=self)
        enabled = step.get("enabled", True)
        menu.add_action(tr("禁用") if enabled else tr("启用"), lambda: self._toggle_step_enabled(index))
        menu.add_separator()
        menu.add_action(tr("上移"), lambda: self._move_step_at(index, -1), enabled=index > 0)
        menu.add_action(tr("下移"), lambda: self._move_step_at(index, 1), enabled=index < len(self._steps) - 1)
        menu.add_separator()
        menu.add_action(tr("删除"), lambda: self._delete_step_at(index))
        menu.popup(global_pos)

    def _toggle_step_enabled(self, index: int):
        if 0 <= index < len(self._steps):
            self._steps[index]["enabled"] = not self._steps[index].get("enabled", True)
            self._refresh_cards()

    def _move_step_at(self, index: int, delta: int):
        self._selected_index = index
        self._move_step(delta)

    def _delete_step_at(self, index: int):
        self._selected_index = index
        self._remove_step()

    def get_shortcut(self) -> ShortcutItem:
        shortcut = copy.deepcopy(self.shortcut)
        shortcut.type = ShortcutType.CHAIN
        shortcut.name = self.name_edit.text().strip() or tr("动作链")
        if hasattr(self, "canvas_widget"):
            canvas = self.canvas_widget.get_canvas()
            if not canvas.get("nodes") and self._steps:
                shortcut.chain_steps = ShortcutItem._normalize_chain_steps(copy.deepcopy(self._steps))
                shortcut.chain_canvas = ShortcutItem._chain_canvas_from_steps(shortcut.chain_steps)
            else:
                self._apply_step_overrides_to_canvas(canvas)
                self.canvas_widget.set_canvas(canvas)
                shortcut.chain_canvas = self.canvas_widget.get_canvas()
                shortcut.chain_steps = ShortcutItem._normalize_chain_steps(self.canvas_widget.compile_steps())
        else:
            shortcut.chain_steps = ShortcutItem._normalize_chain_steps(copy.deepcopy(self._steps))
            shortcut.chain_canvas = ShortcutItem._chain_canvas_from_steps(shortcut.chain_steps)
        shortcut.chain_result_window = self._get_result_window_value()
        shortcut.icon_path = self._custom_icon_path
        shortcut.icon_invert_light = self.invert_light_cb.isChecked()
        shortcut.icon_invert_dark = self.invert_dark_cb.isChecked()
        return shortcut

    def _apply_step_overrides_to_canvas(self, canvas: dict):
        """Keep old tests and direct internal mutations coherent with the canvas."""
        nodes = sorted(canvas.get("nodes", []), key=lambda n: int(n.get("order", 0) or 0))
        if len(nodes) != len(self._steps):
            return
        for node, step in zip(nodes, self._steps, strict=False):
            if str(node.get("node_type") or "shortcut") != str(step.get("node_type") or "shortcut"):
                continue
            if node.get("shortcut_id") and node.get("shortcut_id") != step.get("shortcut_id"):
                continue
            node["enabled"] = bool(step.get("enabled", node.get("enabled", True)))
            node["stop_on_error"] = bool(step.get("stop_on_error", node.get("stop_on_error", True)))
            node["delay_ms"] = int(step.get("delay_ms", node.get("delay_ms", 0)) or 0)
