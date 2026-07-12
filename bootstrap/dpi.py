import ctypes
import logging

logger = logging.getLogger(__name__)


def setup_dpi_awareness():
    try:
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception as exc:
                    logger.debug("设置DPI感知失败: %s", exc, exc_info=True)
    except Exception as exc:
        logger.debug("设置DPI感知外层失败: %s", exc, exc_info=True)
