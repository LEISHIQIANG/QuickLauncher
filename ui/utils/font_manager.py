"""
字体管理器 - 统一管理全局字体
"""
import os
import sys
import logging

logger = logging.getLogger(__name__)

# 全局字体族名称
GLOBAL_FONT_FAMILY = "Source Han Sans SC"

def get_font_family():
    """获取全局字体族名称"""
    return GLOBAL_FONT_FAMILY

def get_font_css():
    """获取字体的 CSS 样式字符串"""
    return f"font-family: '{GLOBAL_FONT_FAMILY}', sans-serif;"

def get_font_css_with_size(size: int, weight: int = 400):
    """获取带大小和粗细的字体 CSS 样式"""
    return f"font-family: '{GLOBAL_FONT_FAMILY}', sans-serif; font-size: {size}px; font-weight: {weight};"

def get_qfont(pixel_size: int = 14, weight: int = 400):
    """获取带正确 hinting 的 QFont 对象，解决打包后中文字压缩问题"""
    from qt_compat import QFont
    font = QFont(GLOBAL_FONT_FAMILY)
    font.setPixelSize(pixel_size)
    font.setWeight(QFont.Weight.Normal if weight <= 400 else QFont.Weight.Medium)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font
