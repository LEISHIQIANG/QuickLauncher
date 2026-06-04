"""Popup settings page builder and event handlers."""

import logging

from core import DEFAULT_SPECIAL_APPS
from core.i18n import tr
from core.trigger_conflict_checker import check_trigger_conflict
from qt_compat import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QSlider,
    QtCompat,
    QVBoxLayout,
    QWidget,
)
from ui.config_window.input_trigger_recorder import InputTriggerRecorderWidget
from ui.config_window.settings_helpers import NumberedListDelegate
from ui.tooltip_helper import install_tooltip

logger = logging.getLogger(__name__)


class SettingsPopupPageMixin:
    def _setup_popup_page(self, page):
        # 弹窗位置
        layout, group = page.add_group("弹窗位置")
        self.pos_group = QButtonGroup(self)

        # 选项：鼠标-弹窗中心，鼠标-弹窗左上角
        self.pos_mouse_center = QRadioButton(tr("鼠标-弹窗中心"))
        self.pos_mouse_tl = QRadioButton(tr("鼠标-弹窗左上角"))

        self.pos_group.addButton(self.pos_mouse_center, 0)
        self.pos_group.addButton(self.pos_mouse_tl, 1)

        self.pos_group.buttonClicked.connect(self._on_popup_pos_changed)

        # 第一行
        row1 = QHBoxLayout()
        row1.addWidget(self.pos_mouse_center)
        row1.addWidget(self.pos_mouse_tl)
        row1.addStretch()

        v_pos = QVBoxLayout()
        v_pos.addLayout(row1)

        layout.addLayout(v_pos)

        # 自动关闭弹窗选项
        auto_close_row = QHBoxLayout()
        auto_close_row.addWidget(self._create_label("自动关闭"))
        self.auto_close_group = QButtonGroup(self)
        self.auto_close_yes = QRadioButton(tr("是"))
        self.auto_close_no = QRadioButton(tr("否"))
        install_tooltip(self.auto_close_yes, tr("鼠标移出窗口后延迟自动关闭"))
        install_tooltip(self.auto_close_no, tr("需要点击窗口内图标或窗口外其他地方才会关闭"))
        self.auto_close_group.addButton(self.auto_close_yes, 0)
        self.auto_close_group.addButton(self.auto_close_no, 1)
        self.auto_close_group.buttonClicked.connect(self._on_auto_close_changed)
        auto_close_row.addWidget(self.auto_close_yes)
        auto_close_row.addWidget(self.auto_close_no)
        auto_close_row.addSpacing(22)
        auto_close_row.addWidget(self._create_label("固定时多开"))
        self.multi_open_pinned_group = QButtonGroup(self)
        self.multi_open_pinned_yes = QRadioButton(tr("是"))
        self.multi_open_pinned_no = QRadioButton(tr("否"))
        install_tooltip(self.multi_open_pinned_yes, tr("窗口固定时，再次中键保留当前窗口并新开一个弹窗"))
        install_tooltip(self.multi_open_pinned_no, tr("窗口固定时，再次中键仍隐藏当前弹窗"))
        self.multi_open_pinned_group.addButton(self.multi_open_pinned_yes, 0)
        self.multi_open_pinned_group.addButton(self.multi_open_pinned_no, 1)
        self.multi_open_pinned_group.buttonClicked.connect(self._on_multi_open_pinned_changed)
        auto_close_row.addWidget(self.multi_open_pinned_yes)
        auto_close_row.addWidget(self.multi_open_pinned_no)
        auto_close_row.addStretch()
        layout.addLayout(auto_close_row)

        # 消失延迟 (仅在自动关闭开启时可用)
        self.delay_widget = QWidget()
        delay_row = QHBoxLayout(self.delay_widget)
        delay_row.setContentsMargins(0, 0, 0, 0)
        delay_row.addWidget(self._create_label("消失延迟"))
        self.delay_slider = QSlider(QtCompat.Horizontal)
        self.delay_slider.setRange(0, 2000)  # 0-2秒
        self.delay_slider.setSingleStep(50)
        self.delay_slider.valueChanged.connect(self._on_delay_changed)
        delay_row.addWidget(self.delay_slider)
        self.delay_label = QLabel("200ms")
        delay_row.addWidget(self.delay_label)
        layout.addWidget(self.delay_widget)

        # 双击间隔
        double_click_widget = QWidget()
        double_click_row = QHBoxLayout(double_click_widget)
        double_click_row.setContentsMargins(0, 0, 0, 0)
        double_click_row.addWidget(self._create_label("双击间隔"))
        self.double_click_slider = QSlider(QtCompat.Horizontal)
        self.double_click_slider.setRange(100, 500)  # 100-500ms
        self.double_click_slider.setSingleStep(50)
        self.double_click_slider.valueChanged.connect(self._on_double_click_interval_changed)
        double_click_row.addWidget(self.double_click_slider)
        self.double_click_label = QLabel("300ms")
        double_click_row.addWidget(self.double_click_label)
        layout.addWidget(double_click_widget)

        # 触发按键配置
        layout, group = page.add_group("触发按键设置")

        normal_row = QHBoxLayout()
        normal_row.addWidget(self._create_label("普通触发"))
        self.normal_trigger_recorder = InputTriggerRecorderWidget()
        install_tooltip(self.normal_trigger_recorder, tr("点击录制框后按下鼠标按键或键盘按键（可同时按住修饰键）"))
        normal_row.addWidget(self.normal_trigger_recorder, 1)
        layout.addLayout(normal_row)

        special_row = QHBoxLayout()
        special_row.addWidget(self._create_label("特殊触发"))
        self.special_trigger_recorder = InputTriggerRecorderWidget()
        install_tooltip(self.special_trigger_recorder, tr("特殊应用（如专业软件）使用此触发方式"))
        special_row.addWidget(self.special_trigger_recorder, 1)
        layout.addLayout(special_row)

        # 传递钩子引用，录制时暂停钩子
        if hasattr(self, 'tray_app') and self.tray_app and hasattr(self.tray_app, 'mouse_hook'):
            self.normal_trigger_recorder.set_mouse_hook(self.tray_app.mouse_hook)
            self.special_trigger_recorder.set_mouse_hook(self.tray_app.mouse_hook)

        # 重新连接清空按钮，让其自动应用配置
        self.normal_trigger_recorder.clear_btn.clicked.disconnect()
        self.normal_trigger_recorder.clear_btn.clicked.connect(lambda: self._on_clear_trigger('normal'))
        self.special_trigger_recorder.clear_btn.clicked.disconnect()
        self.special_trigger_recorder.clear_btn.clicked.connect(lambda: self._on_clear_trigger('special'))

        apply_btn = QPushButton(tr("应用触发设置"))
        apply_btn.clicked.connect(self._on_trigger_config_changed)
        layout.addWidget(apply_btn)

        # 特殊触发应用
        layout, group = page.add_group("特殊触发应用列表")

        # 让此分组占据页面剩余空间
        page.layout.setStretchFactor(group, 1)

        # 按钮控制区 (置于列表上方，始终显示)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.special_add_btn = QPushButton(tr("新建"))
        self.special_add_btn.clicked.connect(self._add_special_app)
        btn_layout.addWidget(self.special_add_btn, 1)

        self.special_del_btn = QPushButton(tr("删除"))
        self.special_del_btn.clicked.connect(self._remove_special_app)
        btn_layout.addWidget(self.special_del_btn, 1)

        reset_btn = QPushButton(tr("重置默认"))
        reset_btn.clicked.connect(self._reset_special_apps)
        btn_layout.addWidget(reset_btn, 1)

        apply_btn = QPushButton(tr("应用更改"))
        apply_btn.clicked.connect(self._apply_special_apps)
        btn_layout.addWidget(apply_btn, 1)

        layout.addLayout(btn_layout)

        # 列表区域
        self.special_apps_list = QListWidget()
        self.special_apps_list.setDragDropMode(QListWidget.NoDragDrop)
        self.special_apps_list.setDragEnabled(False)
        self.special_apps_list.setAcceptDrops(False)
        self.special_apps_list.setDropIndicatorShown(False)
        self.special_apps_list.setSelectionMode(QtCompat.SingleSelection)
        # 禁用列表自己的滚动条，使用窗口滚动条
        self.special_apps_list.setVerticalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        self.special_apps_list.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        self.special_apps_list.setItemDelegate(NumberedListDelegate(self.special_apps_list))
        self.special_apps_list.setStyleSheet(
            "QListWidget { background: transparent; outline: none; border: none; } QListWidget::item { border: none; background: transparent; min-height: 24px; margin: 1px 0px; padding: 2px 6px; }"
        )
        self.special_apps_list.itemDoubleClicked.connect(self._edit_special_app_item)

        layout.addWidget(self.special_apps_list, 1)  # stretch=1 让列表填满剩余空间

        layout.addStretch()

    # === Settings Load ===

    def _load_popup_settings(self, settings):
        if settings.popup_align_mode == "mouse_top_left":
            self.pos_mouse_tl.setChecked(True)
        else:
            self.pos_mouse_center.setChecked(True)

        popup_auto_close = getattr(settings, "popup_auto_close", True)
        if popup_auto_close:
            self.auto_close_yes.setChecked(True)
        else:
            self.auto_close_no.setChecked(True)
        self.delay_widget.setVisible(popup_auto_close)

        if getattr(settings, "popup_multi_open_when_pinned", False):
            self.multi_open_pinned_yes.setChecked(True)
        else:
            self.multi_open_pinned_no.setChecked(True)

        self.delay_slider.setValue(settings.hover_leave_delay)
        self.delay_label.setText(f"{settings.hover_leave_delay}ms")

        double_click_interval = getattr(settings, "double_click_interval", 300)
        self.double_click_slider.setValue(double_click_interval)
        self.double_click_label.setText(f"{double_click_interval}ms")

        # 加载触发配置
        self.normal_trigger_recorder.set_trigger(
            getattr(settings, "popup_trigger_mode", "mouse"),
            getattr(settings, "popup_trigger_keys", []),
            getattr(settings, "popup_trigger_button", "middle"),
            getattr(settings, "popup_trigger_modifiers", [])
        )
        self.special_trigger_recorder.set_trigger(
            getattr(settings, "popup_special_trigger_mode", "mouse"),
            getattr(settings, "popup_special_trigger_keys", []),
            getattr(settings, "popup_special_trigger_button", "middle"),
            getattr(settings, "popup_special_trigger_modifiers", ["ctrl"])
        )

        self.special_apps_list.clear()
        for app in settings.special_apps:
            item = QListWidgetItem(app)
            item.setFlags((item.flags() & ~QtCompat.ItemIsDragEnabled) | QtCompat.ItemIsEditable)
            self.special_apps_list.addItem(item)

    # === Event Handlers ===

    def _on_popup_pos_changed(self, button):
        if self._updating:
            return
        pos = "mouse_center"
        if button == self.pos_mouse_tl:
            pos = "mouse_top_left"
        self.data_manager.update_settings(popup_align_mode=pos)

    def _on_delay_changed(self, value):
        self.delay_label.setText(f"{value}ms")
        if self._updating:
            return
        self.data_manager.update_settings(hover_leave_delay=value)

    def _on_double_click_interval_changed(self, value):
        self.double_click_label.setText(f"{value}ms")
        if self._updating:
            return
        self.data_manager.update_settings(double_click_interval=value)

    def _on_auto_close_changed(self, button):
        if self._updating:
            return
        auto_close = button == self.auto_close_yes
        self.delay_widget.setVisible(auto_close)
        self.data_manager.update_settings(popup_auto_close=auto_close)

    def _on_multi_open_pinned_changed(self, button):
        if self._updating:
            return
        self.data_manager.update_settings(popup_multi_open_when_pinned=(button == self.multi_open_pinned_yes))

    def _on_clear_trigger(self, trigger_type: str):
        """清空触发配置并自动应用"""
        # 保存当前配置作为备份
        if trigger_type == 'normal':
            recorder = self.normal_trigger_recorder
        else:
            recorder = self.special_trigger_recorder

        backup_mode = recorder.get_mode()
        backup_keys = recorder.get_keys()
        backup_button = recorder.get_button()
        backup_mods = recorder.get_modifiers()

        # 清空UI
        recorder.clear()

        # 尝试应用配置
        result = self._try_apply_trigger_config()

        # 如果验证失败，回退UI到之前的状态
        if not result:
            recorder.set_trigger(backup_mode, backup_keys, backup_button, backup_mods)

    def _try_apply_trigger_config(self) -> bool:
        """尝试应用触发配置，返回是否成功"""
        if self._updating:
            logger.warning("当前正在更新中，跳过配置应用")
            return False

        normal_mode = self.normal_trigger_recorder.get_mode()
        normal_keys = self.normal_trigger_recorder.get_keys()
        normal_btn = self.normal_trigger_recorder.get_button()
        normal_mods = self.normal_trigger_recorder.get_modifiers()
        special_mode = self.special_trigger_recorder.get_mode()
        special_keys = self.special_trigger_recorder.get_keys()
        special_btn = self.special_trigger_recorder.get_button()
        special_mods = self.special_trigger_recorder.get_modifiers()

        logger.info(f"准备保存配置: 普通={normal_mode}({normal_keys})+{normal_btn}+{normal_mods}, 特殊={special_mode}({special_keys})+{special_btn}+{special_mods}")

        # 使用扩展的冲突检测（支持keyboard/hybrid模式）
        is_conflict, msg = check_trigger_conflict(
            button=normal_btn,
            modifiers=normal_mods,
            mode=normal_mode,
            keys=normal_keys
        )
        if is_conflict:
            from ui.styles.themed_messagebox import ThemedMessageBox
            ThemedMessageBox.warning(self, "配置冲突", msg)
            return False

        is_conflict, msg = check_trigger_conflict(
            button=special_btn,
            modifiers=special_mods,
            mode=special_mode,
            keys=special_keys
        )
        if is_conflict:
            from ui.styles.themed_messagebox import ThemedMessageBox
            ThemedMessageBox.warning(self, "配置冲突", f"特殊触发：{msg}")
            return False

        # 保存配置
        self.data_manager.update_settings(
            popup_trigger_mode=normal_mode,
            popup_trigger_keys=normal_keys,
            popup_trigger_button=normal_btn,
            popup_trigger_modifiers=normal_mods,
            popup_special_trigger_mode=special_mode,
            popup_special_trigger_keys=special_keys,
            popup_special_trigger_button=special_btn,
            popup_special_trigger_modifiers=special_mods
        )
        logger.info("配置已保存到数据模型，准备发射信号")
        self.trigger_config_changed.emit()
        logger.info("trigger_config_changed 信号已发射")
        return True

    def _on_trigger_config_changed(self):
        """应用触发配置变更"""
        logger.info("触发配置变更按钮被点击")
        self._try_apply_trigger_config()

    # === Special Apps ===

    def _add_special_app(self):
        item = QListWidgetItem("new_app")
        item.setFlags((item.flags() & ~QtCompat.ItemIsDragEnabled) | QtCompat.ItemIsEditable)
        self.special_apps_list.addItem(item)
        self.special_apps_list.setCurrentItem(item)
        self.special_apps_list.editItem(item)

    def _remove_special_app(self):
        row = self.special_apps_list.currentRow()
        if row >= 0:
            self.special_apps_list.takeItem(row)

    def _edit_special_app_item(self, item):
        self.special_apps_list.editItem(item)

    def _reset_special_apps(self):
        self.special_apps_list.clear()
        for app in DEFAULT_SPECIAL_APPS:
            item = QListWidgetItem(app)
            item.setFlags((item.flags() & ~QtCompat.ItemIsDragEnabled) | QtCompat.ItemIsEditable)
            self.special_apps_list.addItem(item)
        self._apply_special_apps()

    def _apply_special_apps(self):
        if self._updating:
            return
        apps = []
        for i in range(self.special_apps_list.count()):
            item = self.special_apps_list.item(i)
            text = item.text().strip().lower()
            if text:
                apps.append(text)
        self.data_manager.update_settings(special_apps=apps)
        self.special_apps_changed.emit()

    def _validate_hotkey(self, hotkey_str: str) -> tuple:
        """验证快捷键是否有效

        Returns:
            (is_valid: bool, error_msg: str)
        """
        if not hotkey_str or not hotkey_str.strip():
            return True, ""

        parts = [p.strip() for p in hotkey_str.split("+")]
        modifiers = []
        main_key = None

        for part in parts:
            part_lower = part.lower().replace("<", "").replace(">", "")
            if part_lower in ("ctrl", "alt", "shift", "cmd", "win"):
                modifiers.append(part_lower)
            else:
                main_key = part

        if "alt" in modifiers:
            return False, "不允许使用 Alt 键\n请使用 Ctrl、Shift 或 Win"

        if not main_key:
            return False, "必须包含一个主键（字母、数字或功能键）"

        if not modifiers:
            return False, "必须包含至少一个修饰键（Ctrl、Shift、Win）"

        try:
            from core.hotkey_conflict_checker import check_conflict

            is_conflict, conflict_desc = check_conflict(hotkey_str)
            if is_conflict:
                return False, f"快捷键冲突：{conflict_desc}"
        except Exception:
            logger.debug("检查快捷键冲突失败", exc_info=True)

        return True, ""
