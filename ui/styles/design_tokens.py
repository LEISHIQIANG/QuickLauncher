"""Design tokens for QuickLauncher UI.

Single source of truth for the visual design language. Every component that
draws or styles itself should pull colours, radii, spacing, elevation and
motion values from this module instead of hard-coding literals.

The token catalogue mirrors §3.1 of ``UI_OPTIMIZATION_PLAN.md``:

* :class:`SurfaceScale`  – window/dialog/control backgrounds
* :class:`TextScale`     – typography colours
* :class:`BorderScale`   – hairlines, dividers, focus rings
* :class:`StatusScale`   – success / warning / error / info semantics
* :class:`RadiusScale`   – 4 / 6 / 8 / 10 / 12 corner radii
* :class:`SpacingScale`  – 4-px based spacing ladder
* :class:`Elevation`     – (offset, blur, colour) tuples for shadows
* :class:`DurationScale` / :class:`EasingScale` – motion tokens

The :func:`surface` / :func:`text` / :func:`border` accessors accept a theme
key (``"dark"`` / ``"light"``) plus a semantic key. They are the recommended
call-site for new code; legacy code can still import the raw scale constants
if the call site is in a hot paint path.

This module is intentionally tiny and dependency free (only PyQt5 via
``qt_compat``); the audit lint :mod:`scripts.audit_hardcoded_colors` whitelists
this file.
"""

from __future__ import annotations

from qt_compat import QColor

__all__ = [
    "SurfaceScale",
    "TextScale",
    "BorderScale",
    "StatusScale",
    "RadiusScale",
    "SpacingScale",
    "Elevation",
    "DurationScale",
    "EasingScale",
    "surface",
    "text",
    "border",
    "status",
    "radius",
    "spacing",
    "elevation",
    "duration",
    "easing",
    "Theme",
    "hex_qss",
    "selection_bg_qss",
    "selection_text_qss",
    "selection_hover_bg_qss",
]


class Theme:
    """Canonical theme identifiers."""

    DARK = "dark"
    LIGHT = "light"


_VALID_THEMES = (Theme.DARK, Theme.LIGHT)


# ---------------------------------------------------------------------------
# Surface (background) colours
# ---------------------------------------------------------------------------


class SurfaceScale:
    """Background colours grouped by usage.

    Values mirror the legacy ``Colors`` class in :mod:`ui.styles.style` so
    adopting the new token layer does not change the rendered output. The
    names use semantic role names (``bg_dialog``, ``bg_chrome`` …) rather
    than colour literals to keep the design system intuitive.
    """

    # Dialog / popup body backgrounds (semi-transparent, glass friendly)
    bg_dialog_dark = QColor(28, 28, 30, 230)
    bg_dialog_light = QColor(242, 242, 247, 205)

    # Chrome (title bars, tool windows, control surfaces)
    bg_chrome_dark = QColor(43, 43, 43, 230)
    bg_chrome_light = QColor(255, 255, 255, 235)

    # Elevated surfaces (cards, list items)
    bg_elevated_dark = QColor(58, 58, 60, 230)
    bg_elevated_light = QColor(255, 255, 255, 245)

    # Glass backgrounds used by ``glass_background.py``
    bg_glass_dark_win10 = QColor(28, 28, 30, 180)
    bg_glass_dark_win11 = QColor(28, 28, 30, 100)
    bg_glass_light_win10 = QColor(242, 242, 247, 160)
    bg_glass_light_win11 = QColor(242, 242, 247, 100)

    # Subtle hover / pressed overlays
    bg_hover_subtle_dark = QColor(255, 255, 255, 15)
    bg_hover_subtle_light = QColor(0, 0, 0, 10)
    bg_pressed_subtle_dark = QColor(255, 255, 255, 25)
    bg_pressed_subtle_light = QColor(0, 0, 0, 18)

    # Selection highlight
    bg_selection_dark = QColor(10, 132, 255, 76)
    bg_selection_light = QColor(0, 122, 255, 36)

    # List item (settings panel / macro record) backgrounds
    bg_list_item_dark = QColor(255, 255, 255, 18)
    bg_list_item_hover_dark = QColor(255, 255, 255, 30)
    bg_list_item_light = QColor(120, 120, 128, 26)
    bg_list_item_hover_light = QColor(120, 120, 128, 44)
    bg_list_selection = QColor(0, 120, 215, 70)

    # Glass overlay tint (used by ``color_filter_overlay``)
    bg_overlay_tint_dark = QColor(0, 0, 0, 90)
    bg_overlay_tint_light = QColor(255, 255, 255, 110)


# ---------------------------------------------------------------------------
# Text colours
# ---------------------------------------------------------------------------


class TextScale:
    primary_dark = QColor(255, 255, 255, 242)
    primary_light = QColor(28, 28, 30, 242)
    secondary_dark = QColor(255, 255, 255, 217)
    secondary_light = QColor(28, 28, 30, 217)
    tertiary_dark = QColor(255, 255, 255, 180)
    tertiary_light = QColor(60, 60, 67, 165)
    disabled = QColor(128, 128, 128, 128)
    on_accent = QColor(255, 255, 255, 255)

    # List item (settings panel) row numbers
    list_num_dark = QColor(255, 255, 255, 100)
    list_num_light = QColor(0, 0, 0, 80)
    list_num_selected_dark = QColor(255, 255, 255, 200)


# ---------------------------------------------------------------------------
# Border / separator colours
# ---------------------------------------------------------------------------


class BorderScale:
    subtle_dark = QColor(190, 190, 197, 60)
    subtle_light = QColor(229, 229, 234, 150)
    strong_dark = QColor(255, 255, 255, 100)
    strong_light = QColor(0, 0, 0, 90)
    separator_dark = QColor(255, 255, 255, 41)
    separator_light = QColor(60, 60, 67, 46)
    focus = QColor(0, 122, 255, 255)
    focus_dark = QColor(10, 132, 255, 255)

    # List item (settings panel) borders
    list_item_dark = QColor(255, 255, 255, 22)
    list_item_light = QColor(60, 60, 67, 18)


# ---------------------------------------------------------------------------
# Semantic status colours
# ---------------------------------------------------------------------------


class StatusScale:
    success = QColor(48, 209, 88, 255)
    success_dark = QColor(48, 209, 88, 200)
    warning = QColor(255, 159, 10, 255)
    warning_dark = QColor(255, 159, 10, 200)
    error = QColor(255, 59, 48, 255)
    error_dark = QColor(255, 69, 58, 220)
    info = QColor(100, 210, 255, 255)
    info_dark = QColor(10, 132, 255, 220)

    # Node states used in chain_canvas
    node_success = QColor(212, 237, 218, 255)
    node_success_strong = QColor(46, 125, 50, 255)
    node_error = QColor(255, 205, 210, 255)
    node_error_strong = QColor(211, 47, 47, 255)
    node_warning = QColor(255, 243, 205, 255)
    node_warning_strong = QColor(245, 124, 0, 255)

    # Drop-target / drag-over highlight (used by folder_panel, icon_grid)
    drop_highlight_pen = QColor(168, 230, 207, 180)
    drop_highlight_brush_soft = QColor(168, 230, 207, 45)
    drop_highlight_brush_strong = QColor(168, 230, 207, 75)
    drop_highlight_pressed = QColor(70, 180, 140, 200)

    # Macro record dialog (press / release / wheel + accent purple)
    macro_press_dark = QColor(120, 220, 150)
    macro_press_light = QColor(20, 130, 60)
    macro_release_dark = QColor(255, 145, 120)
    macro_release_light = QColor(170, 40, 40)
    macro_wheel_dark = QColor(120, 180, 240)
    macro_wheel_light = QColor(40, 90, 200)
    macro_accent_purple = QColor(192, 132, 252)

    # Support page / donation card palette (used by settings_support_page)
    support_card_bg_dark = QColor(255, 255, 255, 10)
    support_card_bg_light = QColor(0, 0, 0, 5)
    support_card_border_dark = QColor(255, 255, 255, 12)
    support_card_border_light = QColor(0, 0, 0, 10)
    support_card_hover_dark = QColor(255, 255, 255, 20)
    support_card_hover_light = QColor(255, 255, 255, 217)
    support_text_primary_dark = QColor(255, 255, 255, 240)
    support_text_primary_light = QColor(28, 28, 30, 230)
    support_text_secondary_dark = QColor(255, 255, 255, 128)
    support_text_secondary_light = QColor(28, 28, 30, 128)

    # QR code glow / halo palette (settings_support_page QR container)
    qr_glow_outer = QColor(255, 235, 190)  # outer warm tint
    qr_glow_inner = QColor(255, 180, 100)  # inner amber
    qr_container_bg_dark = QColor(255, 255, 255, 10)
    qr_container_border_dark = QColor(255, 255, 255, 12)


class GroupIconScale:
    """Settings panel group icon accent colours (categorical, not theme-aware).

    These are the accent base hues for the navigation group icons in
    ``ui/config_window/settings_panel.py``.  They are *not* theme-aware
    because each entry is tied to a specific navigation category
    (danger, plugin, command …) and conveys brand identity rather than
    theme state.
    """

    danger = QColor(255, 99, 99)
    plugin = QColor(44, 190, 155)
    bookmark = QColor(255, 184, 77)
    command = QColor(82, 145, 255)
    support = QColor(255, 122, 86)
    log = QColor(54, 176, 116)
    theme = QColor(112, 101, 242)
    language = QColor(28, 150, 130)
    popup = QColor(45, 126, 235)
    about = QColor(28, 150, 130)
    about_light = QColor(45, 126, 235)
    about_dark = QColor(96, 166, 255)

    # Icon ink (theme-aware — one constant per theme, hardcoded for now)
    ink_light = QColor(38, 49, 64, 150)
    ink_dark = QColor(235, 241, 250, 165)

    # List item text colours for light theme (dark theme already uses TextScale)
    list_text_selected_light = QColor(0, 0, 0, 242)
    list_text_hovered_light = QColor(0, 0, 0, 200)
    list_text_normal_light = QColor(0, 0, 0, 150)
    list_text_tertiary_dark = QColor(255, 255, 255, 150)


# ---------------------------------------------------------------------------
# Radius, spacing, elevation, motion
# ---------------------------------------------------------------------------


class RadiusScale:
    """Corner radius ladder – 4 / 6 / 8 / 10 / 12 only."""

    xs = 4
    sm = 6
    md = 8
    lg = 10
    xl = 12


class SpacingScale:
    """Spacing ladder – 4-px based.

    The audit lint ``audit_grid_violations`` blocks any ``sp()`` call whose
    argument is not a multiple of 4 (whitelist: 1, 3, 5, 6 for hairline
    borders / line heights / 1-px rings). Use these named keys when the
    semantic intent is clear.
    """

    s2 = 4
    s3 = 8
    s4 = 12
    s5 = 16
    s6 = 20
    s7 = 24
    s8 = 32
    s9 = 48


class Elevation:
    """Shadow elevation tokens.

    Each entry is ``(y_offset, blur_radius, colour)`` consumed by
    :class:`QGraphicsDropShadowEffect`. The colour is the shadow tint;
    alpha controls intensity.
    """

    elev_0 = (0, 0, QColor(0, 0, 0, 0))
    elev_1 = (3, 12, QColor(0, 0, 0, 30))
    elev_2 = (6, 20, QColor(0, 0, 0, 50))
    elev_3 = (12, 32, QColor(0, 0, 0, 80))

    @staticmethod
    def for_level(level: int, is_win10: bool = False) -> tuple[int, int, QColor]:
        """Return the elevation tuple, automatically downgrading on Win10."""

        if is_win10 and level >= 3:
            level = 1
        return {
            0: Elevation.elev_0,
            1: Elevation.elev_1,
            2: Elevation.elev_2,
            3: Elevation.elev_3,
        }[max(0, min(3, level))]


class DurationScale:
    """Animation duration tokens (milliseconds)."""

    INSTANT = 50
    FAST = 120
    NORMAL = 200
    SLOW = 320
    X_SLOW = 480

    # Specific UI scenarios
    FADE_IN = 200
    FADE_OUT = 160
    SLIDE_IN = 240
    SCALE_IN = 220
    RIPPLE = 280
    TOOLTIP = 120
    THEME_SWITCH = 200
    DIALOG_OPEN = 280
    DIALOG_CLOSE = 200


class EasingScale:
    """Cubic-bezier easing curves in CSS notation."""

    STANDARD = "cubic-bezier(0.4, 0.0, 0.2, 1.0)"
    EMPHASIZED = "cubic-bezier(0.2, 0.0, 0.0, 1.0)"
    ACCELERATE = "cubic-bezier(0.4, 0.0, 1.0, 1.0)"
    DECELERATE = "cubic-bezier(0.0, 0.0, 0.2, 1.0)"
    LINEAR = "linear"


# ---------------------------------------------------------------------------
# Public resolution helpers
# ---------------------------------------------------------------------------


def _check_theme(theme: str) -> str:
    if theme not in _VALID_THEMES:
        return Theme.DARK
    return theme


def surface(theme: str, key: str) -> QColor:
    """Resolve a :class:`QColor` from :class:`SurfaceScale`.

    ``key`` is the *stem* of the constant – e.g. ``"bg_dialog"`` resolves to
    ``bg_dialog_dark`` / ``bg_dialog_light`` based on ``theme``.

    Pre-suffixed keys such as ``"bg_glass_dark_win10"`` (which already contain
    ``_dark`` or ``_light``) are tried literally first, then with the
    ``_dark`` / ``_light`` suffix appended (see §4.1 plan for migration
    consistency).
    """

    theme = _check_theme(theme)
    suffix = "_dark" if theme == Theme.DARK else "_light"

    # (1) Try the bare key literally — catches pre-suffixed constants like
    #     "bg_glass_dark_win10", "bg_dialog_dark" etc.
    value = getattr(SurfaceScale, key, None)
    if value is not None:
        return QColor(value)

    # (2) Try {key}{suffix} — the conventional pattern
    full = f"{key}{suffix}"
    value = getattr(SurfaceScale, full, None)
    if value is not None:
        return QColor(value)

    return QColor(0, 0, 0, 0)


def text(theme: str, key: str) -> QColor:
    """Resolve a text colour. ``key`` is the semantic role (``"primary"`` …)."""

    theme = _check_theme(theme)
    suffix = "_dark" if theme == Theme.DARK else "_light"
    full = f"{key}{suffix}"
    value = getattr(TextScale, full, None)
    if value is None:
        # Allow fully-qualified keys
        value = getattr(TextScale, key, None)
    if value is None:
        return QColor(255, 255, 255, 255)
    return QColor(value)


def border(theme: str, key: str) -> QColor:
    """Resolve a border / separator colour."""

    theme = _check_theme(theme)
    suffix = "_dark" if theme == Theme.DARK else "_light"
    full = f"{key}{suffix}"
    value = getattr(BorderScale, full, None)
    if value is None:
        value = getattr(BorderScale, key, None)
    if value is None:
        return QColor(0, 0, 0, 0)
    return QColor(value)


def status(key: str) -> QColor:
    """Resolve a :class:`StatusScale` colour. Theme-agnostic."""

    value = getattr(StatusScale, key, None)
    if value is None:
        return QColor(128, 128, 128, 255)
    return QColor(value)


def radius(key: str) -> int:
    """Resolve a :class:`RadiusScale` key. Returns 8 on unknown key."""

    value = getattr(RadiusScale, key, None)
    if value is None:
        return RadiusScale.md
    return int(value)


def spacing(key: str) -> int:
    """Resolve a :class:`SpacingScale` key. Returns 8 on unknown key."""

    value = getattr(SpacingScale, key, None)
    if value is None:
        return SpacingScale.s3
    return int(value)


def elevation(level: int, *, is_win10: bool = False) -> tuple[int, int, QColor]:
    """Resolve an :class:`Elevation` tuple by level (0–3)."""

    return Elevation.for_level(level, is_win10=is_win10)


def duration(key: str) -> int:
    """Resolve a :class:`DurationScale` key in milliseconds."""

    value = getattr(DurationScale, key, None)
    if value is None:
        return DurationScale.NORMAL
    return int(value)


def easing(key: str) -> str:
    """Resolve an :class:`EasingScale` key as a CSS cubic-bezier string."""

    value = getattr(EasingScale, key, None)
    if value is None:
        return EasingScale.STANDARD
    return str(value)


def apply_motion_scale(value: int, scale: float = 1.0) -> int:
    """Multiply a duration by the user motion-scale preference.

    Honours ``Settings.motion_scale`` (range 0.5–2.0) for accessibility. The
    value is clamped to ``[0, 1000]`` to avoid pathological animations.
    """

    if scale is None or scale == 1.0:
        return int(value)
    try:
        scaled = int(round(value * float(scale)))
    except (TypeError, ValueError):
        return int(value)
    return max(0, min(1000, scaled))


# ---------------------------------------------------------------------------
# QSS bridge helpers
# ---------------------------------------------------------------------------


def _qss_color(color: QColor) -> str:
    """QColor → ``rgba(r, g, b, a)``."""
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


def hex_qss(color: QColor) -> str:
    """QColor → ``#rrggbb`` (drops alpha)."""
    return f"#{color.red():02x}{color.green():02x}{color.blue():02x}"


def selection_bg_qss(theme: str) -> str:
    """Return ``rgba(10, 132, 255, 0.30)`` for dark, ``rgba(0, 122, 255, 0.14)`` for light."""
    if theme == "dark":
        return "rgba(10, 132, 255, 0.30)"
    return "rgba(0, 122, 255, 0.14)"


def selection_text_qss(theme: str) -> str:
    """Return ``rgba(255, 255, 255, 0.95)`` for dark, ``rgba(28, 28, 30, 0.96)`` for light."""
    if theme == "dark":
        return "rgba(255, 255, 255, 0.95)"
    return "rgba(28, 28, 30, 0.96)"


def selection_hover_bg_qss(theme: str) -> str:
    """Return ``rgba(255, 255, 255, 0.08)`` for dark, ``rgba(0, 0, 0, 0.05)`` for light."""
    if theme == "dark":
        return "rgba(255, 255, 255, 0.08)"
    return "rgba(0, 0, 0, 0.05)"
