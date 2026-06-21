"""Theme-aware QSS token factories — one dict per component/theme.

Every token dict mirrors the hard-coded colour values of the original
``style_sheet.py`` / ``glassmorphism.py`` so that the rendered QSS is
byte-for-byte identical.
"""

from __future__ import annotations

from ui.styles.design_tokens import selection_bg_qss, selection_text_qss

# Qt Style Sheets do not support CSS transitions. Runtime micro-interactions
# are implemented with Qt animations; keep this token empty so style output
# never contains declarations silently ignored by Qt.
TRANSITION_CSS = ""

# ----- Plain button (from StyleSheet.get_button_style) -----

BUTTON_PLAIN_DARK = {
    "color_btn_bg": "rgba(255, 255, 255, 0.12)",
    "color_btn_border": "rgba(255, 255, 255, 0.18)",
    "radius_btn": 10,
    "btn_padding": "3px 12px",
    "color_btn_text": "rgba(255, 255, 255, 0.85)",
    "btn_font_size": "11px",
    "btn_font_weight": "400",
    "btn_min_height": "22px",
    "color_btn_hover_bg": "rgba(255, 255, 255, 0.20)",
    "color_btn_hover_border": "rgba(255, 255, 255, 0.25)",
    "color_btn_focus_border": "rgba(10, 132, 255, 0.78)",
    "color_btn_pressed_bg": "rgba(255, 255, 255, 0.08)",
    "color_btn_pressed_border": "rgba(255, 255, 255, 0.14)",
    "color_btn_default_bg": "#0A84FF",
    "color_btn_default_border": "#0A84FF",
    "color_btn_default_hover_bg": "#0077EA",
    "color_btn_default_pressed_bg": "#006FD6",
    "color_btn_default_pressed_border": "#006FD6",
    "color_btn_disabled_bg": "rgba(255, 255, 255, 0.06)",
    "color_btn_disabled_text": "rgba(235, 235, 245, 0.3)",
}
BUTTON_PLAIN_LIGHT = {
    "color_btn_bg": "rgba(255, 255, 255, 0.80)",
    "color_btn_border": "rgba(0, 0, 0, 0.08)",
    "radius_btn": 10,
    "btn_padding": "3px 12px",
    "color_btn_text": "rgba(28, 28, 30, 0.75)",
    "btn_font_size": "11px",
    "btn_font_weight": "400",
    "btn_min_height": "22px",
    "color_btn_hover_bg": "rgba(255, 255, 255, 0.95)",
    "color_btn_hover_border": "rgba(0, 0, 0, 0.10)",
    "color_btn_focus_border": "rgba(0, 122, 255, 0.55)",
    "color_btn_pressed_bg": "rgba(240, 240, 245, 0.90)",
    "color_btn_pressed_border": "rgba(0, 0, 0, 0.12)",
    "color_btn_default_bg": "#007AFF",
    "color_btn_default_border": "#007AFF",
    "color_btn_default_hover_bg": "#0A84FF",
    "color_btn_default_pressed_bg": "#006FD6",
    "color_btn_default_pressed_border": "#006FD6",
    "color_btn_disabled_bg": "rgba(0, 0, 0, 0.04)",
    "color_btn_disabled_text": "rgba(60, 60, 67, 0.3)",
}

# ----- Plain input (from StyleSheet.get_input_style) -----

INPUT_PLAIN_DARK = {
    "color_input_bg": "rgba(190, 190, 197, 0.22)",
    "color_input_border": "rgba(255, 255, 255, 0.15)",
    "radius_input": 6,
    "input_padding": "4px 8px",
    "color_input_text": "#ffffff",
    "input_font_size": "11px",
    "input_font_weight": "400",
    "color_input_focus_border": "#0A84FF",
    "color_input_focus_bg": "rgba(190, 190, 197, 0.28)",
    "color_input_disabled_bg": "rgba(190, 190, 197, 0.12)",
    "color_input_disabled_text": "rgba(235, 235, 245, 0.3)",
}
INPUT_PLAIN_LIGHT = {
    "color_input_bg": "#ffffff",
    "color_input_border": "rgba(0, 0, 0, 0.12)",
    "radius_input": 6,
    "input_padding": "4px 8px",
    "color_input_text": "#1c1c1e",
    "input_font_size": "11px",
    "input_font_weight": "400",
    "color_input_focus_border": "#007AFF",
    "color_input_focus_bg": "#ffffff",
    "color_input_disabled_bg": "#f5f5f7",
    "color_input_disabled_text": "rgba(60, 60, 67, 0.3)",
}

# ----- Scrollbar (from StyleSheet.get_scrollbar_style) -----

SCROLLBAR_DARK = {
    "scrollbar_width": "6px",
    "scrollbar_height": "6px",
    "color_scrollbar_handle": "rgba(255, 255, 255, 80)",
    "color_scrollbar_handle_hover": "rgba(255, 255, 255, 120)",
    "radius_scrollbar_handle": 3,
}
SCROLLBAR_LIGHT = {
    "scrollbar_width": "6px",
    "scrollbar_height": "6px",
    "color_scrollbar_handle": "rgba(0, 0, 0, 60)",
    "color_scrollbar_handle_hover": "rgba(0, 0, 0, 100)",
    "radius_scrollbar_handle": 3,
}

# ----- ComboBox (from StyleSheet.get_combobox_style) -----

_COMBOBOX_ARROW_DARK = (
    "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'>"
    "<path d='M2.5 3.5L5 6L7.5 3.5' fill='none' stroke='white' stroke-width='1.2' stroke-linecap='round'"
    " stroke-linejoin='round'/></svg>"
)
_COMBOBOX_ARROW_LIGHT = (
    "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'>"
    "<path d='M2.5 3.5L5 6L7.5 3.5' fill='none' stroke='black' stroke-width='1.2' stroke-linecap='round'"
    " stroke-linejoin='round'/></svg>"
)

COMBOBOX_DARK = {
    "color_cb_bg": "rgba(190, 190, 197, 0.22)",
    "color_cb_border": "rgba(255, 255, 255, 0.1)",
    "radius_cb": 6,
    "cb_padding": "5px 8px",
    "color_cb_text": "rgba(255, 255, 255, 0.9)",
    "cb_min_height": "24px",
    "cb_font_size": "12px",
    "color_cb_hover_border": "#0A84FF",
    "color_cb_hover_bg": "rgba(190, 190, 197, 0.30)",
    "color_cb_focus_border": "#0A84FF",
    "cb_arrow_svg": _COMBOBOX_ARROW_DARK,
    "color_cb_menu_bg": "rgba(40, 40, 45, 200)",
    "color_cb_menu_border": "rgba(255, 255, 255, 0.12)",
    "radius_cb_menu": 8,
    "color_cb_menu_text": "#ffffff",
    "radius_cb_item": 6,
    "color_cb_item_hover_bg": "rgba(255, 255, 255, 0.08)",
    "color_cb_selected_border": "rgba(10, 132, 255, 0.45)",
}
COMBOBOX_LIGHT = {
    "color_cb_bg": "rgba(255, 255, 255, 120)",
    "color_cb_border": "rgba(0, 0, 0, 0.08)",
    "radius_cb": 6,
    "cb_padding": "5px 8px",
    "color_cb_text": "#1c1c1e",
    "cb_min_height": "24px",
    "cb_font_size": "12px",
    "color_cb_hover_border": "#007AFF",
    "color_cb_hover_bg": "rgba(255, 255, 255, 180)",
    "color_cb_focus_border": "#007AFF",
    "cb_arrow_svg": _COMBOBOX_ARROW_LIGHT,
    "color_cb_menu_bg": "rgba(255, 255, 255, 210)",
    "color_cb_menu_border": "rgba(0, 0, 0, 0.08)",
    "radius_cb_menu": 8,
    "color_cb_menu_text": "#1c1c1e",
    "radius_cb_item": 6,
    "color_cb_item_hover_bg": "rgba(0, 0, 0, 0.05)",
    "color_cb_selected_border": "rgba(0, 122, 255, 0.25)",
}

# ----- GroupBox plain (from StyleSheet.get_groupbox_style) -----

GROUPBOX_PLAIN_DARK = {
    "gb_margin_top": "10px",
    "gb_padding_top": "24px",
    "gb_font_size": "13px",
    "color_gb_text": "white",
    "gb_title_origin": "margin",
    "gb_title_padding_bottom": "8px",
    "color_gb_title_text": "#ffffff",
}
GROUPBOX_PLAIN_LIGHT = {
    "gb_margin_top": "6px",
    "gb_padding_top": "20px",
    "gb_font_size": "13px",
    "color_gb_text": "#1c1c1e",
    "gb_title_origin": "padding",
    "gb_title_padding_bottom": "4px",
    "color_gb_title_text": "#1c1c1e",
}

# ----- Slider (from StyleSheet.get_slider_style) -----

SLIDER_DARK = {
    "slider_groove_height": "4px",
    "radius_slider_groove": 2,
    "color_slider_accent": "#0A84FF",
    "color_slider_track": "#3a3a3c",
    "color_slider_handle_bg": "#ffffff",
    "slider_handle_size": "16px",
    "slider_handle_margin": "-6px 0",
    "radius_slider_handle": 8,
    "slider_handle_border": "1px solid rgba(0, 0, 0, 0.2)",
    "color_slider_handle_hover_bg": "#f8f8f8",
    "color_slider_handle_hover_border": "rgba(0, 0, 0, 0.1)",
    "color_slider_handle_pressed_bg": "#f0f0f0",
}
SLIDER_LIGHT = {
    "slider_groove_height": "4px",
    "radius_slider_groove": 2,
    "color_slider_accent": "#007AFF",
    "color_slider_track": "#D1D1D6",
    "color_slider_handle_bg": "#ffffff",
    "slider_handle_size": "16px",
    "slider_handle_margin": "-6px 0",
    "radius_slider_handle": 8,
    "slider_handle_border": "1px solid rgba(0, 0, 0, 0.05)",
    "color_slider_handle_hover_bg": "#f8f8f8",
    "color_slider_handle_hover_border": "rgba(0, 0, 0, 0.1)",
    "color_slider_handle_pressed_bg": "#f0f0f0",
}


# ----- Neumorphism button (from Glassmorphism.get_neumorphism_button_style) -----

_G = "qlineargradient(x1:0, y1:0, x2:0, y2:1,\n                        "
_M = ",\n                        "
_E = ")"

BTN_NEUMORPHISM_DARK = {
    "color_btn_bg": _G
    + "stop:0 rgba(85, 85, 90, 0.9)"
    + _M
    + "stop:0.5 rgba(75, 75, 80, 0.9)"
    + _M
    + "stop:1 rgba(65, 65, 70, 0.9)"
    + _E,
    "color_btn_border": "rgba(255, 255, 255, 0.15)",
    "radius_btn": 10,
    "btn_padding": "4px 16px",
    "color_btn_text": "rgba(255, 255, 255, 0.95)",
    "btn_font_size": "12px",
    "btn_font_weight": "400",
    "color_btn_hover_bg": _G
    + "stop:0 rgba(95, 95, 100, 0.95)"
    + _M
    + "stop:0.5 rgba(85, 85, 90, 0.95)"
    + _M
    + "stop:1 rgba(75, 75, 80, 0.95)"
    + _E,
    "color_btn_hover_border": "rgba(255, 255, 255, 0.25)",
    "color_btn_focus_border": "rgba(10, 132, 255, 0.78)",
    "color_btn_pressed_bg": _G + "stop:0 rgba(55, 55, 60, 0.9)" + _M + "stop:1 rgba(65, 65, 70, 0.9)" + _E,
    "color_btn_pressed_border": "rgba(255, 255, 255, 0.1)",
    "color_btn_default_bg": _G + "stop:0 rgba(10, 132, 255, 0.8)" + _M + "stop:1 rgba(0, 100, 220, 0.8)" + _E,
    "color_btn_default_border": "rgba(255, 255, 255, 0.15)",
    "color_btn_default_hover_bg": _G + "stop:0 rgba(10, 132, 255, 0.8)" + _M + "stop:1 rgba(0, 100, 220, 0.8)" + _E,
    "color_btn_default_pressed_bg": _G + "stop:0 rgba(10, 132, 255, 0.8)" + _M + "stop:1 rgba(0, 100, 220, 0.8)" + _E,
    "color_btn_default_pressed_border": "rgba(255, 255, 255, 0.15)",
    "color_btn_disabled_bg": "rgba(44, 44, 46, 0.4)",
    "color_btn_disabled_text": "rgba(255, 255, 255, 0.3)",
}
BTN_NEUMORPHISM_LIGHT = {
    "color_btn_bg": _G
    + "stop:0 rgba(255, 255, 255, 0.8)"
    + _M
    + "stop:0.5 rgba(250, 250, 252, 0.8)"
    + _M
    + "stop:1 rgba(240, 240, 245, 0.8)"
    + _E,
    "color_btn_border": "rgba(0, 0, 0, 0.06)",
    "radius_btn": 10,
    "btn_padding": "4px 16px",
    "color_btn_text": "rgba(28, 28, 30, 0.9)",
    "btn_font_size": "12px",
    "btn_font_weight": "400",
    "color_btn_hover_bg": _G + "stop:0 rgba(255, 255, 255, 0.9)" + _M + "stop:1 rgba(245, 245, 250, 0.9)" + _E,
    "color_btn_hover_border": "rgba(0, 0, 0, 0.1)",
    "color_btn_focus_border": "rgba(0, 122, 255, 0.55)",
    "color_btn_pressed_bg": _G + "stop:0 rgba(235, 235, 240, 0.9)" + _M + "stop:1 rgba(245, 245, 250, 0.9)" + _E,
    "color_btn_pressed_border": "rgba(0, 0, 0, 0.12)",
    "color_btn_default_bg": _G + "stop:0 rgba(0, 122, 255, 0.8)" + _M + "stop:1 rgba(0, 100, 220, 0.8)" + _E,
    "color_btn_default_border": "rgba(0, 0, 0, 0.08)",
    "color_btn_default_hover_bg": _G + "stop:0 rgba(0, 122, 255, 0.8)" + _M + "stop:1 rgba(0, 100, 220, 0.8)" + _E,
    "color_btn_default_pressed_bg": _G + "stop:0 rgba(0, 122, 255, 0.8)" + _M + "stop:1 rgba(0, 100, 220, 0.8)" + _E,
    "color_btn_default_pressed_border": "rgba(0, 0, 0, 0.08)",
    "color_btn_disabled_bg": "rgba(242, 242, 247, 0.4)",
    "color_btn_disabled_text": "rgba(60, 60, 67, 0.3)",
}

# ----- Flat action button (from Glassmorphism.get_flat_action_button_style) -----

BTN_FLAT_DARK = {
    "color_btn_bg": "rgba(255,255,255,0.18)",
    "color_btn_border": "rgba(255,255,255,0.22)",
    "radius_btn": 10,
    "btn_padding": "4px 13px",
    "color_btn_text": "rgba(255,255,255,0.85)",
    "btn_font_size": "11px",
    "btn_font_weight": "400",
    "color_btn_hover_bg": "rgba(255,255,255,0.28)",
    "color_btn_hover_border": "rgba(255,255,255,0.22)",
    "color_btn_pressed_bg": "rgba(255,255,255,0.18)",
    "color_btn_pressed_border": "rgba(255,255,255,0.22)",
    "color_btn_disabled_bg": "rgba(255,255,255,0.3)",
    "color_btn_disabled_text": "#C7C7CC",
}
BTN_FLAT_LIGHT = {
    "color_btn_bg": "rgba(255,255,255,0.75)",
    "color_btn_border": "rgba(255,255,255,0.35)",
    "radius_btn": 10,
    "btn_padding": "4px 13px",
    "color_btn_text": "#1D1D1F",
    "btn_font_size": "11px",
    "btn_font_weight": "400",
    "color_btn_hover_bg": "rgba(255,255,255,0.95)",
    "color_btn_hover_border": "rgba(255,255,255,0.35)",
    "color_btn_pressed_bg": "rgba(255,255,255,0.75)",
    "color_btn_pressed_border": "rgba(255,255,255,0.35)",
    "color_btn_disabled_bg": "rgba(255,255,255,0.3)",
    "color_btn_disabled_text": "#C7C7CC",
}

# ----- Delete button (from Glassmorphism.get_action_button_style with is_delete=True) -----

BTN_DELETE_DARK = {
    "color_btn_bg": "rgba(244, 67, 54, 0.15)",
    "color_btn_border": "rgba(244, 67, 54, 0.3)",
    "radius_btn": 4,
    "btn_padding": "2px 4px",
    "color_btn_text": "#ff5252",
    "btn_font_size": "10px",
    "btn_font_weight": "400",
    "color_btn_hover_bg": "rgba(244, 67, 54, 0.25)",
    "color_btn_hover_border": "rgba(244, 67, 54, 0.5)",
    "color_btn_hover_text": "#ff7979",
    "color_btn_pressed_bg": "rgba(244, 67, 54, 0.25)",
    "color_btn_pressed_border": "rgba(244, 67, 54, 0.5)",
    "color_btn_disabled_bg": "rgba(128,128,128,0.08)",
    "color_btn_disabled_text": "rgba(128,128,128,0.4)",
    "color_btn_disabled_border": "rgba(128,128,128,0.15)",
}
BTN_DELETE_LIGHT = {
    "color_btn_bg": "rgba(211, 47, 47, 0.08)",
    "color_btn_border": "rgba(211, 47, 47, 0.25)",
    "radius_btn": 4,
    "btn_padding": "2px 4px",
    "color_btn_text": "#d32f2f",
    "btn_font_size": "10px",
    "btn_font_weight": "400",
    "color_btn_hover_bg": "rgba(211, 47, 47, 0.15)",
    "color_btn_hover_border": "rgba(211, 47, 47, 0.45)",
    "color_btn_hover_text": "#c62828",
    "color_btn_pressed_bg": "rgba(211, 47, 47, 0.15)",
    "color_btn_pressed_border": "rgba(211, 47, 47, 0.45)",
    "color_btn_disabled_bg": "rgba(128,128,128,0.08)",
    "color_btn_disabled_text": "rgba(128,128,128,0.4)",
    "color_btn_disabled_border": "rgba(128,128,128,0.15)",
}

# ----- Action button (from Glassmorphism.get_action_button_style) -----

BTN_ACTION_DARK = {
    "color_btn_bg": "rgba(255,255,255,0.18)",
    "color_btn_border": "rgba(255,255,255,0.22)",
    "radius_btn": 8,
    "btn_padding": "5px 12px",
    "color_btn_text": "rgba(255,255,255,0.85)",
    "btn_font_size": "11px",
    "btn_font_weight": "400",
    "color_btn_hover_bg": "rgba(255,255,255,0.28)",
    "color_btn_hover_text": "rgba(255,255,255,0.95)",
    "color_btn_hover_border": "rgba(255,255,255,0.22)",
    "color_btn_pressed_bg": "rgba(255,255,255,0.18)",
    "color_btn_pressed_border": "rgba(255,255,255,0.22)",
    "color_btn_disabled_bg": "rgba(128,128,128,0.08)",
    "color_btn_disabled_text": "rgba(128,128,128,0.4)",
    "color_btn_disabled_border": "rgba(128,128,128,0.15)",
    "color_btn_checked_bg": "rgba(10,132,255,0.85)",
    "color_btn_checked_text": "white",
    "color_btn_checked_border": "rgba(10,132,255,0.9)",
}
BTN_ACTION_LIGHT = {
    "color_btn_bg": "rgba(255,255,255,0.75)",
    "color_btn_border": "rgba(255,255,255,0.35)",
    "radius_btn": 8,
    "btn_padding": "5px 12px",
    "color_btn_text": "rgba(28,28,30,0.75)",
    "btn_font_size": "11px",
    "btn_font_weight": "400",
    "color_btn_hover_bg": "rgba(255,255,255,0.95)",
    "color_btn_hover_text": "rgba(28,28,30,0.9)",
    "color_btn_hover_border": "rgba(255,255,255,0.35)",
    "color_btn_pressed_bg": "rgba(255,255,255,0.75)",
    "color_btn_pressed_border": "rgba(255,255,255,0.35)",
    "color_btn_disabled_bg": "rgba(128,128,128,0.08)",
    "color_btn_disabled_text": "rgba(128,128,128,0.4)",
    "color_btn_disabled_border": "rgba(128,128,128,0.15)",
    "color_btn_checked_bg": "rgba(10,132,255,0.85)",
    "color_btn_checked_text": "white",
    "color_btn_checked_border": "rgba(10,132,255,0.9)",
}
BTN_ACTION_COMPACT_DARK = dict(
    BTN_ACTION_DARK,
    **{
        "btn_font_size": "10px",
        "btn_padding": "2px 4px",
        "radius_btn": 4,
    },
)
BTN_ACTION_COMPACT_LIGHT = dict(
    BTN_ACTION_LIGHT,
    **{
        "btn_font_size": "10px",
        "btn_padding": "2px 4px",
        "radius_btn": 4,
    },
)

# ----- Neumorphism input (from Glassmorphism.get_neumorphism_input_style) -----

INPUT_NEUMORPHISM_DARK = {
    "color_input_bg": "rgba(38, 38, 42, 0.7)",
    "color_input_border": "rgba(255, 255, 255, 0.1)",
    "radius_input": 6,
    "input_padding": "3px 8px",
    "color_input_text": "rgba(255, 255, 255, 0.9)",
    "input_font_size": "12px",
    "input_font_weight": "400",
    "input_min_height": "24px",
    "color_input_focus_border": "rgba(10, 132, 255, 0.8)",
    "color_input_focus_bg": "rgba(42, 42, 46, 0.85)",
    "color_input_disabled_bg": "rgba(38, 38, 42, 0.3)",
    "color_input_disabled_text": "rgba(255, 255, 255, 0.3)",
    "color_spin_bg": "rgba(38, 38, 42, 0.7)",
    "color_spin_border": "rgba(255, 255, 255, 0.1)",
    "color_spin_text": "rgba(255, 255, 255, 0.9)",
    "color_spin_focus_border": "rgba(10, 132, 255, 0.8)",
    "color_spin_focus_bg": "rgba(42, 42, 46, 0.85)",
    "color_spin_disabled_bg": "rgba(38, 38, 42, 0.3)",
    "color_spin_disabled_text": "rgba(255, 255, 255, 0.3)",
}
INPUT_NEUMORPHISM_LIGHT = {
    "color_input_bg": "rgba(255, 255, 255, 0.7)",
    "color_input_border": "rgba(0, 0, 0, 0.1)",
    "radius_input": 6,
    "input_padding": "3px 8px",
    "color_input_text": "rgba(28, 28, 30, 0.9)",
    "input_font_size": "12px",
    "input_font_weight": "400",
    "input_min_height": "24px",
    "color_input_focus_border": "rgba(0, 122, 255, 0.5)",
    "color_input_focus_bg": "rgba(255, 255, 255, 0.85)",
    "color_input_disabled_bg": "rgba(242, 242, 247, 0.4)",
    "color_input_disabled_text": "rgba(60, 60, 67, 0.3)",
    "color_spin_bg": "rgba(255, 255, 255, 0.7)",
    "color_spin_border": "rgba(0, 0, 0, 0.06)",
    "color_spin_text": "rgba(28, 28, 30, 0.9)",
    "color_spin_focus_border": "rgba(0, 122, 255, 0.5)",
    "color_spin_focus_bg": "rgba(255, 255, 255, 0.85)",
    "color_spin_disabled_bg": "rgba(242, 242, 247, 0.4)",
    "color_spin_disabled_text": "rgba(60, 60, 67, 0.3)",
}

# ----- Neumorphism groupbox (from Glassmorphism.get_neumorphism_groupbox_style) -----

GROUPBOX_NEUMORPHISM_DARK = {
    "color_gb_bg": "rgba(255, 255, 255, 0.05)",
    "color_gb_border": "rgba(255, 255, 255, 0.08)",
    "radius_gb": 12,
    "gb_margin_top": "18px",
    "gb_padding_top": "10px",
    "gb_font_size": "12px",
    "color_gb_text": "rgba(255, 255, 255, 0.9)",
    "gb_title_left": "14px",
    "gb_title_padding": "2px 10px",
    "gb_title_font_size": "11px",
    "color_gb_title_text": "rgba(255, 255, 255, 0.5)",
}
GROUPBOX_NEUMORPHISM_LIGHT = {
    "color_gb_bg": "rgba(0, 0, 0, 0.03)",
    "color_gb_border": "rgba(0, 0, 0, 0.06)",
    "radius_gb": 12,
    "gb_margin_top": "18px",
    "gb_padding_top": "10px",
    "gb_font_size": "12px",
    "color_gb_text": "rgba(28, 28, 30, 0.9)",
    "gb_title_left": "14px",
    "gb_title_padding": "2px 10px",
    "gb_title_font_size": "11px",
    "color_gb_title_text": "rgba(0, 0, 0, 0.5)",
}


# ----- Token accessors -----


def get_button_plain_tokens(theme: str) -> dict:
    return BUTTON_PLAIN_DARK if theme == "dark" else BUTTON_PLAIN_LIGHT


def get_input_plain_tokens(theme: str) -> dict:
    return INPUT_PLAIN_DARK if theme == "dark" else INPUT_PLAIN_LIGHT


def get_scrollbar_tokens(theme: str) -> dict:
    return SCROLLBAR_DARK if theme == "dark" else SCROLLBAR_LIGHT


def get_combobox_tokens(theme: str) -> dict:
    tokens = dict(COMBOBOX_DARK if theme == "dark" else COMBOBOX_LIGHT)
    tokens["color_cb_selection_bg"] = selection_bg_qss(theme)
    tokens["color_cb_selection_text"] = selection_text_qss(theme)
    return tokens


def get_groupbox_plain_tokens(theme: str) -> dict:
    return GROUPBOX_PLAIN_DARK if theme == "dark" else GROUPBOX_PLAIN_LIGHT


def get_slider_tokens(theme: str) -> dict:
    return SLIDER_DARK if theme == "dark" else SLIDER_LIGHT


def get_button_neum_tokens(theme: str) -> dict:
    return BTN_NEUMORPHISM_DARK if theme == "dark" else BTN_NEUMORPHISM_LIGHT


def get_button_flat_tokens(theme: str) -> dict:
    return BTN_FLAT_DARK if theme == "dark" else BTN_FLAT_LIGHT


def get_button_delete_tokens(theme: str) -> dict:
    return BTN_DELETE_DARK if theme == "dark" else BTN_DELETE_LIGHT


def get_button_action_tokens(theme: str) -> dict:
    return BTN_ACTION_DARK if theme == "dark" else BTN_ACTION_LIGHT


def get_button_action_compact_tokens(theme: str) -> dict:
    return BTN_ACTION_COMPACT_DARK if theme == "dark" else BTN_ACTION_COMPACT_LIGHT


def get_input_neum_tokens(theme: str) -> dict:
    return INPUT_NEUMORPHISM_DARK if theme == "dark" else INPUT_NEUMORPHISM_LIGHT


def get_groupbox_neum_tokens(theme: str) -> dict:
    return GROUPBOX_NEUMORPHISM_DARK if theme == "dark" else GROUPBOX_NEUMORPHISM_LIGHT
