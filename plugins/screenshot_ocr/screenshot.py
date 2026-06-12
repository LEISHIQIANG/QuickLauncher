import os
import tempfile
import time

try:
    import win32gui
except ImportError:
    import ctypes
    from ctypes import wintypes

    class _Win32GuiFallback:
        """Small pywin32-compatible subset used by the screenshot selector."""

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def __init__(self):
            self.user32 = ctypes.windll.user32
            self.user32.EnumWindows.argtypes = [self.WNDENUMPROC, wintypes.LPARAM]
            self.user32.EnumWindows.restype = wintypes.BOOL
            self.user32.EnumChildWindows.argtypes = [wintypes.HWND, self.WNDENUMPROC, wintypes.LPARAM]
            self.user32.EnumChildWindows.restype = wintypes.BOOL
            self.user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            self.user32.GetWindowRect.restype = wintypes.BOOL
            self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
            self.user32.IsWindowVisible.restype = wintypes.BOOL

        def IsWindowVisible(self, hwnd):
            return bool(self.user32.IsWindowVisible(wintypes.HWND(hwnd)))

        def GetWindowRect(self, hwnd):
            rect = wintypes.RECT()
            if not self.user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
                raise OSError("GetWindowRect failed")
            return rect.left, rect.top, rect.right, rect.bottom

        def EnumWindows(self, callback, lParam):
            proc = self.WNDENUMPROC(lambda hwnd, param: self._callback_result(callback, hwnd, param))
            return bool(self.user32.EnumWindows(proc, lParam or 0))

        def EnumChildWindows(self, hwnd, callback, lParam):
            proc = self.WNDENUMPROC(lambda child_hwnd, param: self._callback_result(callback, child_hwnd, param))
            return bool(self.user32.EnumChildWindows(wintypes.HWND(hwnd), proc, lParam or 0))

        @staticmethod
        def _callback_result(callback, hwnd, lParam):
            try:
                return 1 if callback(int(hwnd), lParam) else 0
            except Exception:
                return 0

    win32gui = _Win32GuiFallback()
import wx


class ScreenshotFrame(wx.Frame):
    """轻量级极简截图窗口，支持拖拽创建、智能窗口元素自动探测、二次边缘缩放与拖拽移动（支持多屏幕独立管理）"""

    def __init__(self, display_idx, on_capture_callback, active_callback=None, is_active_callback=None):
        super().__init__(None, style=wx.FRAME_NO_TASKBAR | wx.STAY_ON_TOP)

        self.display_idx = display_idx
        self.on_capture_callback = on_capture_callback
        self.active_callback = active_callback
        self.is_active_callback = is_active_callback

        # 获取当前显示器的几何尺寸与坐标
        display = wx.Display(display_idx)
        geometry = display.GetGeometry()
        self.rect_full = geometry
        self.SetSize(geometry.GetSize())
        self.SetPosition(geometry.GetPosition())

        # 动态获取当前屏幕的 DPI 缩放比例
        try:
            self.scale_factor = display.GetScaleFactor()
        except AttributeError:
            self.scale_factor = 1.0

        # 仅捕获当前显示器的屏幕图像
        screen_dc = wx.ScreenDC()
        self.original_bitmap = wx.Bitmap(geometry.width, geometry.height)
        mem_dc = wx.MemoryDC(self.original_bitmap)
        mem_dc.Blit(0, 0, geometry.width, geometry.height, screen_dc, geometry.x, geometry.y)
        mem_dc.SelectObject(wx.NullBitmap)

        # 生成本显示屏的黑色半透明蒙版背景
        self.dark_mask_bitmap = wx.Bitmap(geometry.width, geometry.height)
        mem_dc = wx.MemoryDC(self.dark_mask_bitmap)
        mem_dc.DrawBitmap(self.original_bitmap, 0, 0)

        gc = wx.GraphicsContext.Create(mem_dc)
        if gc:
            # 使用黑色半透明遮罩，保持良好的对比度
            gc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 130)))
            gc.DrawRectangle(0, 0, geometry.width, geometry.height)
        mem_dc.SelectObject(wx.NullBitmap)

        self.start_pos = None
        self.end_pos = None
        self.is_dragging = False
        self.show_buttons = False

        # 智能元素自动识别变量
        self.auto_rect = None
        self.display_auto_rect = None
        self.auto_anim_start_rect = None
        self.auto_anim_target_rect = None
        self.auto_anim_started_at = 0.0
        self.auto_anim_duration = 0.08
        self.auto_anim_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_auto_rect_timer, self.auto_anim_timer)
        self.pending_auto_rect = None
        self.window_rects = []
        self._init_window_rects()

        # 拖拽相关状态
        self.hover_handle = None
        self.drag_mode = None
        self.drag_start_pos = None
        self.drag_start_rect = None
        self.click_start_pos = None

        # 按钮矩形定义
        self.confirm_rect = wx.Rect(0, 0, 0, 0)
        self.cancel_rect = wx.Rect(0, 0, 0, 0)

        # 使用 Panel 并启用双缓冲
        self.panel = wx.Panel(self)
        self.panel.SetBackgroundStyle(wx.BG_STYLE_PAINT)

        self.panel.Bind(wx.EVT_PAINT, self.on_paint)
        self.panel.Bind(wx.EVT_LEFT_DOWN, self.on_left_down)
        self.panel.Bind(wx.EVT_MOTION, self.on_motion)
        self.panel.Bind(wx.EVT_LEFT_UP, self.on_left_up)
        self.panel.Bind(wx.EVT_RIGHT_DOWN, self.on_right_down)
        self.panel.Bind(wx.EVT_LEFT_DCLICK, self.on_double_click)
        self.panel.Bind(wx.EVT_KEY_DOWN, self.on_key_down)
        self.panel.Bind(wx.EVT_ENTER_WINDOW, self.on_enter_window)

        self.ShowFullScreen(True)
        self.SetCursor(wx.Cursor(wx.CURSOR_CROSS))
        self.panel.SetFocus()

    def on_enter_window(self, event):
        self.activate_display()
        event.Skip()

    def activate_display(self):
        if self.active_callback:
            self.active_callback(self.display_idx)

    def is_interaction_active(self):
        if not self.is_active_callback:
            return True
        try:
            return bool(self.is_active_callback(self.display_idx))
        except Exception:
            return True

    def set_interaction_active(self, active):
        if active:
            self.panel.Refresh()
            return
        self.clear_interaction_state()

    def clear_interaction_state(self):
        self.start_pos = None
        self.end_pos = None
        self.is_dragging = False
        self.show_buttons = False
        self.pending_auto_rect = None
        self.hover_handle = None
        self.drag_mode = None
        self.drag_start_pos = None
        self.drag_start_rect = None
        self.click_start_pos = None
        self.set_auto_rect(None)
        if self.panel.HasCapture():
            try:
                self.panel.ReleaseMouse()
            except Exception:
                pass
        self.panel.Refresh()

    def _rect_copy(self, rect):
        return wx.Rect(rect.x, rect.y, rect.width, rect.height) if rect else None

    def _rect_same(self, a, b):
        if a is None or b is None:
            return a is None and b is None
        return a.x == b.x and a.y == b.y and a.width == b.width and a.height == b.height

    def set_auto_rect(self, rect):
        next_rect = self._rect_copy(rect)
        if self._rect_same(self.auto_rect, next_rect):
            return

        current_rect = self._rect_copy(self.display_auto_rect or self.auto_rect)
        self.auto_rect = next_rect

        if next_rect is None or current_rect is None:
            self.display_auto_rect = self._rect_copy(next_rect)
            self.auto_anim_start_rect = None
            self.auto_anim_target_rect = None
            if self.auto_anim_timer.IsRunning():
                self.auto_anim_timer.Stop()
            self.panel.Refresh()
            return

        self.auto_anim_start_rect = current_rect
        self.auto_anim_target_rect = self._rect_copy(next_rect)
        self.auto_anim_started_at = time.time()
        if not self.auto_anim_timer.IsRunning():
            self.auto_anim_timer.Start(12)

    def on_auto_rect_timer(self, event):
        if not self.auto_anim_start_rect or not self.auto_anim_target_rect:
            if self.auto_anim_timer.IsRunning():
                self.auto_anim_timer.Stop()
            return

        t = (time.time() - self.auto_anim_started_at) / max(0.001, self.auto_anim_duration)
        if t >= 1.0:
            self.display_auto_rect = self._rect_copy(self.auto_anim_target_rect)
            self.auto_anim_start_rect = None
            self.auto_anim_target_rect = None
            self.auto_anim_timer.Stop()
            self.panel.Refresh()
            return

        # Ease-out interpolation keeps the transition brief without feeling abrupt.
        t = 1 - (1 - t) * (1 - t)
        start = self.auto_anim_start_rect
        target = self.auto_anim_target_rect
        self.display_auto_rect = wx.Rect(
            int(start.x + (target.x - start.x) * t),
            int(start.y + (target.y - start.y) * t),
            int(start.width + (target.width - start.width) * t),
            int(start.height + (target.height - start.height) * t),
        )
        self.panel.Refresh()

    def _init_window_rects(self):
        """收集当前显示器屏幕范围内的所有可见窗口及其控件，优化元素高亮检测"""
        my_hwnd = self.GetHandle()
        m_left = self.rect_full.x
        m_top = self.rect_full.y
        m_right = self.rect_full.x + self.rect_full.width
        m_bottom = self.rect_full.y + self.rect_full.height

        def enum_child_proc(hwnd, lParam):
            if win32gui.IsWindowVisible(hwnd):
                try:
                    rect = win32gui.GetWindowRect(hwnd)
                    left, top, right, bottom = rect
                    # 仅保留与当前显示器相交的子控件，忽略极小控件
                    if not (right <= m_left or left >= m_right or bottom <= m_top or top >= m_bottom):
                        w = right - left
                        h = bottom - top
                        if w > 4 and h > 4:
                            self.window_rects.append((hwnd, wx.Rect(left, top, w, h)))
                except Exception:
                    pass
            return True

        def enum_window_proc(hwnd, lParam):
            # 排除当前截图窗口本身
            if hwnd == my_hwnd:
                return True
            if win32gui.IsWindowVisible(hwnd):
                try:
                    rect = win32gui.GetWindowRect(hwnd)
                    left, top, right, bottom = rect
                    # 仅保留与当前显示器相交的窗口
                    if not (right <= m_left or left >= m_right or bottom <= m_top or top >= m_bottom):
                        w = right - left
                        h = bottom - top
                        if w > 4 and h > 4:
                            self.window_rects.append((hwnd, wx.Rect(left, top, w, h)))
                            # 递归枚举子元素
                            win32gui.EnumChildWindows(hwnd, enum_child_proc, None)
                except Exception:
                    pass
            return True

        try:
            win32gui.EnumWindows(enum_window_proc, None)
        except Exception as e:
            print(f"Failed to enumerate windows on screen {self.display_idx}: {e}")

    def find_smallest_containing_rect(self, screen_pt):
        """寻找包含当前鼠标位置的最小可见窗口/元素矩形（即最底层的叶子节点控件）"""
        smallest_rect = None
        smallest_area = float("inf")

        for hwnd, rect in self.window_rects:
            if rect.Contains(screen_pt):
                area = rect.width * rect.height
                if area < smallest_area:
                    smallest_area = area
                    smallest_rect = rect
        return smallest_rect

    def get_hover_handle(self, p):
        """根据坐标 p 判定鼠标悬停的控制柄位置"""
        if not self.start_pos or not self.end_pos or self.is_dragging:
            return None

        x = min(self.start_pos.x, self.end_pos.x)
        y = min(self.start_pos.y, self.end_pos.y)
        w = abs(self.start_pos.x - self.end_pos.x)
        h = abs(self.start_pos.y - self.end_pos.y)

        tol = max(8, int(8 * self.scale_factor))  # 容错半径（像素）

        near_left = abs(p.x - x) <= tol
        near_right = abs(p.x - (x + w)) <= tol
        near_top = abs(p.y - y) <= tol
        near_bottom = abs(p.y - (y + h)) <= tol

        in_x_range = x - tol <= p.x <= x + w + tol
        in_y_range = y - tol <= p.y <= y + h + tol

        # 1. 优先判定四个角
        if near_left and near_top:
            return "TL"
        if near_right and near_top:
            return "TR"
        if near_left and near_bottom:
            return "BL"
        if near_right and near_bottom:
            return "BR"

        # 2. 判定四条边
        if near_top and in_x_range:
            return "T"
        if near_bottom and in_x_range:
            return "B"
        if near_left and in_y_range:
            return "L"
        if near_right and in_y_range:
            return "R"

        # 3. 判定内部移动
        if x < p.x < x + w and y < p.y < y + h:
            # 如果确认/取消按钮正在显示，且鼠标在按钮上，不做移动拦截
            if self.show_buttons:
                if self.confirm_rect.Contains(p) or self.cancel_rect.Contains(p):
                    return None
            return "MOVE"

        return None

    def update_cursor(self, handle):
        """根据控制柄状态设置相应的鼠标指针形状"""
        if handle in ["TL", "BR"]:
            self.SetCursor(wx.Cursor(wx.CURSOR_SIZENWSE))
        elif handle in ["TR", "BL"]:
            self.SetCursor(wx.Cursor(wx.CURSOR_SIZENESW))
        elif handle in ["T", "B"]:
            self.SetCursor(wx.Cursor(wx.CURSOR_SIZENS))
        elif handle in ["L", "R"]:
            self.SetCursor(wx.Cursor(wx.CURSOR_SIZEWE))
        elif handle == "MOVE":
            self.SetCursor(wx.Cursor(wx.CURSOR_SIZING))
        else:
            self.SetCursor(wx.Cursor(wx.CURSOR_CROSS))

    def on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self.panel)
        dc.Clear()

        w, h = self.rect_full.width, self.rect_full.height

        # 1. 绘制当前显示器变暗的背景
        dc.DrawBitmap(self.dark_mask_bitmap, 0, 0)

        # 2. 如果存在自动识别到的窗口且没有激活的拉框选区，高亮绘制该窗口区域
        active = self.is_interaction_active()
        auto_draw_rect = self.display_auto_rect or self.auto_rect
        if active and auto_draw_rect and not self.start_pos:
            ax, ay, aw, ah = auto_draw_rect.x, auto_draw_rect.y, auto_draw_rect.width, auto_draw_rect.height
            if aw > 0 and ah > 0:
                try:
                    sub_bitmap = self.original_bitmap.GetSubBitmap(auto_draw_rect)
                    dc.DrawBitmap(sub_bitmap, ax, ay)
                except Exception:
                    pass

                # 绘制智能框双色虚线边框
                pen_black_width = max(2, int(2 * self.scale_factor))
                pen_black = wx.Pen(wx.Colour(0, 0, 0), pen_black_width, wx.PENSTYLE_SOLID)
                dc.SetPen(pen_black)
                dc.SetBrush(wx.TRANSPARENT_BRUSH)
                dc.DrawRectangle(ax, ay, aw, ah)

                pen_white_width = max(1, int(1 * self.scale_factor))
                pen_white = wx.Pen(wx.Colour(255, 255, 255), pen_white_width, wx.PENSTYLE_USER_DASH)
                dash_len = max(2, int(4 * self.scale_factor))
                pen_white.SetDashes([dash_len, dash_len])
                dc.SetPen(pen_white)
                dc.DrawRectangle(ax, ay, aw, ah)

        # 3. 如果有确定的选区，高亮绘制并加边框
        if active and self.start_pos and self.end_pos:
            x = min(self.start_pos.x, self.end_pos.x)
            y = min(self.start_pos.y, self.end_pos.y)
            sw = abs(self.start_pos.x - self.end_pos.x)
            sh = abs(self.start_pos.y - self.end_pos.y)

            if sw > 0 and sh > 0:
                rect = wx.Rect(x, y, sw, sh)
                try:
                    sub_bitmap = self.original_bitmap.GetSubBitmap(rect)
                    dc.DrawBitmap(sub_bitmap, x, y)
                except Exception:
                    pass

                # 绘制选择框双色虚线边框
                pen_black_width = max(2, int(2 * self.scale_factor))
                pen_black = wx.Pen(wx.Colour(0, 0, 0), pen_black_width, wx.PENSTYLE_SOLID)
                dc.SetPen(pen_black)
                dc.SetBrush(wx.TRANSPARENT_BRUSH)
                dc.DrawRectangle(x, y, sw, sh)

                pen_white_width = max(1, int(1 * self.scale_factor))
                pen_white = wx.Pen(wx.Colour(255, 255, 255), pen_white_width, wx.PENSTYLE_USER_DASH)
                dash_len = max(2, int(4 * self.scale_factor))
                pen_white.SetDashes([dash_len, dash_len])
                dc.SetPen(pen_white)
                dc.DrawRectangle(x, y, sw, sh)

                # 绘制大小文本标签（极简黑底白字）
                font_size = max(8, int(9 * self.scale_factor))
                dc.SetFont(wx.Font(font_size, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
                dc.SetTextForeground(wx.Colour(255, 255, 255))
                dc.SetTextBackground(wx.Colour(0, 0, 0))
                dc.SetBackgroundMode(wx.SOLID)
                size_text = f" {sw} x {sh} "

                text_y_offset = max(10, int(20 * self.scale_factor))
                text_y = y - text_y_offset if y - text_y_offset > 0 else y + max(3, int(5 * self.scale_factor))
                dc.DrawText(size_text, x, text_y)

                # 绘制 8 个拖拽调整控制手柄锚点（白心黑边小圆点）
                if self.show_buttons:
                    handle_color = wx.Colour(255, 255, 255)
                    handle_border_width = max(1, int(1 * self.scale_factor))
                    handle_border = wx.Pen(wx.Colour(0, 0, 0), handle_border_width)
                    dc.SetPen(handle_border)
                    dc.SetBrush(wx.Brush(handle_color))

                    hs_radius = max(3, int(3 * self.scale_factor))

                    points = [
                        (x, y),  # 左上
                        (x + sw // 2, y),  # 中上
                        (x + sw, y),  # 右上
                        (x, y + sh // 2),  # 左中
                        (x + sw, y + sh // 2),  # 右中
                        (x, y + sh),  # 左下
                        (x + sw // 2, y + sh),  # 中下
                        (x + sw, y + sh),  # 右下
                    ]
                    for px, py in points:
                        dc.DrawCircle(px, py, hs_radius)

                # 4. 绘制操作按钮 (极简高对比黑白按钮)
                if self.show_buttons:
                    btn_w = int(80 * self.scale_factor)
                    btn_h = int(28 * self.scale_factor)
                    gap = int(8 * self.scale_factor)

                    btn_y = y + sh + gap
                    if btn_y + btn_h > h:
                        btn_y = y + sh - btn_h - gap

                    btn_x_confirm = x + sw - btn_w
                    btn_x_cancel = btn_x_confirm - btn_w - gap

                    if btn_x_confirm + btn_w > w:
                        btn_x_confirm = w - btn_w
                        btn_x_cancel = btn_x_confirm - btn_w - gap
                    if btn_x_cancel < 0:
                        btn_x_cancel = 0
                        btn_x_confirm = btn_x_cancel + btn_w + gap

                    self.confirm_rect = wx.Rect(btn_x_confirm, btn_y, btn_w, btn_h)
                    self.cancel_rect = wx.Rect(btn_x_cancel, btn_y, btn_w, btn_h)

                    # 确认按钮 (黑底白字)
                    button_border_width = max(1, int(1 * self.scale_factor))
                    dc.SetPen(wx.Pen(wx.Colour(0, 0, 0), button_border_width))
                    dc.SetBrush(wx.Brush(wx.Colour(0, 0, 0)))
                    dc.DrawRoundedRectangle(self.confirm_rect, max(1, int(2 * self.scale_factor)))

                    # 取消按钮 (白底灰字，细灰边框)
                    dc.SetPen(wx.Pen(wx.Colour(180, 180, 180), button_border_width))
                    dc.SetBrush(wx.Brush(wx.Colour(255, 255, 255)))
                    dc.DrawRoundedRectangle(self.cancel_rect, max(1, int(2 * self.scale_factor)))

                    # 绘制文字
                    dc.SetBackgroundMode(wx.TRANSPARENT)
                    btn_font_size = max(8, int(9 * self.scale_factor))
                    dc.SetFont(wx.Font(btn_font_size, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))

                    dc.SetTextForeground(wx.Colour(255, 255, 255))
                    dc.DrawLabel("✔ 确定", self.confirm_rect, wx.ALIGN_CENTER)

                    dc.SetTextForeground(wx.Colour(120, 120, 120))
                    dc.DrawLabel("✖ 取消", self.cancel_rect, wx.ALIGN_CENTER)

    def on_left_down(self, event):
        self.activate_display()
        pos = event.GetPosition()
        self.click_start_pos = pos

        # 1. 优先检测确认/取消按钮点击
        if self.show_buttons:
            if self.confirm_rect.Contains(pos):
                self.confirm_capture()
                return
            elif self.cancel_rect.Contains(pos):
                self.cancel_capture()
                return

        # If an auto-detected element is highlighted, defer selecting it until
        # mouse-up. Do not create a temporary 0-sized manual selection here;
        # that causes a visible dashed-frame flash on simple clicks.
        if self.auto_rect and not self.start_pos and not self.end_pos:
            self.pending_auto_rect = wx.Rect(self.auto_rect)
            self.drag_mode = "AUTO_CLICK"
            self.is_dragging = True
            self.show_buttons = False
            if not self.panel.HasCapture():
                self.panel.CaptureMouse()
            return

        # 2. 判断是否在已有区域的控制边缘或内部开始拖拽修改
        handle = self.get_hover_handle(pos)
        if handle:
            self.drag_mode = handle
            self.drag_start_pos = pos
            x = min(self.start_pos.x, self.end_pos.x)
            y = min(self.start_pos.y, self.end_pos.y)
            w = abs(self.start_pos.x - self.end_pos.x)
            h = abs(self.start_pos.y - self.end_pos.y)
            self.drag_start_rect = wx.Rect(x, y, w, h)

            self.is_dragging = True
            self.show_buttons = False

            if not self.panel.HasCapture():
                self.panel.CaptureMouse()

            self.panel.Refresh()
            return

        # 3. 点击外部，创建新截图区域（临时坐标设为单击位置）
        self.start_pos = pos
        self.end_pos = pos
        self.drag_mode = "NEW"
        self.is_dragging = True
        self.show_buttons = False

        if not self.panel.HasCapture():
            self.panel.CaptureMouse()

        self.panel.Refresh()

    def on_motion(self, event):
        self.activate_display()
        pos = event.GetPosition()

        # A. 如果未在拖拽修改状态下，检测悬浮位置改变鼠标光标与智能识别高亮
        if not self.is_dragging and not self.drag_mode:
            if self.start_pos and self.end_pos:
                # 已经有确定选区，只做手柄 hover 判定
                self.set_auto_rect(None)
                handle = self.get_hover_handle(pos)
                self.update_cursor(handle)
                self.hover_handle = handle
            else:
                # 开启窗口控件自动识别（注意将 client 坐标换算回全局 screen 坐标做匹配）
                screen_pt = wx.Point(pos.x + self.rect_full.x, pos.y + self.rect_full.y)
                smallest_rect = self.find_smallest_containing_rect(screen_pt)
                if smallest_rect:
                    client_rect = wx.Rect(smallest_rect)
                    client_rect.x -= self.rect_full.x
                    client_rect.y -= self.rect_full.y
                    if not self._rect_same(self.auto_rect, client_rect):
                        self.set_auto_rect(client_rect)
                else:
                    if self.auto_rect is not None:
                        self.set_auto_rect(None)
                self.SetCursor(wx.Cursor(wx.CURSOR_CROSS))
            event.Skip()
            return

        # B. 绘制新选区状态
        if self.is_dragging and self.drag_mode == "AUTO_CLICK":
            if self.click_start_pos:
                dx = abs(pos.x - self.click_start_pos.x)
                dy = abs(pos.y - self.click_start_pos.y)
                if dx >= 5 or dy >= 5:
                    self.pending_auto_rect = None
                    self.start_pos = self.click_start_pos
                    self.end_pos = pos
                    self.drag_mode = "NEW"
                    self.show_buttons = False
                    self.panel.Refresh()
            return

        if self.is_dragging and self.drag_mode == "NEW":
            self.end_pos = pos
            self.panel.Refresh()
            return

        # C. 二次调整大小或拖拽移动状态
        if self.is_dragging and self.drag_mode:
            dx = pos.x - self.drag_start_pos.x
            dy = pos.y - self.drag_start_pos.y

            screen_w = self.rect_full.width
            screen_h = self.rect_full.height

            r = wx.Rect(self.drag_start_rect)

            if self.drag_mode == "MOVE":
                new_x = self.drag_start_rect.x + dx
                new_y = self.drag_start_rect.y + dy
                if new_x < 0:
                    new_x = 0
                if new_y < 0:
                    new_y = 0
                if new_x + r.width > screen_w:
                    new_x = screen_w - r.width
                if new_y + r.height > screen_h:
                    new_y = screen_h - r.height
                r.x = new_x
                r.y = new_y
            else:
                # 边缘拉伸夹逼限制
                min_size = max(10, int(10 * self.scale_factor))

                # 水平调整
                if "L" in self.drag_mode:
                    new_x = self.drag_start_rect.x + dx
                    new_w = self.drag_start_rect.width - dx
                    if new_x < 0:
                        new_x = 0
                        new_w = self.drag_start_rect.x + self.drag_start_rect.width
                    if new_w < min_size:
                        new_w = min_size
                        new_x = self.drag_start_rect.x + self.drag_start_rect.width - min_size
                    r.x = new_x
                    r.width = new_w
                elif "R" in self.drag_mode:
                    new_w = self.drag_start_rect.width + dx
                    if self.drag_start_rect.x + new_w > screen_w:
                        new_w = screen_w - self.drag_start_rect.x
                    if new_w < min_size:
                        new_w = min_size
                    r.width = new_w

                # 垂直调整
                if "T" in self.drag_mode:
                    new_y = self.drag_start_rect.y + dy
                    new_h = self.drag_start_rect.height - dy
                    if new_y < 0:
                        new_y = 0
                        new_h = self.drag_start_rect.y + self.drag_start_rect.height
                    if new_h < min_size:
                        new_h = min_size
                        new_y = self.drag_start_rect.y + self.drag_start_rect.height - min_size
                    r.y = new_y
                    r.height = new_h
                elif "B" in self.drag_mode:
                    new_h = self.drag_start_rect.height + dy
                    if self.drag_start_rect.y + new_h > screen_h:
                        new_h = screen_h - self.drag_start_rect.y
                    if new_h < min_size:
                        new_h = min_size
                    r.height = new_h

            self.start_pos = wx.Point(r.x, r.y)
            self.end_pos = wx.Point(r.x + r.width, r.y + r.height)
            self.panel.Refresh()

    def on_left_up(self, event):
        # 释放鼠标捕获
        if self.panel.HasCapture():
            try:
                self.panel.ReleaseMouse()
            except Exception:
                pass

        pos = event.GetPosition()
        is_click = False
        if hasattr(self, "click_start_pos") and self.click_start_pos:
            dx = abs(pos.x - self.click_start_pos.x)
            dy = abs(pos.y - self.click_start_pos.y)
            if dx < 5 and dy < 5:
                is_click = True

        if self.is_dragging:
            pending_auto_rect = self.pending_auto_rect
            self.is_dragging = False
            self.drag_mode = None
            self.pending_auto_rect = None

            # 如果是单纯的单击，且有自动探测的窗口/元素，则直接贴合自动探测框
            if is_click and pending_auto_rect:
                self.start_pos = wx.Point(pending_auto_rect.x, pending_auto_rect.y)
                self.end_pos = wx.Point(
                    pending_auto_rect.x + pending_auto_rect.width,
                    pending_auto_rect.y + pending_auto_rect.height,
                )
                self.show_buttons = True
                self.set_auto_rect(None)
            elif is_click and self.auto_rect:
                self.start_pos = wx.Point(self.auto_rect.x, self.auto_rect.y)
                self.end_pos = wx.Point(
                    self.auto_rect.x + self.auto_rect.width, self.auto_rect.y + self.auto_rect.height
                )
                self.show_buttons = True
                self.set_auto_rect(None)
            else:
                # 拖拽绘制或二次调整结束
                if self.start_pos and self.end_pos:
                    x = min(self.start_pos.x, self.end_pos.x)
                    y = min(self.start_pos.y, self.end_pos.y)
                    sw = abs(self.start_pos.x - self.end_pos.x)
                    sh = abs(self.start_pos.y - self.end_pos.y)

                    if sw > 5 and sh > 5:
                        self.start_pos = wx.Point(x, y)
                        self.end_pos = wx.Point(x + sw, y + sh)
                        self.show_buttons = True
                    else:
                        self.start_pos = None
                        self.end_pos = None
                        self.show_buttons = False

            self.panel.Refresh()
            self.click_start_pos = None

    def on_right_down(self, event):
        self.cancel_capture()

    def on_double_click(self, event):
        pos = event.GetPosition()
        if self.start_pos and self.end_pos:
            x = min(self.start_pos.x, self.end_pos.x)
            y = min(self.start_pos.y, self.end_pos.y)
            sw = abs(self.start_pos.x - self.end_pos.x)
            sh = abs(self.start_pos.y - self.end_pos.y)
            rect = wx.Rect(x, y, sw, sh)
            if rect.Contains(pos):
                self.confirm_capture()

    def on_key_down(self, event):
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_ESCAPE:
            self.cancel_capture()
        elif keycode == wx.WXK_RETURN:
            self.confirm_capture()
        else:
            event.Skip()

    def confirm_capture(self):
        if self.start_pos and self.end_pos:
            x = min(self.start_pos.x, self.end_pos.x)
            y = min(self.start_pos.y, self.end_pos.y)
            sw = abs(self.start_pos.x - self.end_pos.x)
            sh = abs(self.start_pos.y - self.end_pos.y)

            if sw > 5 and sh > 5:
                rect = wx.Rect(x, y, sw, sh)
                try:
                    cropped_bitmap = self.original_bitmap.GetSubBitmap(rect)
                    image = cropped_bitmap.ConvertToImage()

                    temp_dir = tempfile.gettempdir()
                    # 加上显示器索引防止并发冲突
                    temp_path = os.path.join(temp_dir, f"wx_ocr_cap_{self.display_idx}_{int(time.time() * 1000)}.png")
                    if image.SaveFile(temp_path, wx.BITMAP_TYPE_PNG):
                        self.Hide()
                        self.Close()
                        if self.on_capture_callback:
                            self.on_capture_callback(temp_path)
                        return
                except Exception as e:
                    print(f"Error cropping/saving capture: {e}")

        self.cancel_capture()

    def cancel_capture(self):
        self.Hide()
        self.Close()
        if self.on_capture_callback:
            self.on_capture_callback(None)
