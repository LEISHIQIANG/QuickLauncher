"""Helpers for non-blocking QThread shutdown.

Qt aborts with ``QThread: Destroyed while thread is still running`` when a
QThread wrapper is destroyed before the native thread has actually finished.
For UI teardown paths we keep late-finishing threads alive at process level and
delete them only after their ``finished`` signal fires.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

logger = logging.getLogger(__name__)

_deferred_qthreads: list[dict[str, object]] = []


def _safe_disconnect(signal) -> None:
    try:
        signal.disconnect()
    except (TypeError, RuntimeError) as exc:
        logger.debug("线程信号已断开或对象已失效: %s", exc, exc_info=True)
    except AttributeError as exc:
        logger.debug("断开线程信号失败: %s", exc, exc_info=True)


def _safe_delete_later(obj, owner: str) -> None:
    if obj is None:
        return
    try:
        delete_later = getattr(obj, "deleteLater", None)
        if callable(delete_later):
            delete_later()
    except RuntimeError as exc:
        logger.debug("延迟删除线程对象时对象已失效 [%s]: %s", owner, exc, exc_info=True)
    except (AttributeError, TypeError) as exc:
        logger.debug("延迟删除线程对象失败 [%s]: %s", owner, exc, exc_info=True)


def _safe_set_parent_none(obj, owner: str) -> None:
    if obj is None:
        return
    try:
        set_parent = getattr(obj, "setParent", None)
        if callable(set_parent):
            set_parent(None)
    except RuntimeError as exc:
        logger.debug("解除线程父对象时对象已失效 [%s]: %s", owner, exc, exc_info=True)
    except (AttributeError, TypeError) as exc:
        logger.debug("解除线程父对象失败 [%s]: %s", owner, exc, exc_info=True)


def _is_running(thread) -> bool:
    try:
        return bool(thread is not None and thread.isRunning())
    except RuntimeError:
        return False
    except (AttributeError, TypeError):
        return False


def _disconnect_named_signals(obj, names: Iterable[str] | None) -> None:
    for name in names or ():
        signal = getattr(obj, name, None)
        if signal is not None:
            _safe_disconnect(signal)


def stop_qthread_nonblocking(
    thread,
    *,
    worker=None,
    cancel: Callable[[], object] | None = None,
    owner: str = "",
    wait_ms: int = 0,
    delete: bool = True,
    disconnect_thread_signals: Iterable[str] | None = None,
    disconnect_worker_signals: Iterable[str] | None = None,
) -> bool:
    """Ask a QThread to stop without letting teardown destroy it while running.

    Returns ``True`` when the thread is already stopped after the optional short
    wait. Returns ``False`` when the thread is still running and has been moved
    into the process-level keepalive list.
    """

    if thread is None:
        return True

    owner = owner or thread.__class__.__name__

    try:
        if cancel is not None:
            cancel()
        elif worker is not None and callable(getattr(worker, "cancel", None)):
            worker.cancel()
        elif callable(getattr(thread, "request_stop", None)):
            thread.request_stop()
    except RuntimeError as exc:
        logger.debug("请求线程停止时对象已失效 [%s]: %s", owner, exc, exc_info=True)
    except (AttributeError, TypeError) as exc:
        logger.debug("请求线程停止失败 [%s]: %s", owner, exc, exc_info=True)

    try:
        if callable(getattr(thread, "quit", None)):
            thread.quit()
    except RuntimeError as exc:
        logger.debug("quit 线程时对象已失效 [%s]: %s", owner, exc, exc_info=True)
    except (AttributeError, TypeError) as exc:
        logger.debug("quit 线程失败 [%s]: %s", owner, exc, exc_info=True)

    if wait_ms > 0 and _is_running(thread):
        try:
            thread.wait(int(wait_ms))
        except RuntimeError as exc:
            logger.debug("等待线程停止时对象已失效 [%s]: %s", owner, exc, exc_info=True)
        except (AttributeError, TypeError) as exc:
            logger.debug("等待线程停止失败 [%s]: %s", owner, exc, exc_info=True)

    if not _is_running(thread):
        if delete:
            _safe_delete_later(worker, owner)
            _safe_delete_later(thread, owner)
        return True

    _disconnect_named_signals(thread, disconnect_thread_signals)
    _disconnect_named_signals(worker, disconnect_worker_signals)
    _safe_set_parent_none(thread, owner)
    _safe_set_parent_none(worker, owner)

    record = {"thread": thread, "worker": worker, "owner": owner}
    _deferred_qthreads.append(record)

    def _cleanup_deferred_thread():
        try:
            if delete:
                _safe_delete_later(worker, owner)
                _safe_delete_later(thread, owner)
        finally:
            try:
                _deferred_qthreads.remove(record)
            except ValueError as exc:
                logger.debug("延迟回收记录已移除 [%s]: %s", owner, exc)

    try:
        thread.finished.connect(_cleanup_deferred_thread)
    except RuntimeError:
        _cleanup_deferred_thread()
    except (AttributeError, TypeError) as exc:
        logger.debug("注册线程延迟回收失败 [%s]: %s", owner, exc, exc_info=True)

    logger.debug("线程仍在运行，已移入延迟回收列表 [%s]", owner)
    return False


def deferred_qthread_count() -> int:
    return len(_deferred_qthreads)
