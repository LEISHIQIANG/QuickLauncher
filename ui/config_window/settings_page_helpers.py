"""Shared settings page helpers."""

import sys

from core.i18n import is_chinese, tr
from qt_compat import (
    QLabel,
    QSpinBox,
    QtCompat,
)


class SettingsPageHelpersMixin:
    def _create_label(self, text):
        """创建右对齐标签，自动处理2字/3字与4字对齐"""
        clean_text = tr(text).replace(":", "")
        new_text = clean_text

        if not is_chinese():
            lbl = QLabel(new_text + ":")
            lbl.setAlignment(QtCompat.AlignRight | QtCompat.AlignVCenter)
            return lbl

        # 2字 -> 4字对齐 (中间加2个全角空格)
        if len(clean_text) == 2:
            new_text = f"{clean_text[0]}\u3000\u3000{clean_text[1]}"
        # 3字 -> 4字对齐 (中间加1个半角空格/En Space)
        elif len(clean_text) == 3:
            new_text = f"{clean_text[0]}\u2002{clean_text[1]}\u2002{clean_text[2]}"

        lbl = QLabel(new_text + ":")
        lbl.setAlignment(QtCompat.AlignRight | QtCompat.AlignVCenter)
        return lbl

    def _create_spinbox(self, min_val, max_val, suffix=""):
        spinbox = QSpinBox()
        spinbox.setRange(min_val, max_val)
        spinbox.setSuffix(tr(suffix) if suffix else "")
        spinbox.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        spinbox.setFixedWidth(60)
        spinbox.setMinimumHeight(24)
        spinbox.setAlignment(QtCompat.AlignCenter)
        return spinbox

    def _is_win11(self) -> bool:
        try:
            return sys.getwindowsversion().build >= 22000
        except Exception:
            return False

    def _is_win10(self) -> bool:
        try:
            v = sys.getwindowsversion()
            return v.major == 10 and v.build < 22000
        except Exception:
            return False
