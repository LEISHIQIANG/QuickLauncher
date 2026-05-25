"""Popup settings page builder."""
from core.i18n import tr
from qt_compat import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QRadioButton,
    QSlider,
    QtCompat,
    QVBoxLayout,
    QWidget,
)
from ui.config_window.settings_helpers import NumberedListDelegate
from ui.tooltip_helper import install_tooltip


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
        self.delay_slider.setRange(0, 2000) # 0-2秒
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

        # 特殊触发应用
        layout, group = page.add_group("特殊触发 (Ctrl+中键)")

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
        self.special_apps_list.setMinimumHeight(120)
        self.special_apps_list.setDragDropMode(QListWidget.NoDragDrop)
        self.special_apps_list.setDragEnabled(False)
        self.special_apps_list.setAcceptDrops(False)
        self.special_apps_list.setDropIndicatorShown(False)
        self.special_apps_list.setSelectionMode(QtCompat.SingleSelection)
        # 开启滚动条，确保列表内容滚动时按钮保持可见
        self.special_apps_list.setVerticalScrollBarPolicy(QtCompat.ScrollBarAsNeeded)
        self.special_apps_list.setItemDelegate(NumberedListDelegate(self.special_apps_list))
        self.special_apps_list.setStyleSheet("QListWidget { background: transparent; outline: none; border: none; } QListWidget::item { border: none; background: transparent; min-height: 24px; margin: 1px 0px; padding: 2px 6px; }")
        self.special_apps_list.itemDoubleClicked.connect(self._edit_special_app_item)

        layout.addWidget(self.special_apps_list, 1)  # stretch=1 让列表填满剩余空间

        layout.addStretch()
