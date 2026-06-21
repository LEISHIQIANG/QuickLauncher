"""Shared settings page helpers."""

from core.i18n import is_chinese, tr
from qt_compat import (
    QLabel,
    QSpinBox,
    QtCompat,
)
from ui.utils.ui_scale import sp


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
        spinbox.setFixedWidth(sp(60))
        spinbox.setMinimumHeight(sp(24))
        spinbox.setAlignment(QtCompat.AlignCenter)
        return spinbox

    def _is_win11(self) -> bool:
        """Check whether the current host is Windows 11 (build >= 22000).

        Uses the canonical :func:`ui.utils.window_effect.is_win11` which reads
        the true OS build via ``RtlGetVersion`` (unaffected by compatibility
        manifests) and caches the result process-wide.
        """
        try:
            from ui.utils.window_effect import is_win11 as _canonical_is_win11

            return bool(_canonical_is_win11())
        except Exception:
            return False

    def _is_win10(self) -> bool:
        """Check whether the current host is Windows 10 (build < 22000).

        See :meth:`_is_win11` for the rationale of using the canonical helper.
        """
        try:
            from ui.utils.window_effect import is_win10 as _canonical_is_win10

            return bool(_canonical_is_win10())
        except Exception:
            return False
