"""PyQt5-only compatibility exports for QuickLauncher."""

import logging
import os

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit, QPlainTextEdit,
    QSpinBox as _QSpinBox, QSlider as _QSlider,
    QCheckBox, QRadioButton, QButtonGroup, QGroupBox,
    QListWidget, QListWidgetItem, QListView, QScrollArea, QFrame,
    QMenu, QMenuBar, QStatusBar, QSplitter, QAction,
    QFileDialog, QInputDialog, QMessageBox, QColorDialog,
    QSystemTrayIcon, QSizePolicy, QStyle, QFileIconProvider, QComboBox,
    QToolTip, QStackedWidget, QStackedLayout, QAbstractSpinBox,
    QStyledItemDelegate, QStyleOptionViewItem,
    QGraphicsDropShadowEffect, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt5.QtGui import (
    QIcon, QPixmap, QImage, QPainter, QColor, QPen, QBrush,
    QPainterPath, QFont, QFontMetrics, QFontDatabase, QKeySequence,
    QDrag, QCursor, QImageReader, QImageIOHandler, QTextCursor, QRegion,
    QBitmap, QLinearGradient,
)
from PyQt5.QtCore import (
    Qt, QObject, QTimer, QPoint, QSize, QRect, QRectF, QPointF,
    pyqtSignal, pyqtProperty, QMimeData, QByteArray, QBuffer, QIODevice,
    QFileInfo, QThread, QModelIndex, QAbstractListModel, QEvent, QMetaObject,
    QPropertyAnimation, QEasingCurve, QParallelAnimationGroup,
)
from PyQt5.QtNetwork import QLocalServer, QLocalSocket


PYQT_VERSION = 5
QT_LIB = "PyQt5"
logger = logging.getLogger(__name__)
logger.debug("Using %s", QT_LIB)


class QSlider(_QSlider):
    def wheelEvent(self, event):
        event.ignore()


class QSpinBox(_QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class QtCompat:
    """Qt5 constants used across the project."""

    AlignLeft = Qt.AlignLeft
    AlignRight = Qt.AlignRight
    AlignTop = Qt.AlignTop
    AlignBottom = Qt.AlignBottom
    AlignCenter = Qt.AlignCenter
    AlignHCenter = Qt.AlignHCenter
    AlignVCenter = Qt.AlignVCenter

    FramelessWindowHint = Qt.FramelessWindowHint
    Window = Qt.Window
    Tool = Qt.Tool
    ToolTip = Qt.ToolTip
    WindowStaysOnTopHint = Qt.WindowStaysOnTopHint
    Popup = Qt.Popup
    NoDropShadowWindowHint = Qt.NoDropShadowWindowHint
    Dialog = Qt.Dialog
    WindowTitleHint = Qt.WindowTitleHint
    CustomizeWindowHint = Qt.CustomizeWindowHint
    WindowCloseButtonHint = Qt.WindowCloseButtonHint

    WA_TranslucentBackground = Qt.WA_TranslucentBackground
    WA_ShowWithoutActivating = Qt.WA_ShowWithoutActivating
    WA_NoSystemBackground = Qt.WA_NoSystemBackground
    WA_DeleteOnClose = Qt.WA_DeleteOnClose

    LeftButton = Qt.LeftButton
    RightButton = Qt.RightButton
    MiddleButton = Qt.MiddleButton

    NoModifier = Qt.NoModifier
    ControlModifier = Qt.ControlModifier
    ShiftModifier = Qt.ShiftModifier
    AltModifier = Qt.AltModifier
    MetaModifier = Qt.MetaModifier

    Key_Escape = Qt.Key_Escape
    Key_Left = Qt.Key_Left
    Key_Right = Qt.Key_Right
    Key_Control = Qt.Key_Control
    Key_Alt = Qt.Key_Alt
    Key_Shift = Qt.Key_Shift
    Key_Meta = Qt.Key_Meta

    ArrowCursor = Qt.ArrowCursor
    SizeHorCursor = Qt.SizeHorCursor
    SizeVerCursor = Qt.SizeVerCursor
    SizeFDiagCursor = Qt.SizeFDiagCursor
    SizeBDiagCursor = Qt.SizeBDiagCursor
    PointingHandCursor = Qt.PointingHandCursor
    ForbiddenCursor = Qt.ForbiddenCursor
    BlankCursor = Qt.BlankCursor

    MoveAction = Qt.MoveAction
    CopyAction = Qt.CopyAction

    Format_ARGB32 = QImage.Format_ARGB32
    Format_ARGB32_Premultiplied = QImage.Format_ARGB32_Premultiplied

    Antialiasing = QPainter.Antialiasing
    HighQualityAntialiasing = QPainter.HighQualityAntialiasing
    TextAntialiasing = QPainter.TextAntialiasing
    SmoothPixmapTransform = QPainter.SmoothPixmapTransform

    NoPen = Qt.NoPen
    NoBrush = Qt.NoBrush
    SolidLine = Qt.SolidLine
    DashLine = Qt.DashLine

    InternalMove = QListWidget.InternalMove
    DragDrop = QListWidget.DragDrop

    ScrollBarAlwaysOff = Qt.ScrollBarAlwaysOff
    ScrollBarAlwaysOn = Qt.ScrollBarAlwaysOn
    ScrollBarAsNeeded = Qt.ScrollBarAsNeeded

    Trigger = QSystemTrayIcon.Trigger
    DoubleClick = QSystemTrayIcon.DoubleClick
    Context = QSystemTrayIcon.Context
    MiddleClick = QSystemTrayIcon.MiddleClick

    transparent = Qt.transparent
    white = Qt.white
    black = Qt.black

    KeepAspectRatio = Qt.KeepAspectRatio
    KeepAspectRatioByExpanding = Qt.KeepAspectRatioByExpanding
    IgnoreAspectRatio = Qt.IgnoreAspectRatio

    SmoothTransformation = Qt.SmoothTransformation

    UserRole = Qt.UserRole
    DisplayRole = Qt.DisplayRole
    DecorationRole = Qt.DecorationRole

    ItemIsDragEnabled = Qt.ItemIsDragEnabled
    ItemIsEditable = Qt.ItemIsEditable

    Horizontal = Qt.Horizontal
    Vertical = Qt.Vertical

    SingleSelection = QListWidget.SingleSelection
    NoButtons = QAbstractSpinBox.NoButtons
    NoFrame = QFrame.NoFrame
    Accepted = QDialog.Accepted
    Rejected = QDialog.Rejected

    CustomContextMenu = Qt.CustomContextMenu

    StrongFocus = Qt.StrongFocus
    WheelFocus = Qt.WheelFocus
    NoFocus = Qt.NoFocus

    RoundCap = Qt.RoundCap
    RoundJoin = Qt.RoundJoin

    ElideRight = Qt.ElideRight

    OutCubic = QEasingCurve.OutCubic
    InCubic = QEasingCurve.InCubic
    InOutQuart = QEasingCurve.InOutQuart
    Linear = QEasingCurve.Linear

    State_Selected = QStyle.State_Selected
    State_MouseOver = QStyle.State_MouseOver

    Icon_Information = QMessageBox.Information
    Icon_Warning = QMessageBox.Warning
    Icon_Critical = QMessageBox.Critical
    Icon_Question = QMessageBox.Question

    Btn_Ok = QMessageBox.Ok
    Btn_Cancel = QMessageBox.Cancel
    Btn_Yes = QMessageBox.Yes
    Btn_No = QMessageBox.No

    WindowDeactivate = QEvent.WindowDeactivate

    QPropertyAnimation = QPropertyAnimation
    QEasingCurve = QEasingCurve
    QParallelAnimationGroup = QParallelAnimationGroup


def setup_high_dpi():
    """Configure Windows and Qt high-DPI behavior before QApplication creation."""
    try:
        import ctypes
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass


def get_standard_icon(app, icon_name):
    """Return a QStyle standard icon by name."""
    style = app.style()
    icon_enum = getattr(QStyle, icon_name, QStyle.SP_ComputerIcon)
    return style.standardIcon(icon_enum)


def exec_app(app):
    """Run the Qt application event loop."""
    return app.exec_()


def exec_dialog(dialog):
    """Run a modal dialog in PyQt5."""
    return dialog.exec_()


__all__ = [
    "PYQT_VERSION", "QT_LIB",
    "QtCompat", "setup_high_dpi", "get_standard_icon", "exec_app", "exec_dialog",
    "pyqtSignal", "pyqtProperty",
    "QApplication", "QMainWindow", "QWidget", "QDialog",
    "QVBoxLayout", "QHBoxLayout", "QGridLayout", "QFormLayout",
    "QLabel", "QPushButton", "QLineEdit", "QTextEdit", "QPlainTextEdit",
    "QSpinBox", "QSlider",
    "QCheckBox", "QRadioButton", "QButtonGroup", "QGroupBox",
    "QListWidget", "QListWidgetItem", "QListView", "QScrollArea", "QFrame",
    "QMenu", "QMenuBar", "QStatusBar", "QSplitter", "QAction",
    "QFileDialog", "QInputDialog", "QMessageBox", "QColorDialog",
    "QSystemTrayIcon", "QSizePolicy", "QStyle", "QFileIconProvider",
    "QComboBox", "QToolTip", "QStackedWidget", "QStackedLayout",
    "QAbstractSpinBox", "QStyledItemDelegate", "QStyleOptionViewItem",
    "QGraphicsDropShadowEffect", "QTableWidget", "QTableWidgetItem", "QHeaderView",
    "QIcon", "QPixmap", "QImage", "QPainter", "QColor", "QPen", "QBrush",
    "QPainterPath", "QFont", "QFontMetrics", "QFontDatabase", "QKeySequence",
    "QDrag", "QCursor", "QImageReader", "QImageIOHandler", "QTextCursor", "QRegion",
    "QBitmap", "QLinearGradient",
    "Qt", "QObject", "QTimer", "QPoint", "QSize", "QRect", "QRectF", "QPointF",
    "QMimeData", "QByteArray", "QBuffer", "QIODevice", "QFileInfo", "QThread",
    "QModelIndex", "QAbstractListModel", "QEvent", "QMetaObject",
    "QPropertyAnimation", "QEasingCurve", "QParallelAnimationGroup",
    "QLocalServer", "QLocalSocket",
]
