"""PyQt5-only compatibility exports for QuickLauncher."""

import logging
import os

from PyQt5.QtCore import (
    QAbstractListModel,
    QBuffer,
    QByteArray,
    QEasingCurve,
    QEvent,
    QFileInfo,
    QIODevice,
    QMetaObject,
    QMimeData,
    QModelIndex,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QThread,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBitmap,
    QBrush,
    QColor,
    QCursor,
    QDrag,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QImage,
    QImageIOHandler,
    QImageReader,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QRadialGradient,
    QRegion,
    QTextCursor,
)
from PyQt5.QtGui import (
    QTextOption as QTextOption,
)
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

try:
    from PyQt5.QtSvg import QSvgRenderer
except ImportError:
    QSvgRenderer = None  # noqa: N814

try:
    from PyQt5.QtWinExtras import QtWin
except ImportError:
    QtWin = None  # noqa: N814
from PyQt5.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFileIconProvider,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QListView,
    QListWidget,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedLayout,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QSystemTrayIcon,
    QTableWidget,
    QTextBrowser,
    QTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtWidgets import (
    QAction as _QAction,
)
from PyQt5.QtWidgets import (
    QCheckBox as _QCheckBox,
)
from PyQt5.QtWidgets import (
    QGroupBox as _QGroupBox,
)
from PyQt5.QtWidgets import (
    QLabel as _QLabel,
)
from PyQt5.QtWidgets import (
    QLineEdit as _QLineEdit,
)
from PyQt5.QtWidgets import (
    QListWidgetItem as _QListWidgetItem,
)
from PyQt5.QtWidgets import (
    QProgressBar as QProgressBar,
)
from PyQt5.QtWidgets import (
    QPushButton as _QPushButton,
)
from PyQt5.QtWidgets import (
    QRadioButton as _QRadioButton,
)
from PyQt5.QtWidgets import (
    QSlider as _QSlider,
)
from PyQt5.QtWidgets import (
    QSpinBox as _QSpinBox,
)
from PyQt5.QtWidgets import (
    QTableWidgetItem as _QTableWidgetItem,
)

PYQT_VERSION = 5
QT_LIB = "PyQt5"
logger = logging.getLogger(__name__)

from core.i18n import tr  # noqa: E402

logger.debug("Using %s", QT_LIB)


def _translate_args(args):
    return tuple(tr(arg) if isinstance(arg, str) else arg for arg in args)


class _TranslatedTextMixin:
    def setText(self, text):  # noqa: N802 - Qt API name
        if isinstance(text, str):
            text = tr(text)
        return super().setText(text)

    def setToolTip(self, text):  # noqa: N802 - Qt API name
        if isinstance(text, str):
            text = tr(text)
        return super().setToolTip(text)


class QLabel(_TranslatedTextMixin, _QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*_translate_args(args), **kwargs)


class QPushButton(_TranslatedTextMixin, _QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*_translate_args(args), **kwargs)


class QCheckBox(_TranslatedTextMixin, _QCheckBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*_translate_args(args), **kwargs)


class QRadioButton(_TranslatedTextMixin, _QRadioButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*_translate_args(args), **kwargs)


class QGroupBox(_TranslatedTextMixin, _QGroupBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*_translate_args(args), **kwargs)

    def setTitle(self, title):  # noqa: N802 - Qt API name
        if isinstance(title, str):
            title = tr(title)
        return super().setTitle(title)


class QAction(_TranslatedTextMixin, _QAction):
    def __init__(self, *args, **kwargs):
        super().__init__(*_translate_args(args), **kwargs)


class QListWidgetItem(_QListWidgetItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*_translate_args(args), **kwargs)

    def setText(self, text):  # noqa: N802 - Qt API name
        if isinstance(text, str):
            text = tr(text)
        return super().setText(text)


class QTableWidgetItem(_QTableWidgetItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*_translate_args(args), **kwargs)

    def setText(self, text):  # noqa: N802 - Qt API name
        if isinstance(text, str):
            text = tr(text)
        return super().setText(text)


class QLineEdit(_QLineEdit):
    def setPlaceholderText(self, text):  # noqa: N802 - Qt API name
        if isinstance(text, str):
            text = tr(text)
        return super().setPlaceholderText(text)

    def setToolTip(self, text):  # noqa: N802 - Qt API name
        if isinstance(text, str):
            text = tr(text)
        return super().setToolTip(text)


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
    ItemIsSelectable = Qt.ItemIsSelectable
    ItemIsEnabled = Qt.ItemIsEnabled

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
        logger.debug("设置DPI感知失败", exc_info=True)

    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        logger.debug("设置高DPI缩放属性失败", exc_info=True)


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
    "PYQT_VERSION",
    "QT_LIB",
    "QtCompat",
    "setup_high_dpi",
    "get_standard_icon",
    "exec_app",
    "exec_dialog",
    "pyqtSignal",
    "pyqtProperty",
    "QApplication",
    "QMainWindow",
    "QWidget",
    "QDialog",
    "QVBoxLayout",
    "QHBoxLayout",
    "QGridLayout",
    "QFormLayout",
    "QLabel",
    "QPushButton",
    "QLineEdit",
    "QTextBrowser",
    "QTextEdit",
    "QPlainTextEdit",
    "QSpinBox",
    "QSlider",
    "QCheckBox",
    "QRadioButton",
    "QButtonGroup",
    "QGroupBox",
    "QListWidget",
    "QListWidgetItem",
    "QListView",
    "QScrollArea",
    "QFrame",
    "QMenu",
    "QMenuBar",
    "QStatusBar",
    "QSplitter",
    "QAction",
    "QFileDialog",
    "QInputDialog",
    "QMessageBox",
    "QColorDialog",
    "QSystemTrayIcon",
    "QSizePolicy",
    "QStyle",
    "QFileIconProvider",
    "QComboBox",
    "QToolTip",
    "QStackedWidget",
    "QStackedLayout",
    "QAbstractSpinBox",
    "QStyledItemDelegate",
    "QStyleOptionViewItem",
    "QGraphicsDropShadowEffect",
    "QGraphicsOpacityEffect",
    "QTableWidget",
    "QTableWidgetItem",
    "QHeaderView",
    "QIcon",
    "QPixmap",
    "QImage",
    "QPainter",
    "QColor",
    "QPen",
    "QBrush",
    "QPainterPath",
    "QFont",
    "QFontMetrics",
    "QFontDatabase",
    "QGuiApplication",
    "QKeySequence",
    "QDrag",
    "QCursor",
    "QImageReader",
    "QImageIOHandler",
    "QTextCursor",
    "QRegion",
    "QBitmap",
    "QLinearGradient",
    "QPalette",
    "QRadialGradient",
    "Qt",
    "QObject",
    "QTimer",
    "QPoint",
    "QSize",
    "QRect",
    "QRectF",
    "QPointF",
    "QMimeData",
    "QByteArray",
    "QBuffer",
    "QIODevice",
    "QFileInfo",
    "QThread",
    "QModelIndex",
    "QAbstractListModel",
    "QEvent",
    "QMetaObject",
    "QPropertyAnimation",
    "QEasingCurve",
    "QParallelAnimationGroup",
    "QLocalServer",
    "QLocalSocket",
    "QSvgRenderer",
    "QtWin",
]
