"""Background loading and cache helpers for type(self)."""

import logging
import os
import threading

from qt_compat import (
    QApplication, QImage, QImageReader, QImageIOHandler, QPainter,
    QPainterPath, QPixmap, QRectF, QSize, QtCompat
)

logger = logging.getLogger(__name__)


class PopupBackgroundMixin:
    @staticmethod
    def _load_bg_task(params):
        """后台线程加载背景图片"""
        # 只取前4个参数，忽略后续扩展参数(如圆角半径)
        path, blur_level, target_w, target_h = params[:4]
        
        try:
            # 确保路径存在
            if not os.path.exists(path):
                return None

            # 使用 QImageReader 优化加载
            try:
                reader = QImageReader(path)
                
                # 增加内存限制 (设置为 0 表示不限制)
                if hasattr(reader, 'setAllocationLimit'):
                    reader.setAllocationLimit(0)
                
                # 获取原始尺寸
                if not reader.canRead():
                    logger.error(f"无法读取图片 (canRead=False): {reader.errorString()}")
                    return None
                    
                orig_size = reader.size()
                img_w, img_h = orig_size.width(), orig_size.height()
                
                # 避免除零错误
                if img_w == 0 or img_h == 0:
                    return None
                
                # 计算目标缩放尺寸
                ratio_w = target_w / img_w
                ratio_h = target_h / img_h
                scale = max(ratio_w, ratio_h)
                
                load_scale = scale

                new_w = int(img_w * load_scale)
                new_h = int(img_h * load_scale)
                
                # 设置读取时的缩放尺寸
                # PyQt5 背景图片读取兼容
                scaled_option = None
                if hasattr(QImageReader, 'ImageOption'):
                    scaled_option = QImageReader.ImageOption.ScaledSize
                elif hasattr(QImageIOHandler, 'ImageOption'):
                    scaled_option = QImageIOHandler.ImageOption.ScaledSize
                
                if scaled_option is not None and reader.supportsOption(scaled_option):
                    reader.setScaledSize(QSize(new_w, new_h))
                
                # 读取图片
                image = reader.read()
                if image.isNull():
                    logger.error(f"QImageReader 读取失败: {reader.errorString()}")
                    return None
                    
            except Exception as e:
                logger.warning(f"QImageReader 优化加载失败 ({e})，尝试直接加载")
                # 后备方案：直接加载
                image = QImage(path)
                if image.isNull():
                    return None
                new_w = image.width()
                new_h = image.height()

            # 缩放和处理
            if blur_level > 0:
                # 计算模糊系数 (0-100 -> 1.0-0.05)
                blur_factor = max(0.05, 1.0 - (blur_level * 0.018))
                
                # 计算目标中间尺寸 (基于目标窗口尺寸，而非当前图片尺寸，确保模糊效果一致)
                small_w = max(1, int(target_w * blur_factor))
                small_h = max(1, int(target_h * blur_factor))
                
                # 1. 缩小到中间尺寸 (KeepAspectRatioByExpanding 保证铺满)
                image = image.scaled(small_w, small_h, QtCompat.KeepAspectRatioByExpanding, QtCompat.SmoothTransformation)
                
                # 2. 放大回目标尺寸 (KeepAspectRatioByExpanding 保证铺满)
                image = image.scaled(target_w, target_h, QtCompat.KeepAspectRatioByExpanding, QtCompat.SmoothTransformation)
                
            else:
                # 始终确保图片适配目标窗口 (KeepAspectRatioByExpanding)
                # 无论是加载了原始大图需要缩小，还是小图需要放大，都统一处理
                # 这解决了 fallback 到直接加载大图时未进行缩放导致只截取了中心一小块的问题
                image = image.scaled(target_w, target_h, QtCompat.KeepAspectRatioByExpanding, QtCompat.SmoothTransformation)
            
            # 裁剪中心
            x = (image.width() - target_w) // 2
            y = (image.height() - target_h) // 2
            image = image.copy(x, y, target_w, target_h)
            
            return image
            
        except Exception as e:
            logger.error(f"处理背景图片失败: {e}")
            return None
    def _on_bg_loaded(self, image, params, seq: int):
        """背景图片加载完成回调"""
        try:
            if int(seq) != int(getattr(self, "_bg_loading_seq", 0)):
                return
        except Exception:
            return

        self._is_loading_bg = False

        # 从 params 获取圆角半径 (兼容旧版本 params 长度)
        radius = 8
        if len(params) >= 5:
            radius = params[4]
            
        if image and not image.isNull():
            # 转换为 Pixmap
            raw_pixmap = QPixmap.fromImage(image)
            
            # 预处理：应用圆角裁剪，避免在 paintEvent 中重复裁剪
            # 这显著减少了重绘时的 GPU/CPU 消耗
            rounded_pixmap = QPixmap(raw_pixmap.size())
            rounded_pixmap.fill(QtCompat.transparent)
            
            painter = QPainter(rounded_pixmap)
            painter.setRenderHint(QtCompat.Antialiasing)
            painter.setRenderHint(QtCompat.SmoothPixmapTransform)
            
            path = QPainterPath()
            path.addRoundedRect(QRectF(raw_pixmap.rect()), radius, radius)
            
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, raw_pixmap)
            painter.end()
            
            self._bg_cache = rounded_pixmap
            self._last_bg_params = params
            
            # 更新全局缓存
            type(self)._global_bg_cache[params] = rounded_pixmap
            type(self)._global_bg_cache.move_to_end(params)
            
            # 限制缓存大小
            while len(type(self)._global_bg_cache) > type(self)._MAX_BG_CACHE:
                type(self)._global_bg_cache.popitem(last=False)
                
            logger.info("背景图片异步加载完成并更新 (已预处理圆角)")
            self.update()
        else:
            logger.warning("背景图片异步加载失败或为空")

        try:
            if self._pending_bg_params and self._pending_bg_params != params:
                self._bg_load_timer.start(0)
        except Exception:
            pass
    def _get_cached_bg_pixmap(self) -> QPixmap:
        """获取缓存的背景图片"""
        # 优先使用 bg_mode 判断
        if getattr(self.settings, 'bg_mode', 'theme') != 'image':
            return None

        # 兼容旧字段 custom_bg_path
        path = self.settings.custom_bg_path
        if not path:
            return None
        try:
            if not os.path.exists(path):
                return None
        except Exception:
            return None

        blur_radius = self.settings.bg_blur_radius

        # 获取当前窗口所在屏幕的DPI比例
        dpr = 1.0
        try:
            screen = QApplication.screenAt(self.pos())
            if screen:
                dpr = screen.devicePixelRatio()
        except Exception:
            pass

        params = (
            path,
            blur_radius,
            self.width(),
            self.height(),
            self._get_paint_corner_radius(),
            dpr  # 加入DPI信息
        )
        
        # 1. 检查实例缓存
        if self._bg_cache and self._last_bg_params == params:
            return self._bg_cache

        # 2. 检查全局缓存
        if params in type(self)._global_bg_cache:
            self._bg_cache = type(self)._global_bg_cache[params]
            type(self)._global_bg_cache.move_to_end(params)  # 标记为最近使用
            self._last_bg_params = params
            return self._bg_cache
        
        # 3. 异步加载
        try:
            if self._bg_cache:
                try:
                    last = self._last_bg_params
                    if last and len(last) >= 4 and last[0] == path and int(last[2]) == int(self.width()) and int(last[3]) == int(self.height()):
                        try:
                            if self._pending_bg_params != params or not self._bg_load_timer.isActive():
                                self._pending_bg_params = params
                                self._bg_load_timer.start(120)
                        except Exception:
                            self._pending_bg_params = params
                            self._bg_load_timer.start(120)
                        return self._bg_cache
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if self._pending_bg_params != params or not self._bg_load_timer.isActive():
                self._pending_bg_params = params
                self._bg_load_timer.start(120)
        except Exception:
            pass
        return None
    def _schedule_bg_load(self):
        try:
            bg_mode = getattr(self.settings, 'bg_mode', 'theme')
            if bg_mode != 'image':
                return
            path = getattr(self.settings, "custom_bg_path", "") or ""
            if not path or not os.path.exists(path):
                return
            blur_radius = getattr(self.settings, 'bg_blur_radius', 0)

            # 获取当前屏幕DPI
            dpr = 1.0
            try:
                screen = QApplication.screenAt(self.pos())
                if screen:
                    dpr = screen.devicePixelRatio()
            except Exception:
                pass

            params = (
                path,
                blur_radius,
                self.width(),
                self.height(),
                self._get_paint_corner_radius(),
                dpr
            )
            if self._pending_bg_params != params or not self._bg_load_timer.isActive():
                self._pending_bg_params = params
                self._bg_load_timer.start(120)
        except Exception:
            return
    def _run_bg_load_request(self):
        params = self._pending_bg_params
        if not params:
            return
        if self._is_loading_bg:
            try:
                self._bg_load_timer.start(60)
            except Exception:
                pass
            return

        self._is_loading_bg = True
        self._bg_load_seq += 1
        seq = int(self._bg_load_seq)
        self._bg_loading_seq = seq

        def run_load():
            try:
                image = self._load_bg_task(params)
                if image:
                    self.bg_loaded_signal.emit(image, params, seq)
                else:
                    self.bg_loaded_signal.emit(QImage(), params, seq)
            except Exception as e:
                logger.error(f"异步加载背景失败: {e}")
                self.bg_loaded_signal.emit(QImage(), params, seq)

        t = threading.Thread(target=run_load, name="BgLoaderThread", daemon=True)
        t.start()

    def _release_background_cache(self):
        """Release instance background pixmaps when the popup is hidden."""
        self._bg_cache = None
        self._last_bg_params = None
