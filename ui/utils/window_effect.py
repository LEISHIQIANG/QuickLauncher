import ctypes
from ctypes import c_int, c_void_p, Structure, POINTER, byref, sizeof, windll, c_bool
from ctypes.wintypes import DWORD, ULONG, HWND
import sys

BOOL = c_int
HRGN = c_void_p

# Windows 版本缓存
_windows_version_cache = None

def get_windows_version():
    """获取 Windows 版本信息（带缓存）"""
    global _windows_version_cache
    if _windows_version_cache is not None:
        return _windows_version_cache
    
    try:
        version = sys.getwindowsversion()
        build = version.build
        
        if build >= 22000:
            _windows_version_cache = "win11"
        elif build >= 10240:
            _windows_version_cache = "win10"
        else:
            _windows_version_cache = "win7"
    except Exception:
        _windows_version_cache = "win10"
    
    return _windows_version_cache

def is_win11():
    """检测是否为 Windows 11"""
    return get_windows_version() == "win11"

def is_win10():
    """检测是否为 Windows 10"""
    return get_windows_version() == "win10"

class WindowCompositionAttributeData(Structure):
    _fields_ = [
        ("Attribute", DWORD),
        ("Data", c_void_p),
        ("SizeOfData", ULONG),
    ]

class DWM_BLURBEHIND(Structure):
    _fields_ = [
        ("dwFlags", DWORD),
        ("fEnable", c_bool),
        ("hRgnBlur", c_void_p),
        ("fTransitionOnMaximized", c_bool)
    ]

class AccentPolicy(Structure):
    _fields_ = [
        ("AccentState", DWORD),
        ("AccentFlags", DWORD),
        ("GradientColor", DWORD),
        ("AnimationId", DWORD),
    ]

class WindowEffect:
    """Windows 窗口特效工具类 (Acrylic/Blur/Aero)"""
    
    # 状态常量
    ACCENT_DISABLED = 0
    ACCENT_ENABLE_GRADIENT = 1
    ACCENT_ENABLE_TRANSPARENTGRADIENT = 2
    ACCENT_ENABLE_BLURBEHIND = 3          # 传统 Aero Blur
    ACCENT_ENABLE_ACRYLICBLURBEHIND = 4   # Acrylic (Win10 1709+)
    ACCENT_INVALID_STATE = 5
    
    # 组合属性常量
    WCA_ACCENT_POLICY = 19

    DWMWCP_DEFAULT = 0
    DWMWCP_DONOTROUND = 1
    DWMWCP_ROUND = 2
    DWMWCP_ROUNDSMALL = 3
    
    def __init__(self):
        self.user32 = windll.user32
        self.gdi32 = windll.gdi32
        self.dwmapi = windll.dwmapi
        self.SetWindowCompositionAttribute = self.user32.SetWindowCompositionAttribute
        self.SetWindowCompositionAttribute.argtypes = [HWND, POINTER(WindowCompositionAttributeData)]
        self.SetWindowCompositionAttribute.restype = c_int

        try:
            self.user32.IsWindow.argtypes = [HWND]
            self.user32.IsWindow.restype = BOOL
        except Exception:
            pass

        try:
            self.user32.GetDpiForWindow.argtypes = [HWND]
            self.user32.GetDpiForWindow.restype = ctypes.c_uint
        except Exception:
            pass

        try:
            self.gdi32.CreateRoundRectRgn.argtypes = [c_int, c_int, c_int, c_int, c_int, c_int]
            self.gdi32.CreateRoundRectRgn.restype = HRGN
        except Exception:
            pass

        try:
            self.gdi32.DeleteObject.argtypes = [c_void_p]
            self.gdi32.DeleteObject.restype = BOOL
        except Exception:
            pass

        try:
            self.user32.SetWindowRgn.argtypes = [HWND, HRGN, BOOL]
            self.user32.SetWindowRgn.restype = c_int
        except Exception:
            pass

        try:
            self.user32.MonitorFromWindow.argtypes = [HWND, DWORD]
            self.user32.MonitorFromWindow.restype = c_void_p
        except Exception:
            pass

    def is_win11(self):
        """实例方法：检测是否为 Windows 11"""
        return is_win11()

    def is_win10(self):
        """实例方法：检测是否为 Windows 10"""
        return is_win10()

    def _is_window(self, hwnd: int) -> bool:
        try:
            return bool(self.user32.IsWindow(HWND(int(hwnd))))
        except Exception:
            return bool(hwnd)

    def _get_dpi_scale(self, hwnd: int):
        """获取窗口当前的 DPI 缩放比例"""
        try:
            hwnd_val = int(hwnd)
            if not self._is_window(hwnd_val):
                return 1.0
            
            # 1. 尝试 GetDpiForWindow (Win10 1607+)
            dpi = 0
            if hasattr(self.user32, "GetDpiForWindow"):
                dpi = self.user32.GetDpiForWindow(HWND(hwnd_val))
            
            # 2. 如果 GetDpiForWindow 没拿到或者返回 96 (可能是窗口还未完全切换 DPI 上下文)
            # 尝试通过 MonitorFromWindow 获取
            if dpi <= 96:
                h_monitor = self.user32.MonitorFromWindow(HWND(hwnd_val), 2) # MONITOR_DEFAULTTONEAREST
                if h_monitor:
                    try:
                        dpi_x = ctypes.c_uint()
                        dpi_y = ctypes.c_uint()
                        # PROCESS_DPI_AWARE = 0
                        windll.shcore.GetDpiForMonitor(h_monitor, 0, byref(dpi_x), byref(dpi_y))
                        if dpi_x.value > 0:
                            dpi = dpi_x.value
                    except Exception:
                        pass
            
            if dpi > 0:
                return float(dpi) / 96.0
        except Exception:
            pass
        return 1.0

    def set_acrylic(self, hwnd: int, gradient_color: str = None, enable: bool = True, animation_id: int = 0, blur: bool = True):
        """
        设置亚克力/模糊效果
        :param hwnd: 窗口句柄 (int)
        :param gradient_color: 16进制颜色字符串 (RRGGBB 或 AARRGGBB)，如果为 None 则使用默认
        :param enable: 是否启用
        :param blur: 是否启用模糊 (True=Acrylic, False=Transparent)
        """
        policy = AccentPolicy()
        
        if not enable:
            policy.AccentState = self.ACCENT_DISABLED
            policy.AccentFlags = 0
            policy.GradientColor = 0
            policy.AnimationId = 0
        else:
            # 根据 blur 参数选择策略
            if blur:
                policy.AccentState = self.ACCENT_ENABLE_ACRYLICBLURBEHIND
            else:
                policy.AccentState = self.ACCENT_ENABLE_TRANSPARENTGRADIENT
                
            policy.AccentFlags = 2 # 似乎有些标志位，2 比较常用
            
            # 颜色处理 (Windows 需要 AABBGGRR 格式的 DWORD)
            # 输入通常是 RGB 或 ARGB
            # GradientColor: AABBGGRR
            
            if gradient_color:
                # 清洗字符串
                gradient_color = gradient_color.lstrip('#')
                if len(gradient_color) == 6:
                    # RRGGBB -> 默认 Alpha 0xCC (204)
                    r = int(gradient_color[0:2], 16)
                    g = int(gradient_color[2:4], 16)
                    b = int(gradient_color[4:6], 16)
                    a = 10 # 默认很透明
                elif len(gradient_color) == 8:
                    # AARRGGBB
                    # 注意：通常配置里的 hex 是 ARGB，但 windows 可能需要 ABGR?
                    # AccentPolicy 的颜色通常是 AABBGGRR
                    # 假设输入是 AARRGGBB (Qt style)
                    a = int(gradient_color[0:2], 16)
                    r = int(gradient_color[2:4], 16)
                    g = int(gradient_color[4:6], 16)
                    b = int(gradient_color[6:8], 16)
                else:
                    a, r, g, b = 10, 255, 255, 255
                
                # 组合成 AABBGGRR
                col = (a << 24) | (b << 16) | (g << 8) | r
                policy.GradientColor = col
            else:
                # 默认白色，高透明
                policy.GradientColor = (10 << 24) | (255 << 16) | (255 << 8) | 255
                
            policy.AnimationId = animation_id

        # 准备数据结构
        data = WindowCompositionAttributeData()
        data.Attribute = self.WCA_ACCENT_POLICY
        data.SizeOfData = sizeof(policy)
        data.Data = ctypes.cast(byref(policy), c_void_p)
        
        if not self._is_window(hwnd):
            return
        self.SetWindowCompositionAttribute(HWND(int(hwnd)), byref(data))

    def set_round_corners(self, hwnd: int, preference=None, enable=None):
        """设置窗口圆角 (Win11 DWM)"""
        try:
            if not self._is_window(hwnd):
                return
            dwmapi = windll.dwmapi
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            if preference is None:
                if enable is None:
                    preference_val = self.DWMWCP_DEFAULT
                else:
                    preference_val = self.DWMWCP_ROUND if enable else self.DWMWCP_DONOTROUND
            else:
                preference_val = int(preference)

            pref = c_int(preference_val)
            dwmapi.DwmSetWindowAttribute(
                HWND(int(hwnd)), 
                DWORD(DWMWA_WINDOW_CORNER_PREFERENCE), 
                byref(pref),
                sizeof(pref)
            )
        except Exception:
            pass

    def set_window_region(self, hwnd: int, w: int, h: int, r: int, x: int = 0, y: int = 0):
        """设置窗口圆角裁剪区域 (Win10/Win7) - 增强版，彻底消除直角残留

        优化策略：
        1. 使用浮点数精确计算，减少舍入误差
        2. 右边和底边添加额外像素补偿
        3. 圆角半径强制为偶数并适当放大
        4. 使用更大的椭圆直径以获得更平滑的圆角
        """
        try:
            if not self._is_window(hwnd):
                return
            scale = self._get_dpi_scale(hwnd)

            # 使用浮点数精确计算坐标，然后四舍五入
            # 右边和底边额外添加 2 像素补偿，确保完全覆盖窗口边缘
            x1 = int(round(x * scale))
            y1 = int(round(y * scale))
            x2 = int(round((x + w) * scale)) + 2  # +2 确保完全覆盖
            y2 = int(round((y + h) * scale)) + 2  # +2 确保完全覆盖

            # 圆角半径优化：
            # 1. 使用 round 而非 int 截断，保持精度
            # 2. 适当放大圆角半径（+1），使圆角更平滑
            # 3. 确保是偶数，GDI 渲染偶数圆角更平滑
            rr = max(4, int(round(r * scale)) + 1)  # 最小为 4，并额外 +1
            if rr % 2 != 0:
                rr += 1  # 强制偶数

            # 创建圆角区域
            # CreateRoundRectRgn 的最后两个参数是椭圆的宽度和高度（直径）
            # 使用稍大的椭圆直径 (rr * 2 + 2) 以获得更平滑的圆角曲线
            ellipse_diameter = rr * 2 + 2
            hrgn = self.gdi32.CreateRoundRectRgn(x1, y1, x2, y2, ellipse_diameter, ellipse_diameter)
            if not hrgn:
                return

            # 应用窗口区域，redraw=True 立即重绘
            res = self.user32.SetWindowRgn(HWND(int(hwnd)), HRGN(hrgn), BOOL(1))
            if not res:
                # 如果失败，删除区域句柄
                try:
                    self.gdi32.DeleteObject(HRGN(hrgn))
                except Exception:
                    pass
        except Exception:
            pass

    def clear_window_region(self, hwnd: int):
        """清除窗口裁剪区域"""
        try:
            if not self._is_window(hwnd):
                return
            self.user32.SetWindowRgn(HWND(int(hwnd)), HRGN(0), BOOL(1))
        except Exception:
            pass

    def set_aero_blur(self, hwnd: int, enable: bool = True):
        """设置传统 Aero 模糊 (Win7/Win10 早期风格)"""
        policy = AccentPolicy()
        if enable:
            policy.AccentState = self.ACCENT_ENABLE_BLURBEHIND
        else:
            policy.AccentState = self.ACCENT_DISABLED
            
        data = WindowCompositionAttributeData()
        data.Attribute = self.WCA_ACCENT_POLICY
        data.SizeOfData = sizeof(policy)
        data.Data = ctypes.cast(byref(policy), c_void_p)
        
        if not self._is_window(hwnd):
            return
        self.SetWindowCompositionAttribute(HWND(int(hwnd)), byref(data))

    def set_dwm_blur_behind(self, hwnd: int, w: int, h: int, r: int, enable: bool = True, x: int = 0, y: int = 0):
        """
        设置 DWM Blur Behind (Win10/Win7) - 增强版，与 set_window_region 使用完全相同的计算逻辑
        注意：这与 SetWindowCompositionAttribute 不同，是另一种模糊机制

        优化策略：确保与 set_window_region 创建的区域完全一致，避免边缘不对齐
        """
        try:
            if not self._is_window(hwnd):
                return
            dwmapi = windll.dwmapi

            # Constants
            DWM_BB_ENABLE = 0x00000001
            DWM_BB_BLURREGION = 0x00000002

            bb = DWM_BLURBEHIND()
            bb.dwFlags = DWM_BB_ENABLE
            bb.fEnable = enable
            bb.hRgnBlur = None

            if enable and r >= 0:
                bb.dwFlags |= DWM_BB_BLURREGION
                scale = self._get_dpi_scale(hwnd)

                # 使用与 set_window_region 完全相同的坐标计算逻辑
                x1 = int(round(x * scale))
                y1 = int(round(y * scale))
                x2 = int(round((x + w) * scale)) + 2  # +2 补偿
                y2 = int(round((y + h) * scale)) + 2  # +2 补偿

                # 圆角半径：与 set_window_region 保持一致
                rr = max(4, int(round(r * scale)) + 1)
                if rr % 2 != 0:
                    rr += 1

                # 使用相同的椭圆直径
                ellipse_diameter = rr * 2 + 2
                hrgn = self.gdi32.CreateRoundRectRgn(x1, y1, x2, y2, ellipse_diameter, ellipse_diameter)
                bb.hRgnBlur = hrgn

            dwmapi.DwmEnableBlurBehindWindow(HWND(int(hwnd)), byref(bb))

            # Clean up region
            if bb.hRgnBlur:
                self.gdi32.DeleteObject(bb.hRgnBlur)

        except Exception:
            pass

    def apply_unified_round_corners(self, hwnd: int, w: int, h: int, r: int = 12):
        """
        应用统一的圆角效果（自动适配 Win10/Win11）
        
        Win11: 使用 DWM 原生圆角
        Win10: 使用窗口区域裁剪
        
        Args:
            hwnd: 窗口句柄
            w: 窗口宽度
            h: 窗口高度
            r: 圆角半径（默认 12px）
        """
        if is_win11():
            # Win11 使用 DWM 原生圆角
            self.set_round_corners(hwnd, enable=True)
        else:
            # Win10 使用区域裁剪
            self.set_window_region(hwnd, w, h, r)
    
    def apply_unified_blur_effect(self, hwnd: int, gradient_color: str = None, enable: bool = True):
        """
        应用统一的模糊效果（自动适配 Win10/Win11）
        
        Win11: 使用 Acrylic 效果
        Win10: 使用 Aero Blur 效果
        
        Args:
            hwnd: 窗口句柄
            gradient_color: 渐变颜色（带透明度）
            enable: 是否启用
        """
        if is_win11():
            # Win11 优先使用 Acrylic
            self.set_acrylic(hwnd, gradient_color, enable, blur=True)
        else:
            # Win10 使用传统 Aero Blur
            self.set_aero_blur(hwnd, enable)
            if enable and gradient_color:
                # 额外设置透明渐变
                self.set_acrylic(hwnd, gradient_color, enable, blur=False)

    def enable_window_shadow(self, hwnd: int, radius: int = 12):
        """
        为无边框窗口启用原生窗口阴影（自动适配 Win10/Win11）
        
        通过 DwmExtendFrameIntoClientArea 扩展边框来实现阴影效果。
        
        Args:
            hwnd: 窗口句柄
            radius: 圆角半径（默认 12px）
        """
        try:
            if not self._is_window(hwnd):
                return False
            
            dwmapi = windll.dwmapi
            
            # 定义 MARGINS 结构
            class MARGINS(Structure):
                _fields_ = [
                    ("cxLeftWidth", c_int),
                    ("cxRightWidth", c_int),
                    ("cyTopHeight", c_int),
                    ("cyBottomHeight", c_int),
                ]
            
            # 设置边距扩展以启用阴影
            # 使用 -1 可以让整个窗口都扩展到客户区
            margins = MARGINS(-1, -1, -1, -1)
            
            dwmapi.DwmExtendFrameIntoClientArea.argtypes = [HWND, POINTER(MARGINS)]
            dwmapi.DwmExtendFrameIntoClientArea.restype = c_int
            result = dwmapi.DwmExtendFrameIntoClientArea(HWND(int(hwnd)), byref(margins))
            
            if result != 0:
                return False
            
            # Win11 上启用圆角
            if is_win11():
                self.set_round_corners(hwnd, enable=True)

            return True
        except Exception as e:
            return False

    def enable_shadow_for_dialog(self, hwnd: int, radius: int = 12):
        """
        为对话框启用阴影效果（自动适配 Win10/Win11）
        
        此方法专门用于标准对话框，使用更小的边距扩展。
        
        Args:
            hwnd: 窗口句柄
            radius: 圆角半径（默认 12px）
        
        Returns:
            bool: 是否成功启用
        """
        try:
            if not self._is_window(hwnd):
                return False
            
            dwmapi = windll.dwmapi
            
            # 定义 MARGINS 结构
            class MARGINS(Structure):
                _fields_ = [
                    ("cxLeftWidth", c_int),
                    ("cxRightWidth", c_int),
                    ("cyTopHeight", c_int),
                    ("cyBottomHeight", c_int),
                ]
            
            # 使用 1 像素边距来启用阴影而不影响客户区
            margins = MARGINS(1, 1, 1, 1)
            
            dwmapi.DwmExtendFrameIntoClientArea.argtypes = [HWND, POINTER(MARGINS)]
            dwmapi.DwmExtendFrameIntoClientArea.restype = c_int
            result = dwmapi.DwmExtendFrameIntoClientArea(HWND(int(hwnd)), byref(margins))
            
            if result != 0:
                return False
            
            # Win11 上启用圆角
            if is_win11():
                self.set_round_corners(hwnd, enable=True)

            return True
        except Exception as e:
            return False


# 全局共享实例，避免重复创建
_window_effect_instance = None

def get_window_effect() -> WindowEffect:
    """获取共享的 WindowEffect 实例"""
    global _window_effect_instance
    if _window_effect_instance is None:
        _window_effect_instance = WindowEffect()
    return _window_effect_instance


def enable_window_shadow_and_round_corners(widget, radius: int = 12, force_region: bool = False):
    """
    为 Qt 窗口启用阴影和圆角效果的便捷函数

    这是一个高级封装，自动处理 Win10/Win11 的差异：
    - Win11: 使用 DWM 原生圆角 + 阴影
    - Win10: 对于标准带标题栏的窗口，完全跳过（保持系统原生外观）
             对于无边框窗口（force_region=True），使用区域裁剪实现圆角

    Args:
        widget: Qt 窗口对象 (QWidget/QDialog/QMainWindow)
        radius: 圆角半径（默认 12px）
        force_region: 是否强制使用区域裁剪（仅用于无边框窗口）

    Returns:
        bool: 是否成功应用

    Usage:
        from ui.utils.window_effect import enable_window_shadow_and_round_corners

        class MyDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                # ... setup UI ...

            def showEvent(self, event):
                super().showEvent(event)
                enable_window_shadow_and_round_corners(self)
    """
    try:
        # 获取窗口句柄
        hwnd = int(widget.winId())
        if not hwnd:
            return False

        effect = get_window_effect()

        if is_win11():
            # Win11: 启用 DWM 阴影和原生圆角
            shadow_ok = effect.enable_shadow_for_dialog(hwnd, radius)
            return shadow_ok
        else:
            # Win10: 对于标准带标题栏的对话框，完全跳过区域裁剪和阴影效果
            # 因为区域裁剪会与系统窗口边框产生冲突，导致边缘显示不完整
            # 只有当 force_region=True（即无边框窗口）时才应用区域裁剪
            if not force_region:
                # 标准对话框，保持系统原生外观，不做任何修改
                return True

            try:
                # 尝试启用阴影 (DWM extension)
                effect.enable_shadow_for_dialog(hwnd, radius)

                w = widget.width()
                h = widget.height()
                if w > 0 and h > 0:
                    # Win10 优化方案：同时使用 SetWindowRgn 和 DWM Blur Behind
                    # 1. SetWindowRgn 负责精确裁剪窗口形状
                    effect.set_window_region(hwnd, w, h, radius)
                    # 2. DWM Blur Behind 负责模糊效果（使用相同的区域）
                    effect.set_dwm_blur_behind(hwnd, w, h, radius, enable=True)
                    return True
            except Exception:
                pass
            return False
    except Exception:
        return False


def enable_acrylic_for_config_window(widget, theme: str = "dark", blur_amount: int = 30, radius: int = 12):
    """
    为配置窗口启用磨砂玻璃 Acrylic 效果
    
    此函数专门为配置窗口优化，提供适合 UI 的模糊效果参数。
    
    Args:
        widget: Qt 窗口对象
        theme: 主题 ("dark" 或 "light")
        blur_amount: 透明度/模糊程度 (0-255)，默认 30 表示高透明度（更明显的模糊）
        radius: 圆角半径 (默认 12px)，仅 Win10 使用
    
    Returns:
        bool: 是否成功应用
    """
    try:
        hwnd = int(widget.winId())
        if not hwnd:
            return False
        
        effect = get_window_effect()
        
        # Windows Acrylic API 需要 AARRGGBB 格式
        if theme == "dark":
            # 深色主题：深灰色 (#1c1c1e)
            r, g, b = 0x1c, 0x1c, 0x1e
        else:
            # 浅色主题：浅灰色 (#f2f2f7)
            r, g, b = 0xf2, 0xf2, 0xf7
        
        if is_win11():
            # Win11: 保持原有逻辑 (Win11 效果很好)
            # 使用较低的 alpha 值获得更好的磨砂效果
            alpha = max(30, min(blur_amount, 80))
            gradient_color = f"{alpha:02x}{r:02x}{g:02x}{b:02x}"
            
            # Application unified blur (Acrylic)
            effect.apply_unified_blur_effect(hwnd, gradient_color, enable=True)
        else:
            # Win10: 全面优化方案，彻底解决"太透明"和"直角残留"问题
            #
            # 修复策略：
            # 1. 提高背景不透明度（alpha=200），使窗口更实，避免过度透明
            # 2. 同时使用 SetWindowRgn + DWM Blur Behind 双重圆角
            # 3. 使用 Acrylic 半透明着色层提供玻璃质感
            # 4. 确保所有区域计算完全一致，避免边缘错位

            alpha = 200  # 显著提高不透明度（范围 0-255），使背景更实
            gradient_color = f"{alpha:02x}{r:02x}{g:02x}{b:02x}"

            w = widget.width()
            h = widget.height()
            if w > 0 and h > 0:
                # 步骤1: 设置窗口裁剪区域（硬性圆角边界）
                effect.set_window_region(hwnd, w, h, radius)

                # 步骤2: 设置 DWM 模糊区域（与裁剪区域完全一致）
                effect.set_dwm_blur_behind(hwnd, w, h, radius, enable=True)

            # 步骤3: 应用 Acrylic 半透明着色（无额外模糊，避免冲突）
            # blur=False 表示只着色不模糊，模糊效果由 DWM Blur Behind 提供
            effect.set_acrylic(hwnd, gradient_color, enable=True, blur=False)

        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False

def force_activate_window(hwnd: int):
    """
    极度强化版的窗口激活函数 (v2)
    
    综合了：
    1. AttachThreadInput (线程输入挂接)
    2. ShowWindow (恢复显示)
    3. HWND_TOPMOST 瞬时转换 (层级置顶)
    4. 虚拟按键欺骗 (绕过 SetForegroundWindow 限制)
    5. SwitchToThisWindow (系统深度激活)
    """
    if not hwnd:
        return False
        
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        
        # 1. 基础状态恢复
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        else:
            user32.ShowWindow(hwnd, 5)  # SW_SHOW
            
        # 2. 线程上下文准备
        foreground_hwnd = user32.GetForegroundWindow()
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        current_thread = kernel32.GetCurrentThreadId()
        foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None) if foreground_hwnd else 0
        
        # 3. 线程输入挂接 (突破 SetForegroundWindow 限制的关键)
        attached = False
        if foreground_thread and foreground_thread != current_thread:
            attached = bool(user32.AttachThreadInput(foreground_thread, current_thread, True))
            
        try:
            # 4. 暴力切换 Z-Order (瞬时置顶)
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002) # HWND_TOPMOST
            user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040) # HWND_NOTOPMOST
            
            # 5. 调用系统前台切换
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            user32.SetActiveWindow(hwnd)
            
            # 6. 使用深度激活 API
            if hasattr(user32, "SwitchToThisWindow"):
                user32.SwitchToThisWindow(hwnd, True)
            
        finally:
            if attached:
                user32.AttachThreadInput(foreground_thread, current_thread, False)
        
        # 8. 最后确认归位到 Top (非 TopMost)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040) # HWND_TOP
        
        return user32.GetForegroundWindow() == hwnd
    except Exception:
        return False
