"""Helpers for non-blocking QThread shutdown.

Qt aborts with ``QThread: Destroyed while thread is still running`` when a
QThread wrapper is destroyed before the native thread has actually finished.
For UI teardown paths we keep late-finishing threads alive at process level and
delete them only after their ``finished`` signal fires.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable

logger = logging.getLogger(__name__)

_deferred_qthreads: list[dict[str, object]] = []
_DEFERRED_LOCK = threading.Lock()


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
    if obj is None:
        return
    for name in names or ():
        try:
            signal = getattr(obj, name, None)
        except RuntimeError as exc:
            logger.debug("断开线程信号时对象已失效: %s", exc, exc_info=True)
            return
        except (AttributeError, TypeError) as exc:
            logger.debug("读取线程信号失败: %s", exc, exc_info=True)
            continue
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
    with _DEFERRED_LOCK:
        _deferred_qthreads.append(record)

    def _cleanup_deferred_thread():
        try:
            if delete:
                _safe_delete_later(worker, owner)
                _safe_delete_later(thread, owner)
        finally:
            with _DEFERRED_LOCK:
                try:
                    _deferred_qthreads.remove(record)
                except ValueError:
                    logger.debug("Deferred thread record already removed")

    try:
        thread.finished.connect(_cleanup_deferred_thread)
    except RuntimeError:
        _cleanup_deferred_thread()
    except (AttributeError, TypeError) as exc:
        logger.debug("注册线程延迟回收失败 [%s]: %s", owner, exc, exc_info=True)

    logger.debug("线程仍在运行，已移入延迟回收列表 [%s]", owner)
    return False


def deferred_qthread_count() -> int:
    with _DEFERRED_LOCK:
        return len(_deferred_qthreads)


def drain_deferred_qthreads(timeout: float = 2.0) -> int:
    """Wait for deferred qthreads to finish and clean them up.

    Called during application shutdown to give late-finishing threads a
    chance to finish before the event loop stops.  Non-blocking: threads
    that exceed *timeout* are left for process exit to clean up.

    Returns the number of threads still alive after the drain.
    """
    deadline = time.monotonic() + max(0.0, float(timeout or 0.0))
    with _DEFERRED_LOCK:
        records = list(_deferred_qthreads)
    still_alive = 0
    for record in records:
        remaining = max(0.0, deadline - time.monotonic())
        if remaining <= 0:
            break
        thread = record.get("thread")
        if thread is None:
            continue
        try:
            quit_method = getattr(thread, "quit", None)
            if callable(quit_method):
                quit_method()
        except Exception:
            logger.debug("Thread quit() failed during deferred drain")
        try:
            wait_method = getattr(thread, "wait", None)
            if callable(wait_method):
                wait_method(int(remaining * 1000))
        except Exception:
            logger.debug("Thread wait() failed during deferred drain")
        try:
            if not _is_running(thread):
                still_alive += 0
                owner = str(record.get("owner", "") or "")
                _safe_delete_later(record.get("worker"), owner)
                _safe_delete_later(thread, owner)
            else:
                still_alive += 1
        except Exception:
            still_alive += 1
    if still_alive:
        logger.debug("Deferred drain: %d thread(s) still alive after %.1fs", still_alive, timeout)
    return still_alive
