"""Command-dialog icon helpers.

Extracted from :mod:`ui.config_window.command_dialog` as part of the
P1-06 file-split pass.  The :class:`CommandDialogIconMixin` owns the
preview update, the auto-generated command icon painter and the
browse/clear handlers.
"""

# noqa: pixmap_dpi - QPixmap constructed locally; drawn via painter that
#            honours devicePixelRatio at the paint-time context.
from __future__ import annotations

import logging
import os

from qt_compat import QColor, QFont, QPainter, QPixmap, QRectF, QtCompat
from ui.utils.pixel_snap import create_pixmap
from ui.utils.ui_scale import font_px, sp

from .icon_browse_helper import choose_custom_icon

logger = logging.getLogger(__name__)


class CommandDialogIconMixin:
    """Mixin that owns the icon preview / browse / clear handlers.

    The host class is expected to expose:

    * :pyattr:`_custom_icon_path` — current custom icon path
    * :pyattr:`_updating_icon` — re-entrancy guard
    * :pyattr:`theme` — current theme (``"dark"`` / ``"light"``)
    * :pyattr:`invert_light_cb` / :pyattr:`invert_dark_cb` — invert flags
    * :pyattr:`icon_preview` / :pyattr:`icon_path_edit` — display widgets
    * :pyattr:`type_combo` — used to pick the auto-generated glyph
    """

    def _update_icon_preview(self):
        """更新图标预览"""
        # 避免递归调用或死循环，如果正在更新中则返回
        if getattr(self, "_updating_icon", False):
            return
        self._updating_icon = True

        try:
            pixmap = None

            if self._custom_icon_path:
                try:
                    should_load = False
                    # 检查是否为资源路径 (包含逗号)
                    if "," in self._custom_icon_path:
                        should_load = True
                    # 或者检查文件是否存在
                    elif os.path.exists(self._custom_icon_path):
                        should_load = True

                    if should_load:
                        from core.icon_extractor import IconExtractor

                        pixmap = IconExtractor.from_file(self._custom_icon_path, 48)
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"加载自定义图标失败: {e}")

            if not pixmap or pixmap.isNull():
                pixmap = self._create_command_icon(48)

            # 应用反转（根据当前主题对应的反转标志）
            _current_theme = getattr(self, "theme", "dark")
            _need_invert = (
                self.invert_light_cb.isChecked() if _current_theme == "light" else self.invert_dark_cb.isChecked()
            )
            if _need_invert and pixmap and not pixmap.isNull():
                from core.icon_extractor import IconExtractor

                pixmap = IconExtractor.invert_pixmap(pixmap)

            # 缩放到预览尺寸
            if pixmap and not pixmap.isNull():
                pixmap = pixmap.scaled(sp(32), sp(32), QtCompat.KeepAspectRatio, QtCompat.SmoothTransformation)
                self.icon_preview.setPixmap(pixmap)
            else:
                self.icon_preview.clear()
        except Exception as exc:  # noqa: BLE001
            logger.debug("更新图标预览失败: %s", exc, exc_info=True)
        finally:
            self._updating_icon = False

    def _create_command_icon(self, size: int) -> QPixmap:
        """创建命令图标"""
        try:
            pixmap = create_pixmap(size, size)
            pixmap.fill(QtCompat.transparent)

            painter = QPainter(pixmap)
            try:
                painter.setRenderHint(QtCompat.Antialiasing)
                painter.setRenderHint(QtCompat.HighQualityAntialiasing)

                painter.setBrush(QColor(50, 50, 50))
                painter.setPen(QtCompat.NoPen)
                margin = size // 8
                painter.drawRoundedRect(QRectF(margin, margin, size - margin * 2, size - margin * 2), 6, 6)

                painter.setPen(QColor(0, 255, 0))
                font = QFont("Consolas")
                font.setPixelSize(font_px(max(9, size // 3)))
                font.setBold(True)
                painter.setFont(font)

                # 根据类型显示不同图标文本
                text = ">_"
                type_index = self.type_combo.currentIndex()  # type: ignore[attr-defined]
                if type_index == 1:  # PowerShell
                    text = "PS"
                    painter.setPen(QColor(90, 180, 255))
                elif type_index == 2:  # Python
                    text = "Py"
                    painter.setPen(QColor(255, 215, 0))  # 金色
                elif type_index == 3:  # Git Bash
                    text = "Sh"
                    painter.setPen(QColor(232, 79, 52))  # 橙红色
                elif type_index == 4:  # Built-in
                    text = "In"
                    painter.setPen(QColor(100, 200, 255))  # 蓝色

                painter.drawText(pixmap.rect(), QtCompat.AlignCenter, text)
            finally:
                painter.end()
            return pixmap
        except Exception as e:  # noqa: BLE001
            logger.error("创建命令图标失败: %s", e, exc_info=True)
            # 返回一个空的透明图片防止后续崩溃
            empty = create_pixmap(size, size)
            empty.fill(QtCompat.transparent)
            return empty

    def _browse_icon(self):
        """浏览图标文件"""
        file_path = choose_custom_icon(self, "选择图标")
        if file_path:
            self._custom_icon_path = file_path
            self.icon_path_edit.setText(file_path)
            self._update_icon_preview()

    def _clear_icon(self):
        """清除自定义图标"""
        self._custom_icon_path = ""
        self.icon_path_edit.clear()
        self._update_icon_preview()


__all__ = ["CommandDialogIconMixin"]
