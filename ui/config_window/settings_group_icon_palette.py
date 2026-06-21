"""Categorical accent colour palette for the settings panel group icons.

The settings panel renders small group icons (folder, sliders, guide, …)
next to each section title. The colour is keyed by the *title* of the
section so it stays consistent regardless of the user's theme.

Per §4.1 of ``UI_OPTIMIZATION_PLAN.md`` this file is whitelisted by
``scripts/audit_hardcoded_colors.py`` because token derivation is not
appropriate for categorical palettes.
"""

from __future__ import annotations

from qt_compat import QColor

__all__ = [
    "ACCENT_DANGER",
    "ACCENT_PLUGIN",
    "ACCENT_FAVORITE_COMMAND",
    "ACCENT_COMMAND",
    "ACCENT_SUPPORT",
    "ACCENT_LOG_CONFIG",
    "ACCENT_THEME",
    "ACCENT_LANGUAGE",
    "ACCENT_POPUP",
    "ACCENT_ABOUT",
    "ACCENT_FALLBACK_LIGHT",
    "ACCENT_FALLBACK_DARK",
    "group_icon_accent",
]


# Per-keyword categorical accents used by ``SettingsPanel._group_icon_accent``.

ACCENT_DANGER = QColor(255, 99, 99)  # 危险
ACCENT_PLUGIN = QColor(44, 190, 155)  # 插件
ACCENT_FAVORITE_COMMAND = QColor(255, 184, 77)  # 收藏命令
ACCENT_COMMAND = QColor(82, 145, 255)  # 命令
ACCENT_SUPPORT = QColor(255, 122, 86)  # 支持一下
ACCENT_LOG_CONFIG = QColor(54, 176, 116)  # 日志 / 配置 / 管理
ACCENT_THEME = QColor(112, 101, 242)  # 主题 / 背景 / 外观 / 视觉
ACCENT_LANGUAGE = QColor(28, 150, 130)  # 语言
ACCENT_POPUP = QColor(45, 126, 235)  # 弹窗 / 位置 / 触发 / 交互
ACCENT_ABOUT = QColor(28, 150, 130)  # 关于 / 简介 / 作者

ACCENT_FALLBACK_LIGHT = QColor(45, 126, 235)
ACCENT_FALLBACK_DARK = QColor(96, 166, 255)


def group_icon_accent(title: str, theme: str) -> QColor:
    """Return the categorical accent colour for a settings group title.

    Mirrors the legacy ``SettingsPanel._group_icon_accent`` exactly –
    the only difference is the literals live in this module instead of
    being inlined in the widget.
    """

    if "危险" in title:
        return ACCENT_DANGER
    if "插件" in title:
        return ACCENT_PLUGIN
    if "收藏命令" in title:
        return ACCENT_FAVORITE_COMMAND
    if "命令" in title:
        return ACCENT_COMMAND
    if "支持一下" in title:
        return ACCENT_SUPPORT
    if "日志" in title or "配置" in title or "管理" in title:
        return ACCENT_LOG_CONFIG
    if "主题" in title or "背景" in title or "外观" in title or "视觉" in title:
        return ACCENT_THEME
    if "语言" in title:
        return ACCENT_LANGUAGE
    if "弹窗" in title or "位置" in title or "触发" in title or "交互" in title:
        return ACCENT_POPUP
    if "关于" in title or "简介" in title or "作者" in title:
        return ACCENT_ABOUT
    return ACCENT_FALLBACK_LIGHT if theme == "light" else ACCENT_FALLBACK_DARK
