"""
图标提取器
"""

import os
import sys
import logging
import ctypes
import time
from collections import OrderedDict
from ctypes import wintypes
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from qt_compat import (
        QPixmap, QImage, QIcon, QPainter, QColor,
        Qt, QSize, QFileIconProvider, QApplication,
        QFileInfo, PYQT_VERSION, QT_LIB
    )
    QT_AVAILABLE = True
    logger.debug(f"icon_extractor: 使用 {QT_LIB}")
except Exception as e:
    QT_AVAILABLE = False
    PYQT_VERSION = 0
    QFileInfo = None
    logger.debug("Qt 兼容层不可用，图标提取将跳过 Qt 路径: %s", e)

# 尝试导入 Win32 模块
HAS_WIN32 = False
try:
    import win32gui
    import win32ui
    import win32con
    import win32api
    from PIL import Image
    HAS_WIN32 = True
except ImportError:
    logger.warning("win32gui/PIL 未安装，图标提取功能受限")


class SHFILEINFO(ctypes.Structure):
    _fields_ = [
        ("hIcon", wintypes.HANDLE),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", ctypes.c_wchar * 260),
        ("szTypeName", ctypes.c_wchar * 80)
    ]

SHGFI_ICON = 0x100
SHGFI_LARGEICON = 0x0


class IconExtractor:
    """
    图标提取工具类 (优化版：LRU缓存 + 直接内存转换)
    """
    _cache = OrderedDict()
    _cache_timestamps = {}
    _MAX_CACHE_SIZE = 130  # Maximum number of icons to cache
    _CACHE_TTL_SECONDS = 30 * 60
    _icon_provider = None
    _qfileinfo_cls = None
    _default_icon_cache = {}
    

    @classmethod
    def _get_cached(cls, cache_key):
        cached = cls._cache.get(cache_key)
        if cached is None:
            cls._cache_timestamps.pop(cache_key, None)
            return None

        timestamp = cls._cache_timestamps.get(cache_key, 0)
        if timestamp and time.time() - timestamp > cls._CACHE_TTL_SECONDS:
            cls._cache.pop(cache_key, None)
            cls._cache_timestamps.pop(cache_key, None)
            return None

        cls._cache.move_to_end(cache_key)
        cls._cache_timestamps[cache_key] = time.time()
        return cached

    @classmethod
    def _remember_cache(cls, cache_key, value):
        cls._cache[cache_key] = value
        cls._cache.move_to_end(cache_key)
        cls._cache_timestamps[cache_key] = time.time()
        while len(cls._cache) > cls._MAX_CACHE_SIZE:
            old_key, _ = cls._cache.popitem(last=False)
            cls._cache_timestamps.pop(old_key, None)

    @classmethod
    def clear_expired_cache(cls):
        now = time.time()
        expired = [
            key for key, timestamp in cls._cache_timestamps.items()
            if timestamp and now - timestamp > cls._CACHE_TTL_SECONDS
        ]
        for key in expired:
            cls._cache.pop(key, None)
            cls._cache_timestamps.pop(key, None)
        return len(expired)

    @classmethod
    def get_cache_stats(cls) -> dict:
        cls.clear_expired_cache()
        return {
            "cache_size": len(cls._cache),
            "default_icon_cache_size": len(cls._default_icon_cache),
            "max_cache_size": cls._MAX_CACHE_SIZE,
            "ttl_seconds": cls._CACHE_TTL_SECONDS,
        }

    @classmethod
    def get_icon_provider(cls):
        if not QT_AVAILABLE:
            return None
        if cls._icon_provider is None:
            cls._icon_provider = QFileIconProvider()
        return cls._icon_provider
    
    @classmethod
    def extract(cls, file_path: str, target_path: str = None, size: int = 24):
        """提取文件图标"""
        if not QT_AVAILABLE:
            return None
        try:
            if QApplication.instance() is None:
                return None
        except Exception:
            return None
            
        if not file_path:
            return cls._create_default_icon(size)
        
        cache_key = f"extract:{file_path}|{size}"
        cached = cls._get_cached(cache_key)
        if cached is not None:
            return cached
        
        pixmap = None

        # shell: 路径使用 PIDL 提取
        for sp in (file_path, target_path):
            if sp and sp.lower().startswith("shell:"):
                pixmap = cls._extract_shell_pidl(sp, size)
                if pixmap and (not hasattr(pixmap, 'isNull') or not pixmap.isNull()):
                    cls._remember_cache(cache_key, pixmap)
                    return pixmap

        # 图片文件直接加载（UWP 应用的 PNG 图标等）
        if file_path and os.path.exists(file_path):
            ext = os.path.splitext(file_path)[1].lower()
            if ext in ('.png', '.jpg', '.jpeg', '.bmp', '.ico'):
                pixmap = cls.from_file(file_path, size=size)
                if pixmap and not pixmap.isNull():
                    cls._remember_cache(cache_key, pixmap)
                    return pixmap

        # 尝试提取
        paths_to_try = []
        if file_path and os.path.exists(file_path):
            paths_to_try.append(file_path)
        if target_path and os.path.exists(target_path) and target_path != file_path:
            paths_to_try.append(target_path)

        for path in paths_to_try:
            # 尝试 Win32 API
            if HAS_WIN32:
                pixmap = cls._extract_win32(path, size)
                if pixmap and not pixmap.isNull():
                    break
            
            # 尝试 Qt 图标提供者
            if not pixmap or pixmap.isNull():
                pixmap = cls._extract_qt(path, size)
                if pixmap and not pixmap.isNull():
                    break
        
        # 回退到默认图标
        if not pixmap or pixmap.isNull():
            pixmap = cls._create_default_icon(size)
        
        # Add to cache
        cls._remember_cache(cache_key, pixmap)
            
        return pixmap
    
    @classmethod
    def _extract_qt(cls, path: str, size: int):
        """使用 Qt 提取图标"""
        if not QT_AVAILABLE:
            return None
            
        try:
            if cls._qfileinfo_cls is None:
                cls._qfileinfo_cls = QFileInfo

            info = cls._qfileinfo_cls(path)
            provider = cls.get_icon_provider()
            if provider:
                icon = provider.icon(info)
                if not icon.isNull():
                    return icon.pixmap(size, size)
        except Exception as e:
            logger.debug(f"Qt 图标提取失败: {e}")
        
        return None
    
    @classmethod
    def _extract_win32(cls, path: str, size: int, return_image: bool = False):
        """使用 Win32 API 提取图标"""
        if (not QT_AVAILABLE) or sys.platform != "win32":
            return None
        
        try:
            # 尝试提取图标
            if HAS_WIN32:
                large, small = win32gui.ExtractIconEx(path, 0)
            else:
                large, small = ([], [])
            
            if large:
                hicon = large[0]
                result = cls._hicon_to_pixmap(hicon, size, return_image)
                
                # 清理
                for ico in large:
                    try:
                        win32gui.DestroyIcon(ico)
                    except:
                        pass
                for ico in small:
                    try:
                        win32gui.DestroyIcon(ico)
                    except:
                        pass
                
                if result:
                    return result
                    
        except Exception as e:
            # 忽略拒绝访问等常见错误，避免刷屏
            if "拒绝访问" not in str(e) and "Access is denied" not in str(e):
                logger.debug(f"ExtractIconEx 失败: {e}")
        
        # 尝试 SHGetFileInfo
        try:
            shfi = SHFILEINFO()
            result = ctypes.windll.shell32.SHGetFileInfoW(
                path, 0, ctypes.byref(shfi),
                ctypes.sizeof(shfi),
                SHGFI_ICON | SHGFI_LARGEICON
            )
            
            if result and shfi.hIcon:
                res = cls._hicon_to_pixmap(shfi.hIcon, size, return_image)
                ctypes.windll.user32.DestroyIcon(shfi.hIcon)
                if res:
                    return res
                    
        except Exception as e:
            logger.debug(f"SHGetFileInfo 失败: {e}")
        
        return None

    @classmethod
    def _extract_shell_pidl(cls, shell_path: str, size: int, return_image: bool = False):
        """通过 SHParseDisplayName + PIDL 从 shell: 路径提取图标"""
        if not QT_AVAILABLE or sys.platform != "win32":
            return None
        try:
            SHParseDisplayName = ctypes.windll.shell32.SHParseDisplayName
            SHParseDisplayName.argtypes = [
                wintypes.LPCWSTR, ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)
            ]
            pidl = ctypes.c_void_p()
            sfgao = ctypes.c_ulong()
            hr = SHParseDisplayName(shell_path, None, ctypes.byref(pidl), 0, ctypes.byref(sfgao))
            if hr != 0 or not pidl.value:
                return None
            try:
                shfi = SHFILEINFO()
                SHGFI_PIDL = 0x8
                # 通过 CFUNCTYPE 创建独立函数指针，避免 64 位 PIDL 指针溢出
                _proto = ctypes.WINFUNCTYPE(
                    ctypes.c_void_p,       # 返回值 DWORD_PTR
                    ctypes.c_void_p,       # pszPath (PIDL pointer)
                    wintypes.DWORD,        # dwFileAttributes
                    ctypes.POINTER(SHFILEINFO),  # psfi
                    wintypes.UINT,         # cbSizeFileInfo
                    wintypes.UINT          # uFlags
                )
                _SHGetFileInfo = _proto(("SHGetFileInfoW", ctypes.windll.shell32))
                result = _SHGetFileInfo(
                    pidl.value, 0, ctypes.byref(shfi), ctypes.sizeof(shfi),
                    SHGFI_ICON | SHGFI_LARGEICON | SHGFI_PIDL
                )
                if result and shfi.hIcon:
                    px = cls._hicon_to_pixmap(shfi.hIcon, size, return_image=return_image)
                    ctypes.windll.user32.DestroyIcon(shfi.hIcon)
                    return px
            finally:
                _free = ctypes.WINFUNCTYPE(None, ctypes.c_void_p)(("CoTaskMemFree", ctypes.windll.ole32))
                _free(pidl.value)
        except Exception as e:
            logger.debug(f"Shell PIDL 图标提取失败: {e}")
        return None

    @classmethod
    def _hicon_to_pixmap(cls, hicon, size: int, return_image: bool = False):
        """将 HICON 转换为 QPixmap 或 QImage"""
        if not QT_AVAILABLE:
            return None
            
        # 确保 hicon 是整数句柄
        if hasattr(hicon, 'value'):
            hicon_handle = hicon.value
        else:
            hicon_handle = hicon
            
        if not hicon_handle:
            return None
            
        # 优先尝试 Qt6 自带方法
        try:
            if hasattr(QImage, 'fromHICON'):
                image = QImage.fromHICON(hicon_handle)
                if not image.isNull():
                    scaled_image = image.scaled(size, size, 
                        Qt.KeepAspectRatio, 
                        Qt.SmoothTransformation)
                    
                    if return_image:
                        return scaled_image
                    return QPixmap.fromImage(scaled_image)
        except Exception as e:
            logger.debug(f"Qt fromHICON 失败: {e}")
        
        if HAS_WIN32:
            try:
                info = win32gui.GetIconInfo(hicon_handle)
                hbmColor = info[4]
                hbmMask = info[3]
                
                if not hbmColor:
                    return None
                
                bmp = win32ui.CreateBitmapFromHandle(hbmColor)
                bmp_info = bmp.GetInfo()
                width = bmp_info['bmWidth']
                height = bmp_info['bmHeight']
                
                hdc = win32gui.GetDC(0)
                hdc_mem = win32ui.CreateDCFromHandle(hdc)
                hdc_mem2 = hdc_mem.CreateCompatibleDC()
                
                old_bmp = hdc_mem2.SelectObject(bmp)
                
                bmp_str = bmp.GetBitmapBits(True)
                
                img = Image.frombuffer('RGBA', (width, height), bmp_str, 'raw', 'BGRA', 0, 1)
                
                hdc_mem2.SelectObject(old_bmp)
                win32gui.DeleteObject(hbmColor)
                if hbmMask:
                    win32gui.DeleteObject(hbmMask)
                win32gui.ReleaseDC(0, hdc)
                
                img = img.resize((size, size), Image.Resampling.LANCZOS)

                from io import BytesIO
                buffer = BytesIO()
                img.save(buffer, format='PNG')
                buffer.seek(0)
                data = buffer.read()
                
                if return_image:
                    image = QImage()
                    image.loadFromData(data)
                    return image
                else:
                    pixmap = QPixmap()
                    pixmap.loadFromData(data)
                    return pixmap
                
            except Exception as e:
                logger.debug(f"HICON 转换失败: {e}")
                return None

        return None
    
    @classmethod
    def _create_default_icon(cls, size: int):
        """创建默认图标"""
        if not QT_AVAILABLE:
            return None

        cached = cls._default_icon_cache.get(size)
        if cached is not None:
            return cached
            
        transparent = Qt.transparent
        nopen = Qt.NoPen
        antialias = QPainter.Antialiasing
        
        pixmap = QPixmap(size, size)
        pixmap.fill(transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(antialias)
        painter.setPen(nopen)
        painter.setBrush(QColor(100, 130, 180))
        margin = size // 8
        painter.drawEllipse(margin, margin, size - margin * 2, size - margin * 2)
        painter.end()

        cls._default_icon_cache[size] = pixmap
        return pixmap
    
    @classmethod
    def get_icon_count(cls, path: str) -> int:
        """获取文件中包含的图标数量"""
        if not path or not os.path.exists(path):
            return 0
            
        try:
            # 1. 尝试使用 PrivateExtractIconsW (更准确)
            # PrivateExtractIconsW(path, 0, 0, 0, None, None, 0, 0) 返回图标数量
            # 但 PrivateExtractIconsW 的行为比较复杂，有时并不直接返回数量
            # 我们可以用 ExtractIconExW 来获取数量
            
            # 2. 使用 ExtractIconExW
            # UINT ExtractIconExW(LPCWSTR lpszFile, int nIconIndex, HICON *phiconLarge, HICON *phiconSmall, UINT nIcons);
            # 如果 nIconIndex = -1，phiconLarge 和 phiconSmall 为 NULL，则返回图标数量
            
            cnt = ctypes.windll.shell32.ExtractIconExW(path, -1, None, None, 0)
            if cnt > 0:
                return cnt
                
        except Exception as e:
            logger.debug(f"获取图标数量失败: {e}")
            
        return 0

    @classmethod
    def _extract_from_resource(cls, path: str, index: int, size: int, return_image: bool = False):
        """从资源文件提取图标 (path,index)"""
        try:
            # PrivateExtractIconsW 声明
            # UINT PrivateExtractIconsW(LPCWSTR szFileName, int nIconIndex, int cxIcon, int cyIcon, HICON *phicon, UINT *piconid, UINT nIcons, UINT flags);
            
            phicon = wintypes.HICON()
            piconid = wintypes.UINT()
            
            ret = ctypes.windll.user32.PrivateExtractIconsW(
                path, index, size, size,
                ctypes.byref(phicon), ctypes.byref(piconid), 1, 0
            )
            
            if ret > 0 and phicon:
                result = cls._hicon_to_pixmap(phicon, size, return_image)
                ctypes.windll.user32.DestroyIcon(phicon)
                return result
                
        except Exception as e:
            logger.debug(f"资源图标提取失败 ({path},{index}): {e}")
            
        # 2. 回退到 ExtractIconW (Shell32)
        try:
            # ExtractIconW: 
            # -1: 返回图标总数
            # 负数 (非-1): 资源 ID
            # 正数: 顺序索引
            hIcon = ctypes.windll.shell32.ExtractIconW(0, path, index)
            # ExtractIconW 返回 0 表示没有图标，1 表示文件存在但没图标（有些文档这么说），或者 >1 是句柄
            if hIcon and hIcon > 1:
                result = cls._hicon_to_pixmap(hIcon, size, return_image)
                ctypes.windll.user32.DestroyIcon(hIcon)
                if result:
                    return result
        except Exception as e:
            logger.debug(f"ExtractIconW 提取失败 ({path},{index}): {e}")

        return None

    @classmethod
    def from_file(cls, icon_path: str, size: int = 24, return_image: bool = False):
        """从图标文件加载"""
        if not QT_AVAILABLE:
            return None
            
        if not icon_path:
            return None

        cache_key = f"from_file:{icon_path}|{size}|{1 if return_image else 0}"
        cached = cls._get_cached(cache_key)
        if cached is not None:
            return cached
            
        # 检查 resource syntax: path,index
        if ',' in icon_path:
            parts = icon_path.split(',')
            if len(parts) >= 2:
                # 处理像 "C:\Path\To\File.dll, 1" 这样的情况
                path_part = ",".join(parts[:-1]).strip()
                index_part = parts[-1].strip()
                
                # 如果最后一部分是数字，则认为是索引
                if index_part.lstrip('-').isdigit():
                    result = cls._extract_from_resource(path_part, int(index_part), size, return_image)
                    if result is not None and (not hasattr(result, "isNull") or not result.isNull()):
                        cls._remember_cache(cache_key, result)
                    return result
        
        if not os.path.exists(icon_path):
            return None
        
        try:
            ext = os.path.splitext(icon_path)[1].lower()
            
            if ext == '.ico':
                icon = QIcon(icon_path)
                if not icon.isNull():
                    # QIcon 无法直接转 QImage (需要 pixmap -> image)
                    pixmap = icon.pixmap(size, size)
                    result = pixmap.toImage() if return_image else pixmap
                    cls._remember_cache(cache_key, result)
                    return result
            elif ext in ('.png', '.jpg', '.jpeg', '.bmp'):
                if return_image:
                    image = QImage(icon_path)
                    if not image.isNull():
                        result = image.scaled(size, size, 
                            Qt.KeepAspectRatio, 
                            Qt.SmoothTransformation)
                        cls._remember_cache(cache_key, result)
                        return result
                else:
                    pixmap = QPixmap(icon_path)
                    if not pixmap.isNull():
                        result = pixmap.scaled(size, size, 
                            Qt.KeepAspectRatio, 
                            Qt.SmoothTransformation)
                        cls._remember_cache(cache_key, result)
                        return result
            elif ext == '.exe':
                result = cls._extract_win32(icon_path, size, return_image)
                if result is not None and (not hasattr(result, "isNull") or not result.isNull()):
                    cls._remember_cache(cache_key, result)
                return result
                
        except Exception as e:
            logger.debug(f"加载图标文件失败: {e}")
        
        return None
    
    @staticmethod
    def invert_pixmap(pixmap):
        """反转 pixmap 的 RGB（保持 alpha）"""
        if not QT_AVAILABLE or not pixmap or pixmap.isNull():
            return pixmap
        image = pixmap.toImage()
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = image.pixelColor(x, y)
                inverted = QColor(
                    255 - pixel.red(),
                    255 - pixel.green(),
                    255 - pixel.blue(),
                    pixel.alpha()
                )
                image.setPixelColor(x, y, inverted)
        return QPixmap.fromImage(image)

    @staticmethod
    def invert_image(image):
        """反转 QImage 的 RGB（保持 alpha）— 线程安全版本"""
        if not QT_AVAILABLE or not image or image.isNull():
            return image
        result = image.copy()
        for y in range(result.height()):
            for x in range(result.width()):
                pixel = result.pixelColor(x, y)
                inverted = QColor(
                    255 - pixel.red(),
                    255 - pixel.green(),
                    255 - pixel.blue(),
                    pixel.alpha()
                )
                result.setPixelColor(x, y, inverted)
        return result

    @classmethod
    def clear_cache(cls):
        """清除缓存"""
        cls._cache.clear()
        cls._cache_timestamps.clear()
        cls._icon_provider = None
        cls._qfileinfo_cls = None
        cls._default_icon_cache.clear()


def should_invert_icon(item, current_theme: str) -> bool:
    """判断图标是否需要反转"""
    if not getattr(item, 'icon_invert_with_theme', False):
        return False
    set_theme = getattr(item, 'icon_invert_theme_when_set', '')
    if not set_theme:
        return False
    if getattr(item, 'icon_invert_current', False):
        return current_theme == set_theme
    else:
        return current_theme != set_theme


def get_icon_dir() -> str:
    """获取图标存储目录"""
    # 避免循环引用，这里局部导入
    from .data_manager import DataManager
    data_manager = DataManager()
    return str(data_manager.icons_dir)
