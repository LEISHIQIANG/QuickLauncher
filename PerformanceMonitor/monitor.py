import sys
import psutil
import ctypes
from ctypes import wintypes
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import QTimer, Qt, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen, QIcon
from collections import deque

def set_window_corner(hwnd):
    dwmapi = ctypes.windll.dwmapi
    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWCP_ROUND = 2
    dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(ctypes.c_int(DWMWCP_ROUND)), ctypes.sizeof(ctypes.c_int))

class PerformanceChart(QWidget):
    def __init__(self, title, unit, max_value=100):
        super().__init__()
        self.title = title
        self.unit = unit
        self.max_value = max_value
        self.data_realtime = deque([0] * 120, maxlen=120)
        self.all_data = []
        self.average = 0
        self.setMinimumHeight(200)

    def add_data(self, realtime):
        self.data_realtime.append(realtime)
        self.all_data.append(realtime)
        self.average = sum(self.all_data) / len(self.all_data)
        if realtime > self.max_value:
            self.max_value = realtime * 1.2
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        margin_left = 40
        margin_right = 10
        margin_top = 40
        margin_bottom = 40
        chart_w = w - margin_left - margin_right
        chart_h = h - margin_top - margin_bottom

        # 背景
        painter.fillRect(0, 0, w, h, QColor(30, 30, 30))
        painter.fillRect(margin_left, margin_top, chart_w, chart_h, QColor(20, 20, 20))

        # 网格和Y轴标注
        painter.setPen(QPen(QColor(60, 60, 60), 0.5))
        for i in range(5):
            y = margin_top + i * chart_h // 4
            painter.drawLine(margin_left, y, margin_left + chart_w, y)

            # Y轴数值
            value = self.max_value * (1 - i / 4)
            painter.setPen(QColor(150, 150, 150))
            if self.max_value < 10:
                painter.drawText(margin_left - 20, y + 5, f"{value:.1f}")
            else:
                painter.drawText(margin_left - 20, y + 5, f"{value:.0f}")
            painter.setPen(QPen(QColor(60, 60, 60), 0.5))

        # 绘制实时数据（填充）
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 120, 215, 80))
        points = []
        for i, val in enumerate(self.data_realtime):
            x = margin_left + chart_w - (120 - i) * chart_w // 120
            y = margin_top + chart_h - int(val * chart_h / self.max_value)
            points.append((x, y))

        if points:
            from PyQt5.QtGui import QPolygon
            from PyQt5.QtCore import QPoint
            poly_points = [QPoint(int(x), int(y)) for x, y in points]
            poly_points.append(QPoint(int(points[-1][0]), margin_top + chart_h))
            poly_points.append(QPoint(int(points[0][0]), margin_top + chart_h))
            painter.drawPolygon(QPolygon(poly_points))

        # 绘制实时线
        painter.setPen(QPen(QColor(0, 180, 240), 1))
        for i in range(len(self.data_realtime) - 1):
            x1 = margin_left + chart_w - (120 - i) * chart_w // 120
            y1 = margin_top + chart_h - int(self.data_realtime[i] * chart_h / self.max_value)
            x2 = margin_left + chart_w - (120 - i - 1) * chart_w // 120
            y2 = margin_top + chart_h - int(self.data_realtime[i + 1] * chart_h / self.max_value)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # 绘制平均线（虚线直线）
        avg_y = margin_top + chart_h - int(self.average * chart_h / self.max_value)
        pen = QPen(QColor(100, 200, 100), 1)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(margin_left, avg_y, margin_left + chart_w, avg_y)

        # 标题和数值
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(10, 16, f"{self.title}: {self.data_realtime[-1]:.1f}{self.unit}")
        painter.drawText(10, 31, f"平均: {self.average:.1f}{self.unit}")

class PerformanceMonitor(QWidget):
    def __init__(self, process_name="QuickLauncher"):
        super().__init__()
        self.process_name = process_name
        self.process = None
        self.drag_pos = None
        self.last_io = None
        self.init_ui()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(1000)

    def init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setGeometry(100, 100, 800, 630)
        self.setStyleSheet("background: #1e1e1e; border-radius: 10px;")

        main_layout = QVBoxLayout()
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 标题栏
        title_bar = QWidget()
        title_bar.setFixedHeight(30)
        title_bar.setStyleSheet("background: #1e1e1e;")
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(5, 0, 5, 0)

        icon_label = QLabel()
        icon_label.setPixmap(QIcon("app.ico").pixmap(20, 20))
        title_layout.addWidget(icon_label)

        title_label = QLabel(f"性能监视器 - {self.process_name}")
        title_label.setStyleSheet("color: white; font-size: 12px;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet("QPushButton{background:transparent;color:white;font-size:20px;border:none;} QPushButton:hover{background:#e81123;}")
        close_btn.clicked.connect(self.close)
        title_layout.addWidget(close_btn)

        title_bar.setLayout(title_layout)
        main_layout.addWidget(title_bar)

        # 图表
        self.cpu_chart = PerformanceChart("CPU", "%", 5)
        self.mem_chart = PerformanceChart("内存", "MB", 200)
        self.disk_chart = PerformanceChart("磁盘", "MB/s", 1)

        main_layout.addWidget(self.cpu_chart)
        main_layout.addWidget(self.mem_chart)
        main_layout.addWidget(self.disk_chart)

        self.setLayout(main_layout)

    def showEvent(self, event):
        super().showEvent(event)
        set_window_corner(int(self.winId()))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.y() < 30:
            self.drag_pos = event.globalPos() - self.pos()

    def mouseMoveEvent(self, event):
        if self.drag_pos and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_pos)

    def mouseReleaseEvent(self, event):
        self.drag_pos = None

    def find_process(self):
        for proc in psutil.process_iter(['name', 'pid']):
            if self.process_name.lower() in proc.info['name'].lower():
                p = psutil.Process(proc.info['pid'])
                p.cpu_percent()  # 初始化CPU计数
                return p
        return None

    def update_data(self):
        if not self.process:
            self.process = self.find_process()

        if self.process:
            try:
                cpu = self.process.cpu_percent() / psutil.cpu_count()
                mem = self.process.memory_full_info().uss / 1024 / 1024
                io = self.process.io_counters()

                # 计算磁盘速率 (MB/s)
                if self.last_io:
                    disk = ((io.read_bytes + io.write_bytes) - (self.last_io.read_bytes + self.last_io.write_bytes)) / 1024 / 1024
                else:
                    disk = 0
                self.last_io = io

                self.cpu_chart.add_data(cpu)
                self.mem_chart.add_data(mem)
                self.disk_chart.add_data(disk)
            except:
                self.process = None
                self.last_io = None
        else:
            self.cpu_chart.add_data(0)
            self.mem_chart.add_data(0)
            self.disk_chart.add_data(0)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    monitor = PerformanceMonitor("QuickLauncher")
    monitor.show()
    sys.exit(app.exec_())
