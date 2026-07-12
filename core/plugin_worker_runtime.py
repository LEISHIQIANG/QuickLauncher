"""Persistent out-of-process runtime for heavyweight plugins."""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from application.errors import DomainError, OperationTimeout
from extensions.sdk.worker_protocol import CAP_HEARTBEAT, negotiate_worker
from infrastructure.process import runtime as process_runtime
from runtime_paths import app_executable, app_root, is_packaged_runtime

logger = logging.getLogger(__name__)
_MAX_MESSAGE_BYTES = 4 * 1024 * 1024


def _find_dist_quicklauncher_exe() -> Path | None:
    """Find a packaged QuickLauncher.exe in project dist directories.

    In dev mode, the project's wxPython/.pyd files may be compiled for
    a different CPython version (e.g. cp312) than the dev interpreter
    (e.g. 3.13).  Workers that import wxPython (ocr_worker.py,
    qr_worker.py) must run under the packaged interpreter.
    """
    try:
        root = Path(__file__).resolve().parents[1]
        candidates = [
            root / "dist" / "main.dist" / "QuickLauncher.exe",
            root / "dist" / "QuickLauncher" / "QuickLauncher.exe",
        ]
        for entry in (
            (root / "dist").glob("QuickLauncher_Portable_*/QuickLauncher.exe") if (root / "dist").is_dir() else []
        ):
            candidates.append(entry)
        for candidate in candidates:
            if candidate.is_file():
                return candidate
    except Exception:
        logger.debug("No worker runtime candidate found", exc_info=True)
    return None


class PluginWorkerError(RuntimeError, DomainError):
    pass


class PluginWorkerBackpressure(PluginWorkerError):
    """Raised when a plugin exceeds its configured worker capacity."""


class JsonLineChannel:
    def __init__(self, connection: socket.socket):
        self._connection = connection
        self._read_buffer = bytearray()
        self._send_lock = threading.Lock()

    def send(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > _MAX_MESSAGE_BYTES:
            raise PluginWorkerError("plugin worker message exceeds size limit")
        with self._send_lock:
            self._connection.sendall(encoded)

    def receive(self, timeout: float | None = None) -> dict[str, Any]:
        self._connection.settimeout(None if timeout is None else max(0.05, float(timeout)))
        while True:
            newline = self._read_buffer.find(b"\n")
            if newline >= 0:
                raw = bytes(self._read_buffer[:newline])
                del self._read_buffer[: newline + 1]
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise PluginWorkerError("plugin worker sent invalid JSON") from exc
                if not isinstance(payload, dict):
                    raise PluginWorkerError("plugin worker message must be an object")
                return payload
            chunk = self._connection.recv(65536)
            if not chunk:
                raise EOFError("plugin worker connection closed")
            self._read_buffer.extend(chunk)
            if len(self._read_buffer) > _MAX_MESSAGE_BYTES:
                raise PluginWorkerError("plugin worker message exceeds size limit")

    def close(self) -> None:
        try:
            self._connection.shutdown(socket.SHUT_RDWR)
        except OSError as exc:
            logger.debug("plugin worker socket shutdown skipped: %s", exc)
        try:
            self._connection.close()
        except OSError as exc:
            logger.debug("plugin worker socket close failed: %s", exc)


class PersistentPluginWorker:
    def __init__(
        self,
        *,
        plugin_id: str,
        script_path: Path,
        site_paths: list[Path] | None = None,
        cwd: Path | None = None,
        inherit_environment: bool = True,
        required_capabilities: frozenset[str] = frozenset(),
        host_call_handler: Any = None,
    ):
        self.plugin_id = str(plugin_id)
        self.script_path = Path(script_path).resolve(strict=False)
        self.site_paths = [Path(path).resolve(strict=False) for path in site_paths or []]
        self.cwd = Path(cwd or self.script_path.parent).resolve(strict=False)
        self.inherit_environment = bool(inherit_environment)
        self.required_capabilities = frozenset(required_capabilities)
        self.host_call_handler = host_call_handler
        self.negotiated_capabilities: frozenset[str] = frozenset()
        self.quarantined = False
        self._process: subprocess.Popen | None = None
        self._channel: JsonLineChannel | None = None
        self._request_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._request_seq = 0
        self._active_requests = 0
        self._active_requests_done = threading.Event()
        self._active_requests_done.set()  # start as done (no requests)

    @property
    def running(self) -> bool:
        process = self._process
        return process is not None and process.poll() is None and self._channel is not None

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process is not None else None

    def start(self, timeout: float = 45.0) -> None:
        with self._state_lock:
            if self.running:
                return
            self._close_unlocked(force=True)
            if not self.script_path.is_file():
                raise FileNotFoundError(str(self.script_path))

            token = secrets.token_urlsafe(32)
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(0.2)
            port = int(listener.getsockname()[1])

            command = self._build_command(port, token)
            env = os.environ.copy() if self.inherit_environment else self._minimal_environment()
            creationflags = 0
            if os.name == "nt":
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
                    subprocess,
                    "BELOW_NORMAL_PRIORITY_CLASS",
                    0x00004000,
                )
            kwargs: dict[str, Any] = {
                "cwd": str(self.cwd),
                "env": env,
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "shell": False,
                "creationflags": creationflags,
            }
            started = time.perf_counter()
            try:
                self._process = process_runtime.popen(command, **kwargs)
                deadline = time.monotonic() + max(0.1, float(timeout))
                while True:
                    if self._process.poll() is not None:
                        raise PluginWorkerError(
                            f"plugin worker exited during startup: returncode={self._process.returncode}"
                        )
                    try:
                        connection, address = listener.accept()
                        break
                    except TimeoutError:
                        if time.monotonic() >= deadline:
                            raise OperationTimeout(f"plugin worker startup timed out after {timeout:.1f}s") from None
                if address[0] not in ("127.0.0.1", "::1"):
                    connection.close()
                    raise PluginWorkerError("plugin worker connected from a non-loopback address")
                channel = JsonLineChannel(connection)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    channel.close()
                    raise OperationTimeout(f"plugin worker startup timed out after {timeout:.1f}s")
                try:
                    hello = channel.receive(timeout=remaining)
                except EOFError as exc:
                    returncode = self._process.poll()
                    raise PluginWorkerError(f"plugin worker exited during startup: returncode={returncode}") from exc
                if hello.get("type") != "ready" or not secrets.compare_digest(str(hello.get("token") or ""), token):
                    channel.close()
                    raise PluginWorkerError("plugin worker authentication failed")
                negotiated = negotiate_worker(hello, self.required_capabilities)
                self.negotiated_capabilities = negotiated.capabilities
                self.quarantined = False
                self._channel = channel
                logger.info(
                    "插件常驻运行时就绪: plugin=%s pid=%s elapsed=%.1f ms",
                    self.plugin_id,
                    getattr(self._process, "pid", 0),
                    (time.perf_counter() - started) * 1000,
                )
            except Exception:
                self._close_unlocked(force=True)
                raise
            finally:
                listener.close()

    def request(
        self,
        payload: dict[str, Any],
        timeout: float = 300.0,
        *,
        capability: str = "request",
    ) -> dict[str, Any]:
        with self._request_lock:
            if not self.running:
                self.start(timeout=min(max(5.0, float(timeout)), 60.0))
            channel = self._channel
            if channel is None:
                raise PluginWorkerError("plugin worker is unavailable")
            if capability and capability not in self.negotiated_capabilities:
                raise PluginWorkerError(f"plugin worker capability unavailable: {capability}")
            self._request_seq += 1
            request_id = f"{self.plugin_id}-{self._request_seq}"
            message = {
                "type": "request",
                "id": request_id,
                "payload": dict(payload or {}),
                "deadline_ms": int((time.time() + max(0.05, timeout)) * 1000),
            }
            self._active_requests += 1
            if self._active_requests == 1:
                self._active_requests_done.clear()
        try:
            try:
                channel.send(message)
                response = self._receive_response(channel, request_id, timeout)
                if response.get("type") != "response" or response.get("id") != request_id:
                    raise PluginWorkerError("plugin worker returned a mismatched response")
                result = response.get("payload")
                if not isinstance(result, dict):
                    raise PluginWorkerError("plugin worker returned an invalid payload")
            except Exception:
                with self._state_lock:
                    self._close_unlocked(force=True)
                raise
            return result
        finally:
            with self._state_lock:
                self._active_requests = max(0, self._active_requests - 1)
                if self._active_requests == 0:
                    self._active_requests_done.set()

    def _receive_response(
        self,
        channel: JsonLineChannel,
        request_id: str,
        timeout: float,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.05, float(timeout))
        while True:
            response = channel.receive(timeout=max(0.05, deadline - time.monotonic()))
            if response.get("type") != "host_call":
                return response
            if response.get("id") != request_id:
                raise PluginWorkerError("plugin worker returned a mismatched host call")
            self._handle_host_call(channel, response)

    def _handle_host_call(self, channel: JsonLineChannel, message: dict[str, Any]) -> None:
        call_id = str(message.get("call_id") or "")
        response: dict[str, Any] = {"type": "host_response", "call_id": call_id}
        try:
            if not callable(self.host_call_handler):
                raise PermissionError("plugin host calls are disabled")
            args = message.get("args")
            kwargs = message.get("kwargs")
            response["result"] = self.host_call_handler(
                str(message.get("method") or ""),
                list(args) if isinstance(args, list) else [],
                dict(kwargs) if isinstance(kwargs, dict) else {},
            )
            response["ok"] = True
        except Exception as exc:
            response["ok"] = False
            response["error"] = {"code": type(exc).__name__, "message": str(exc)}
        channel.send(response)

    def health_check(self, timeout: float = 3.0) -> bool:
        if not self.running:
            return False
        if CAP_HEARTBEAT not in self.negotiated_capabilities:
            return True
        with self._request_lock:
            channel = self._channel
            if channel is None:
                return False
            heartbeat_id = f"health-{self.plugin_id}-{time.monotonic_ns()}"
            try:
                channel.send({"type": "heartbeat", "id": heartbeat_id})
                response = channel.receive(timeout=timeout)
                healthy = response.get("type") == "heartbeat_ack" and response.get("id") == heartbeat_id
            except Exception:
                healthy = False
            if not healthy:
                self.quarantined = True
            else:
                self.quarantined = False
            return healthy

    def close(self, timeout: float = 3.0) -> None:
        """Shut down the worker subprocess gracefully.

        Waits for any in-flight ``request()`` calls to complete before
        force-killing the subprocess.  This prevents the subprocess from
        being terminated mid-operation, which could leave plugin state
        inconsistent.
        """
        with self._state_lock:
            channel = self._channel
            process = self._process
            if channel is not None and process is not None and process.poll() is None:
                try:
                    channel.send({"type": "shutdown"})
                    process.wait(timeout=max(0.1, float(timeout)))
                except Exception as exc:
                    logger.debug("plugin worker graceful shutdown failed: %s", exc)

            # Wait for in-flight requests to complete before closing the
            # channel and force-killing the process.  This avoids the
            # race where _close_unlocked(force=True) kills the subprocess
            # while a request() thread is blocked in _receive_response().
            if self._active_requests > 0:
                self._active_requests_done.wait(timeout=max(0.5, float(timeout)))

            self._close_unlocked(force=True)

    def _close_unlocked(self, *, force: bool) -> None:
        channel = self._channel
        self._channel = None
        if channel is not None:
            channel.close()
        process = self._process
        self._process = None
        self.negotiated_capabilities = frozenset()
        # Reset the active-requests tracker so that any subsequent start()
        # begins with a clean state (the old requests are dead anyway
        # because we just closed the channel).
        self._active_requests = 0
        self._active_requests_done.set()
        if process is None or process.poll() is not None:
            return
        if force:
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except Exception:
                try:
                    process.kill()
                except OSError as exc:
                    logger.debug("plugin worker force kill failed: %s", exc)

    def _build_command(self, port: int, token: str) -> list[str]:
        if is_packaged_runtime():
            command = [str(app_executable()), "--plugin-worker", str(self.script_path)]
        else:
            # Dev mode: prefer packaged QuickLauncher.exe when available so that
            # workers importing wxPython (ocr_worker.py, qr_worker.py) can load
            # the bundled cp312 .pyd files even when the dev interpreter is 3.13.
            fallback_exe = _find_dist_quicklauncher_exe()
            if fallback_exe is not None:
                command = [str(fallback_exe), "--plugin-worker", str(self.script_path)]
            else:
                command = [str(sys.executable), str(app_root() / "main.py"), "--plugin-worker", str(self.script_path)]
        for site_path in self.site_paths:
            command.extend(["--plugin-site", str(site_path)])
        command.extend(["--plugin-port", str(port), "--plugin-token", token])
        return command

    @staticmethod
    def _minimal_environment() -> dict[str, str]:
        keep = ("SystemRoot", "WINDIR", "TEMP", "TMP", "PATH", "PATHEXT", "COMSPEC")
        return {key: value for key in keep if (value := os.environ.get(key))}


def run_worker_process(
    script_path: str,
    *,
    site_paths: list[str],
    port: int,
    token: str,
) -> int:
    script = Path(script_path).resolve(strict=False)
    if not script.is_file():
        return 2
    for path in reversed([script.parent, *[Path(value) for value in site_paths]]):
        path_text = str(path.resolve(strict=False))
        if path.is_dir() and path_text not in sys.path:
            sys.path.insert(0, path_text)
        if path.is_dir():
            os.environ["PATH"] = path_text + os.pathsep + os.environ.get("PATH", "")
            add_dll_directory = getattr(os, "add_dll_directory", None)
            if add_dll_directory:
                try:
                    add_dll_directory(path_text)
                except OSError as exc:
                    logger.debug("plugin worker DLL directory rejected %s: %s", path_text, exc)

    connection = socket.create_connection(("127.0.0.1", int(port)), timeout=15.0)
    channel = JsonLineChannel(connection)
    module_name = f"_plugin_worker_{secrets.token_hex(8)}"
    spec = importlib.util.spec_from_file_location(module_name, script)
    if spec is None or spec.loader is None:
        channel.close()
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run_worker = getattr(module, "run_worker", None)
    if not callable(run_worker):
        channel.close()
        return 2
    try:
        result = run_worker(channel, token)
        return int(result or 0)
    finally:
        channel.close()
