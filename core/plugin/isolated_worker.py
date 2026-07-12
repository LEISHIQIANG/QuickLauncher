"""Generic worker process for unverified third-party plugins."""

from __future__ import annotations

import builtins
import importlib.util
import logging
import time
import types
import uuid
from pathlib import Path
from typing import Any

from extensions.sdk.worker_protocol import ready_message

logger = logging.getLogger(__name__)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_value(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _json_value(to_dict())
    fields = (
        "success",
        "message",
        "display_type",
        "payload",
        "actions",
        "error",
        "is_async",
        "progress",
        "cancellable",
    )
    if any(hasattr(value, field) for field in fields):
        return {field: _json_value(getattr(value, field, None)) for field in fields}
    return str(value)


class RemotePluginAPI:
    def __init__(self, channel, request_id: str, plugin_id: str, plugin_dir: Path, permissions: list[str]) -> None:
        self.channel = channel
        self.request_id = request_id
        self.plugin_id = plugin_id
        self.plugin_dir = plugin_dir
        self.permissions = frozenset(permissions)
        self.commands: list[dict[str, Any]] = []
        self.command_handlers: dict[str, Any] = {}
        self.search_sources: list[dict[str, Any]] = []
        self.search_handlers: dict[str, Any] = {}
        self.modules: list[dict[str, str]] = []

    @property
    def logger(self) -> logging.Logger:
        return logging.getLogger(f"plugin.{self.plugin_id}")

    @property
    def data_dir(self) -> Path:
        return Path(self._host_call("data_dir"))

    def register_command(self, id: str, title: str, handler, **kwargs) -> bool:
        expected = {self.plugin_id, self.plugin_id.replace("-", "_").replace(" ", "_")}
        if "." not in id or id.split(".", 1)[0] not in expected:
            return False
        self.command_handlers[id] = handler
        self.commands.append({"id": id, "title": title, "kind": "command", **_json_value(kwargs)})
        return True

    def register_builtin_command(self, id: str, title: str, handler, **kwargs) -> bool:
        self.command_handlers[id] = handler
        self.commands.append({"id": id, "title": title, "kind": "builtin", **_json_value(kwargs)})
        return True

    def register_search_source(self, source_id: str, handler=None, **kwargs) -> bool:
        self.search_handlers[source_id] = handler
        self.search_sources.append({"id": source_id, **_json_value(kwargs)})
        return True

    def register_module(self, module_id: str, manifest_path: str = "module.json") -> bool:
        self.modules.append({"id": module_id, "manifest_path": manifest_path})
        return True

    def _host_call(self, method: str, *args, **kwargs):
        call_id = uuid.uuid4().hex
        self.channel.send(
            {
                "type": "host_call",
                "id": self.request_id,
                "call_id": call_id,
                "method": method,
                "args": _json_value(args),
                "kwargs": _json_value(kwargs),
            }
        )
        response = self.channel.receive()
        if response.get("type") != "host_response" or response.get("call_id") != call_id:
            raise RuntimeError("invalid host API response")
        if not response.get("ok"):
            error = response.get("error")
            message = error.get("message") if isinstance(error, dict) else error
            raise PermissionError(str(message or "host API call failed"))
        return response.get("result")

    def __getattr__(self, name: str):
        allowed = {
            "read_clipboard",
            "write_clipboard",
            "get_selected_files",
            "get_theme",
            "get_app_version",
            "open_url",
            "open_file",
            "open_folder",
            "read_text_file",
            "write_data_file",
            "http_request",
            "run_process_capture",
            "launch_target",
            "run_command",
            "is_user_admin",
            "get_recycle_bin_info",
            "empty_recycle_bin",
        }
        if name not in allowed:
            raise AttributeError(name)
        return lambda *args, **kwargs: self._host_call(name, *args, **kwargs)


class IsolatedPluginWorker:
    def __init__(self, channel, token: str) -> None:
        self.channel = channel
        self.token = token
        self.api: RemotePluginAPI | None = None
        self.module: Any = None

    def run(self) -> int:
        self.channel.send(ready_message(self.token, worker_version="1.0.0"))
        while True:
            message = self.channel.receive()
            message_type = str(message.get("type") or "")
            if message_type == "shutdown":
                self._dispose()
                return 0
            if message_type == "heartbeat":
                self.channel.send({"type": "heartbeat_ack", "id": message.get("id")})
                continue
            if message_type == "cancel":
                continue
            if message_type != "request":
                continue
            request_id = str(message.get("id") or "")
            deadline_ms = int(message.get("deadline_ms") or 0)
            if deadline_ms and int(time.time() * 1000) >= deadline_ms:
                self._respond(request_id, {"status": "timeout", "error": {"code": "deadline_exceeded"}})
                continue
            payload = message.get("payload")
            try:
                result = self._handle(request_id, dict(payload) if isinstance(payload, dict) else {})
                self._respond(request_id, {"status": "ok", **result})
            except Exception as exc:
                self._respond(
                    request_id,
                    {"status": "error", "error": {"code": type(exc).__name__, "message": str(exc)}},
                )

    def _handle(self, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        operation = str(payload.get("operation") or "")
        if operation == "load":
            return self._load(request_id, payload)
        if self.api is None:
            raise RuntimeError("plugin is not loaded")
        # Host callbacks belong to the currently executing request.  The API
        # object survives the initial load request, so refresh its correlation
        # id before invoking any plugin-owned handler.
        self.api.request_id = request_id
        if operation == "execute_command":
            command_id = str(payload.get("command_id") or "")
            handler = self.api.command_handlers.get(command_id)
            if not callable(handler):
                raise KeyError(command_id)
            context = types.SimpleNamespace(**dict(payload.get("context") or {}))
            return {"result": _json_value(handler(context))}
        if operation == "search":
            source_id = str(payload.get("source_id") or "")
            handler = self.api.search_handlers.get(source_id)
            return {"results": _json_value(handler(str(payload.get("query") or ""))) if callable(handler) else []}
        raise ValueError(f"unsupported operation: {operation}")

    def _load(self, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        entry_path = Path(str(payload.get("entry_path") or "")).resolve(strict=True)
        plugin_dir = entry_path.parent
        plugin_id = str(payload.get("plugin_id") or plugin_dir.name)
        self.api = RemotePluginAPI(
            self.channel,
            request_id,
            plugin_id,
            plugin_dir,
            list(payload.get("permissions") or []),
        )
        module_name = f"_isolated_plugin_{plugin_id}"
        spec = importlib.util.spec_from_file_location(module_name, entry_path)
        if spec is None or spec.loader is None:
            raise ImportError(str(entry_path))
        module = importlib.util.module_from_spec(spec)
        module.__dict__["__builtins__"] = self._restricted_builtins()
        spec.loader.exec_module(module)
        register = getattr(module, "register", None)
        if not callable(register):
            raise AttributeError(f"插件 {plugin_id} 缺少 register(api) 函数")
        register(self.api)
        self.module = module
        return {
            "commands": self.api.commands,
            "search_sources": self.api.search_sources,
            "modules": self.api.modules,
        }

    def _restricted_builtins(self) -> dict[str, Any]:
        safe = dict(vars(builtins))
        original_import = builtins.__import__
        permissions = self.api.permissions if self.api is not None else frozenset()

        def restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
            root = str(name or "").split(".", 1)[0]
            if level == 0 and root in {"ctypes", "multiprocessing", "socket", "subprocess"}:
                raise PermissionError(f"direct import blocked in isolated plugin: {root}")
            return original_import(name, globals, locals, fromlist, level)

        original_open = builtins.open

        def restricted_open(file, mode="r", *args, **kwargs):
            writes = any(flag in str(mode) for flag in ("w", "a", "x", "+"))
            permission = "file.write" if writes else "file.read"
            if permission not in permissions:
                raise PermissionError(f"plugin missing permission: {permission}")
            return original_open(file, mode, *args, **kwargs)

        safe["__import__"] = restricted_import
        safe["open"] = restricted_open
        safe["eval"] = None
        safe["exec"] = None
        return safe

    def _dispose(self) -> None:
        if self.module is None:
            return
        for hook_name in ("unregister", "dispose"):
            hook = getattr(self.module, hook_name, None)
            if callable(hook):
                try:
                    hook(self.api)
                except TypeError:
                    hook()

    def _respond(self, request_id: str, payload: dict[str, Any]) -> None:
        self.channel.send({"type": "response", "id": request_id, "payload": payload})


def run_worker(channel, token: str) -> int:
    return IsolatedPluginWorker(channel, token).run()
