"""Extracted from ui.styles.style (W6.3 split)."""


class Colors:
    """
    设计规范颜色常量
    """

    # 系统蓝色
    BLUE = "#007AFF"
    BLUE_LIGHT = "#0A84FF"

    # 系统绿色
    # 系统绿色 (改为青色)
    GREEN = "#30B0C7"
    GREEN_LIGHT = "#40C8E0"

    # 系统红色
    RED = "#FF3B30"
    RED_LIGHT = "#FF453A"

    # 系统灰色
    GRAY = "#8E8E93"
    GRAY2 = "#636366"
    GRAY3 = "#48484A"
    GRAY4 = "#3A3A3C"
    GRAY5 = "#2C2C2E"
    GRAY6 = "#1C1C1E"

    # 深色主题背景
    DARK_BG_PRIMARY = "rgba(28, 28, 30, 0.85)"
    DARK_BG_SECONDARY = "rgba(44, 44, 46, 0.85)"
    DARK_BG_TERTIARY = "rgba(58, 58, 60, 0.85)"
    DARK_TEXT_PRIMARY = "#FFFFFF"
    DARK_TEXT_SECONDARY = "#8E8E93"
    DARK_BORDER = "rgba(255, 255, 255, 0.1)"
    DARK_SEPARATOR = "rgba(255, 255, 255, 0.16)"

    # 浅色主题背景
    LIGHT_BG_PRIMARY = "rgba(242, 242, 247, 0.8)"
    LIGHT_BG_SECONDARY = "rgba(255, 255, 255, 0.8)"
    LIGHT_BG_TERTIARY = "rgba(229, 229, 234, 0.8)"
    LIGHT_TEXT_PRIMARY = "#1C1C1E"
    LIGHT_TEXT_SECONDARY = "#8E8E93"
    LIGHT_BORDER = "rgba(0, 0, 0, 0.08)"
    LIGHT_SEPARATOR = "rgba(60, 60, 67, 0.18)"

    # 通用圆角
    RADIUS_SMALL = 8
    RADIUS_MEDIUM = 10
    RADIUS_LARGE = 12
    RADIUS_XLARGE = 16

    @classmethod
    def get_bg_primary(cls, theme: str) -> str:
        return cls.DARK_BG_PRIMARY if theme == "dark" else cls.LIGHT_BG_PRIMARY

    @classmethod
    def get_bg_secondary(cls, theme: str) -> str:
        return cls.DARK_BG_SECONDARY if theme == "dark" else cls.LIGHT_BG_SECONDARY

    @classmethod
    def get_text_primary(cls, theme: str) -> str:
        return cls.DARK_TEXT_PRIMARY if theme == "dark" else cls.LIGHT_TEXT_PRIMARY

    @classmethod
    def get_text_secondary(cls, theme: str) -> str:
        return cls.DARK_TEXT_SECONDARY if theme == "dark" else cls.LIGHT_TEXT_SECONDARY

    @classmethod
    def get_border(cls, theme: str) -> str:
        return cls.DARK_BORDER if theme == "dark" else cls.LIGHT_BORDER

    @classmethod
    def get_accent(cls, theme: str) -> str:
        return cls.BLUE_LIGHT if theme == "dark" else cls.BLUE

    @classmethod
    def get_selection_bg(cls, theme: str) -> str:
        return "rgba(10, 132, 255, 0.30)" if theme == "dark" else "rgba(0, 122, 255, 0.14)"

    @classmethod
    def get_selection_hover_bg(cls, theme: str) -> str:
        return "rgba(255, 255, 255, 0.08)" if theme == "dark" else "rgba(0, 0, 0, 0.05)"

    @classmethod
    def get_selection_text(cls, theme: str) -> str:
        return "rgba(255, 255, 255, 0.95)" if theme == "dark" else "rgba(28, 28, 30, 0.96)"
