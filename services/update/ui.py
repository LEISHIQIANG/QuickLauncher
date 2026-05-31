"""Update notification UI helpers."""

import html
import logging
import re

from core.i18n import tr
from services.update.config import UpdateInfo
from ui.styles.themed_messagebox import ThemedMessageBox

logger = logging.getLogger(__name__)


def _markdown_to_html(md: str, theme: str = "dark") -> str:
    """Lightweight GitHub-flavored markdown to HTML converter."""
    if not md:
        return ""

    text_color = "#d1d1d6" if theme == "dark" else "#3a3a3c"
    secondary_color = "#a1a1a6" if theme == "dark" else "#636366"
    link_color = "#0a84ff" if theme == "dark" else "#007aff"
    code_bg = "rgba(255,255,255,0.09)" if theme == "dark" else "rgba(0,0,0,0.055)"
    code_color = "#ff9f0a" if theme == "dark" else "#c44600"
    heading_color = "#ffffff" if theme == "dark" else "#1c1c1e"
    emphasis_color = "#f2f2f7" if theme == "dark" else "#242426"
    hr_color = "rgba(255,255,255,0.12)" if theme == "dark" else "rgba(0,0,0,0.12)"
    list_bullet = "#ffb340" if theme == "dark" else "#0a84ff"
    list_text_color = "#e5e5ea" if theme == "dark" else "#2c2c2e"

    lines = md.split("\n")
    html_parts = []
    in_code_block = False
    code_buf = []
    in_list = False
    in_ol = False

    def close_list():
        nonlocal in_list, in_ol
        if in_list:
            html_parts.append("</table>")
            in_list = False
        if in_ol:
            html_parts.append("</ol>")
            in_ol = False

    def inline_format(text: str) -> str:
        placeholders: list[str] = []

        def stash(fragment: str) -> str:
            placeholders.append(fragment)
            return f"\x00{len(placeholders) - 1}\x00"

        def restore(value: str) -> str:
            for idx, fragment in enumerate(placeholders):
                value = value.replace(f"\x00{idx}\x00", fragment)
            return value

        def code_repl(match: re.Match) -> str:
            code = html.escape(match.group(1), quote=False)
            return stash(
                f'<code style="background:{code_bg};color:{code_color};padding:1px 5px;'
                f'border-radius:4px;font-size:11px;">{code}</code>'
            )

        def link_repl(match: re.Match) -> str:
            label = inline_format(match.group(1))
            url = html.escape(match.group(2), quote=True)
            return stash(f'<a href="{url}" style="color:{link_color};text-decoration:none;">{label}</a>')

        text = re.sub(r"`([^`]+)`", code_repl, text)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, text)
        text = html.escape(text, quote=False)
        text = re.sub(
            r"\*\*\*(.+?)\*\*\*",
            rf'<span style="font-weight:500;color:{emphasis_color};"><i>\1</i></span>',
            text,
        )
        text = re.sub(r"\*\*(.+?)\*\*", rf'<span style="font-weight:500;color:{emphasis_color};">\1</span>', text)
        text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", text)
        text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
        text = re.sub(
            r"\[x\]",
            f'<span style="color:{list_bullet};font-weight:500;">[x]</span>',
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\[ \]", f'<span style="color:{secondary_color};">[ ]</span>', text)
        return restore(text)

    for raw_line in lines:
        line = raw_line.rstrip()

        # Code block toggle
        if line.strip().startswith("```"):
            if in_code_block:
                code_text = html.escape("\n".join(code_buf), quote=False)
                html_parts.append(
                    f'<pre style="background:{code_bg};padding:9px 11px;border-radius:7px;'
                    f'font-size:11px;line-height:1.55;overflow-x:auto;margin:8px 0;">'
                    f'<code style="color:{code_color};">{code_text}</code></pre>'
                )
                code_buf = []
                in_code_block = False
            else:
                close_list()
                in_code_block = True
            continue

        if in_code_block:
            code_buf.append(line)
            continue

        stripped = line.strip()

        # Empty line
        if not stripped:
            close_list()
            html_parts.append("")
            continue

        # Horizontal rule
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            close_list()
            html_parts.append(f'<hr style="border:none;border-top:1px solid {hr_color};margin:12px 0;">')
            continue

        # Headings
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            close_list()
            level = len(heading_match.group(1))
            text = inline_format(heading_match.group(2))
            sizes = {1: 17, 2: 15, 3: 14, 4: 13, 5: 12, 6: 12}
            weight = "500"
            margin_top = "13px" if level <= 2 else "10px"
            html_parts.append(
                f'<div style="font-size:{sizes[level]}px;font-weight:{weight};color:{heading_color};'
                f'line-height:1.35;margin-top:{margin_top};margin-bottom:6px;">{text}</div>'
            )
            continue

        # Unordered list
        ul_match = re.match(r"^(\s*)[-*+]\s+(.+)$", line)
        if ul_match:
            if not in_list:
                close_list()
                in_list = True
                html_parts.append('<table style="border-collapse:collapse;margin:5px 0 7px 0;">')
            indent = min(len(ul_match.group(1)) // 2, 3) * 14
            text = inline_format(ul_match.group(2))
            html_parts.append(
                f'<tr><td style="width:{12 + indent}px;padding:2px 4px 2px {indent}px;'
                f'color:{list_bullet};font-size:14px;line-height:1.5;vertical-align:top;">&#8226;</td>'
                f'<td style="padding:2px 0;color:{list_text_color};font-size:12px;'
                f'line-height:1.55;vertical-align:top;">{text}</td></tr>'
            )
            continue

        # Ordered list
        ol_match = re.match(r"^(\s*)\d+\.\s+(.+)$", line)
        if ol_match:
            if not in_ol:
                close_list()
                in_ol = True
                html_parts.append(f'<ol style="margin:5px 0 7px 20px;padding-left:12px;color:{list_text_color};">')
            text = inline_format(ol_match.group(2))
            html_parts.append(f'<li style="margin:2px 0;font-size:12px;line-height:1.55;">{text}</li>')
            continue

        # Regular paragraph
        close_list()
        text = inline_format(stripped)
        html_parts.append(f'<p style="margin:4px 0;font-size:12px;line-height:1.65;color:{text_color};">{text}</p>')

    close_list()

    return "\n".join(html_parts)


class UpdateDialog:
    """Themed update dialog with markdown changelog rendering."""

    @staticmethod
    def show_update_available(update_info: UpdateInfo, on_download=None, on_skip=None, parent=None):
        from qt_compat import (
            QColor,
            QDialog,
            QHBoxLayout,
            QLabel,
            QPainter,
            QPainterPath,
            QPen,
            QPoint,
            QPushButton,
            Qt,
            QtCompat,
            QTextBrowser,
            QTimer,
            QVBoxLayout,
        )
        from ui.styles.style import get_dialog_stylesheet
        from ui.utils.dialog_helper import center_dialog_on_main_window
        from ui.utils.font_manager import get_qfont, tune_font_rendering
        from ui.utils.window_effect import get_window_effect, is_win10, is_win11

        theme = "dark"
        if parent and hasattr(parent, "_theme"):
            theme = parent._theme
        elif parent and hasattr(parent, "data_manager"):
            try:
                theme = parent.data_manager.get_settings().theme
            except Exception as exc:
                logger.debug("获取父窗口主题失败: %s", exc, exc_info=True)

        dialog = QDialog(parent)
        dialog.setWindowTitle(tr("发现更新"))
        dialog.setModal(True)
        dialog.setFixedSize(350, 440)
        dialog.setWindowFlags(QtCompat.FramelessWindowHint | QtCompat.Dialog)
        dialog.setAttribute(QtCompat.WA_TranslucentBackground, True)
        dialog.setFont(get_qfont(12))
        dialog.setWindowOpacity(0)

        corner_radius = 8 if is_win11() else 12
        if theme == "dark":
            bg_color = QColor(28, 28, 30, 180)
            border_color = QColor(190, 190, 197, 60)
        else:
            bg_color = QColor(242, 242, 247, 160)
            border_color = QColor(229, 229, 234, 150)

        title_color = "#ffffff" if theme == "dark" else "#1c1c1e"
        text_color = "#d1d1d6" if theme == "dark" else "#3a3a3c"
        secondary_color = "#a1a1a6" if theme == "dark" else "#636366"
        badge_bg = "rgba(255, 149, 0, 0.15)" if theme == "dark" else "rgba(0, 122, 255, 0.10)"
        badge_color = "#ff9500" if theme == "dark" else "#007aff"
        badge_border = "rgba(255, 149, 0, 0.3)" if theme == "dark" else "rgba(0, 122, 255, 0.25)"

        # Main layout
        layout = QVBoxLayout(dialog)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 12, 14, 12)

        # Title
        title_layout = QHBoxLayout()
        title_layout.setSpacing(8)
        title_layout.setContentsMargins(0, 0, 0, 0)

        icon_label = QLabel()
        ThemedMessageBox.configure_icon_label(icon_label, ThemedMessageBox.Download)
        title_layout.addWidget(icon_label)

        title_label = QLabel(tr("发现更新"))
        title_label.setFont(get_qfont(13, 400))
        title_label.setStyleSheet(f"font-size: 13px; font-weight: 400; color: {title_color};")
        title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title_layout.addWidget(title_label, 1)

        layout.addLayout(title_layout)

        # Version + size badge
        changelog = update_info.changelog_zh or update_info.changelog_en or tr("暂无更新说明。")
        size_mb = update_info.file_size / 1024 / 1024

        version_html = (
            f"<div style=\"font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 12px; "
            f'color: {secondary_color}; margin-bottom: 4px;">'
            f'<span style="display:inline-block;background:{badge_bg};color:{badge_color};'
            f'padding:2px 8px;border-radius:4px;font-weight:400;border:1px solid {badge_border};">'
            f"v{update_info.version}</span>"
            f'<span style="margin-left:8px;color:{secondary_color};"> {size_mb:.1f} MB</span>'
        )
        if update_info.mandatory:
            version_html += (
                f'<span style="margin-left:8px;display:inline-block;background:rgba(255,59,48,0.15);'
                f"color:#ff3b30;padding:2px 8px;border-radius:4px;font-size:11px;"
                f'border:1px solid rgba(255,59,48,0.3);">{tr("强制更新")}</span>'
            )
        version_html += "</div>"

        version_label = QLabel()
        version_label.setTextFormat(Qt.RichText)
        version_label.setText(version_html)
        layout.addWidget(version_label)

        # Changelog area (scrollable, markdown rendered)
        text_browser = QTextBrowser()
        text_browser.setOpenExternalLinks(True)
        text_browser.setFrameShape(QTextBrowser.NoFrame)
        text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        text_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        text_browser.setFont(get_qfont(12))

        html_content = _markdown_to_html(changelog, theme)
        full_html = (
            "<div style=\"font-family: 'Segoe UI', 'Microsoft YaHei UI', sans-serif; "
            f'font-size: 12px; color: {text_color}; line-height: 1.65; padding: 6px 8px;">'
            f"{html_content}</div>"
        )
        text_browser.setHtml(full_html)

        text_browser.setStyleSheet("QTextBrowser { background: transparent; border: none; padding: 0px; }")
        layout.addWidget(text_browser, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addStretch()

        skip_btn = QPushButton(tr("跳过此版本") if not update_info.mandatory else tr("稍后提醒"))
        skip_btn.setFixedHeight(24)
        skip_btn.setMinimumWidth(80)
        skip_btn.clicked.connect(lambda: _on_skip_clicked())
        btn_layout.addWidget(skip_btn)

        download_btn = QPushButton(tr("立即下载"))
        download_btn.setDefault(True)
        download_btn.setFixedHeight(24)
        download_btn.setMinimumWidth(72)
        download_btn.clicked.connect(lambda: _on_download_clicked())
        btn_layout.addWidget(download_btn)

        layout.addLayout(btn_layout)

        # Apply theme
        dialog.setStyleSheet(get_dialog_stylesheet(theme))
        tune_font_rendering(dialog, recursive=True)

        # Paint background
        def paint_event(event):
            painter = QPainter(dialog)
            painter.setRenderHint(QtCompat.Antialiasing)
            if is_win10():
                painter.setRenderHint(QtCompat.HighQualityAntialiasing, True)
                painter.setRenderHint(QtCompat.SmoothPixmapTransform, True)
            inset = 1.0 if is_win10() else 0.5
            path = QPainterPath()
            path.addRoundedRect(
                inset,
                inset,
                dialog.width() - inset * 2,
                dialog.height() - inset * 2,
                corner_radius,
                corner_radius,
            )
            tint = QColor(bg_color)
            if is_win10():
                tint.setAlpha(min(tint.alpha(), 150))
            else:
                tint.setAlpha(min(tint.alpha(), 100))
            painter.fillPath(path, tint)
            pen_c = QColor(border_color)
            pen_c.setAlpha(min(pen_c.alpha(), 120))
            painter.setPen(QPen(pen_c, 1))
            painter.drawPath(path)

        dialog.paintEvent = paint_event

        # Show animation
        dialog._acrylic_applied = False
        dialog._dialog_finished = False

        def show_event(event):
            QDialog.showEvent(dialog, event)
            dialog._dialog_finished = False
            center_dialog_on_main_window(dialog)
            if not dialog._acrylic_applied:
                dialog._acrylic_applied = True
                QTimer.singleShot(10, _apply_acrylic)
            # Fade in
            dialog._opacity_anim = QtCompat.QPropertyAnimation(dialog, b"windowOpacity")
            dialog._opacity_anim.setDuration(200)
            dialog._opacity_anim.setStartValue(0.0)
            dialog._opacity_anim.setEndValue(1.0)
            dialog._opacity_anim.setEasingCurve(QtCompat.OutCubic)
            pos = dialog.pos()
            dialog._pos_anim = QtCompat.QPropertyAnimation(dialog, b"pos")
            dialog._pos_anim.setDuration(200)
            dialog._pos_anim.setStartValue(QPoint(pos.x(), pos.y() + 20))
            dialog._pos_anim.setEndValue(pos)
            dialog._pos_anim.setEasingCurve(QtCompat.OutCubic)
            dialog._anim_group = QtCompat.QParallelAnimationGroup()
            dialog._anim_group.addAnimation(dialog._opacity_anim)
            dialog._anim_group.addAnimation(dialog._pos_anim)
            dialog._anim_group.start()

        dialog.showEvent = show_event

        def _apply_acrylic():
            try:
                if dialog._dialog_finished or not dialog.isVisible():
                    return
                from ui.utils.window_effect import enable_acrylic_for_config_window

                hwnd = int(dialog.winId())
                if not hwnd:
                    return
                effect = get_window_effect()
                if is_win11():
                    effect.set_round_corners(hwnd, enable=True)
                    effect.enable_window_shadow(hwnd, corner_radius)
                else:
                    w, h = dialog.width(), dialog.height()
                    if w > 0 and h > 0:
                        effect.set_window_region(hwnd, w, h, corner_radius)
                enable_acrylic_for_config_window(dialog, theme, blur_amount=30, radius=corner_radius)
            except Exception as exc:
                logger.debug("应用窗口特效失败: %s", exc, exc_info=True)

        def done_result(result):
            dialog._dialog_finished = True
            for attr in ("_anim_group", "_opacity_anim", "_pos_anim"):
                anim = getattr(dialog, attr, None)
                if anim is not None:
                    try:
                        anim.stop()
                    except Exception as exc:
                        logger.debug("停止动画失败: %s", exc, exc_info=True)
            QDialog.done(dialog, result)

        dialog.done = done_result

        result_val = {"value": 0}

        def _on_download_clicked():
            result_val["value"] = 1
            dialog.accept()

        def _on_skip_clicked():
            result_val["value"] = 2
            dialog.reject()

        dialog.exec_()

        if result_val["value"] == 1 and on_download:
            on_download()
        elif result_val["value"] == 2 and not update_info.mandatory and on_skip:
            on_skip()

    @staticmethod
    def show_download_progress_text(current: int, total: int) -> str:
        pct = current / total * 100 if total > 0 else 0
        mb_done = current / 1024 / 1024
        mb_total = total / 1024 / 1024
        return tr("正在下载更新... {done:.1f}/{total:.1f} MB ({pct:.0f}%)", done=mb_done, total=mb_total, pct=pct)

    @staticmethod
    def show_download_failed(error: str, parent=None):
        ThemedMessageBox.critical(parent, tr("更新失败"), tr("更新失败:\n{error}", error=error))

    @staticmethod
    def show_download_finished(on_install=None, parent=None):
        result = ThemedMessageBox.question(
            parent,
            tr("下载完成"),
            tr("新版本已下载完成，是否立即安装并重启？"),
            buttons=ThemedMessageBox.Yes | ThemedMessageBox.No,
            icon_type=ThemedMessageBox.Download,
        )
        if result == ThemedMessageBox.Yes and on_install:
            on_install()

    @staticmethod
    def show_up_to_date(parent=None):
        ThemedMessageBox.information(parent, tr("检查更新"), tr("当前已经是最新版本。"))

    @staticmethod
    def show_check_failed(error: str, parent=None):
        ThemedMessageBox.warning(parent, tr("检查更新失败"), tr("无法检查更新:\n{error}", error=error))


# Backward-compatible alias
UpdateNotification = UpdateDialog
