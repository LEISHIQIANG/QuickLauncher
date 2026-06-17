"""Grasshopper-style grouped-button widget for the chain dialog module bar.

Extracted from :mod:`ui.config_window.chain_dialog` during the
P1-06 file-split pass.  The widget lays out small action buttons in
a 3-row grid; the bottom label displays the group title.

The companion :func:`make_module_button` factory creates the
76x24 px pill-style push-buttons that populate these groups.
"""

from __future__ import annotations

from qt_compat import (
    QGridLayout,
    QLabel,
    QPushButton,
    Qt,
    QVBoxLayout,
    QWidget,
)
from ui.utils.ui_scale import scale_qss, sp


class GrasshopperGroupWidget(QWidget):
    """Grasshopper 风格的二级属性/电池组团控件，支持 2 行紧凑排布和底部微型标签。"""

    def __init__(self, title: str, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.setObjectName("GrasshopperGroup")

        # 布局：垂直紧凑
        layout = QVBoxLayout(self)
        layout.setContentsMargins(sp(6), sp(4), sp(6), sp(2))
        layout.setSpacing(sp(2))

        # 2行格栅布局放置电池按钮
        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(sp(4))
        layout.addLayout(self.grid_layout)

        # 底部小文字标题标签
        self.label = QLabel(title)
        self.label.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]

        # 配色与分割线样式
        if theme == "dark":
            border_color = "rgba(255, 255, 255, 15)"
            bg_color = "rgba(255, 255, 255, 4)"
            label_color = "rgba(255, 255, 255, 120)"
            line_color = "rgba(255, 255, 255, 20)"
        else:
            border_color = "rgba(0, 0, 0, 15)"
            bg_color = "rgba(0, 0, 0, 3)"
            label_color = "rgba(0, 0, 0, 130)"
            line_color = "rgba(0, 0, 0, 15)"

        self.label.setStyleSheet(
            scale_qss(
                f"""
            QLabel {{
                color: {label_color};
                font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
                font-size: 9px;
                font-weight: bold;
                background: transparent;
                padding-top: 2px;
                border-top: 1px solid {line_color};
            }}
        """
            )
        )
        layout.addWidget(self.label)

        self.setStyleSheet(
            scale_qss(
                f"""
            QWidget#GrasshopperGroup {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 4px;
            }}
        """
            )
        )
        self.setFixedHeight(sp(102))

        self._button_count = 0

    def add_button(self, button: QPushButton):
        # 采用上下三排的形式摆放 (row=0, row=1, row=2)
        row = self._button_count % 3
        col = self._button_count // 3
        self.grid_layout.addWidget(button, row, col)
        self._button_count += 1


def make_module_button(title: str, callback) -> QPushButton:
    """Create a Grasshopper-style 76x24 px module button.

    Extracted from :meth:`ChainDialog._make_module_button` so the
    module-bar factories can stay free of dialog state.
    """
    btn = QPushButton(title)
    # 草蜢式的精美小电池按纽 (固定为宽 76px，高 24px)
    btn.setFixedSize(sp(76), sp(24))
    btn.clicked.connect(callback)
    return btn


__all__ = ["GrasshopperGroupWidget", "make_module_button"]
