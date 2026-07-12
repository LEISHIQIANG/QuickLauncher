"""Host-side runtime for process-isolated third-party plugins."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from core.command_registry import CommandContext
from core.plugin_worker_runtime import PersistentPluginWorker, PluginWorkerError
from extensions.sdk.worker_protocol import HOST_CAPABILITIES

from .paths import safe_relative_plugin_path

logger = logging.getLogger(__name__)


def _context_payload(context: CommandContext) -> dict[str, Any]:
    return {
        "raw_input": context.raw_input,
        "args_text": context.args_text,
        "args": dict(context.args),
        "clipboard_text": context.clipboard_text,
        "clipboard_kind": context.clipboard_kind,
        "clipboard_files": list(context.clipboard_files),
        "clipboard_html": context.clipboard_html,
        "selected_text": context.selected_text,
        "selected_text_method": context.selected_text_method,
        "selected_files": list(context.selected_files),
        "context_meta": dict(context.context_meta),
    }


class IsolatedPluginRuntime:
    def __init__(self) -> None:
        self._workers: dict[str, PersistentPluginWorker] = {}

    def load(self, info: Any, host_api: Any) -> None:
        manifest = info.manifest
        safe_entry = safe_relative_plugin_path(manifest.entry)
        if safe_entry is None:
            raise ValueError(f"plugin.entry unsafe path: {manifest.entry}")
        plugin_dir = Path(info.directory).resolve(strict=False)
        entry_path = (plugin_dir / safe_entry).resolve(strict=False)
        worker_script = Path(__file__).with_name("isolated_worker.py")

        allowed_host_methods = {
            "data_dir",
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

        def host_call(method: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
            if method not in allowed_host_methods:
                raise PermissionError(f"host API method is not allowed: {method}")
            value = getattr(host_api, method)
            result = value(*args, **kwargs) if callable(value) else value
            if isinstance(result, Path):
                return str(result)
            return result

        worker = PersistentPluginWorker(
            plugin_id=manifest.id,
            script_path=worker_script,
            site_paths=[plugin_dir],
            cwd=worker_script.parent,
            inherit_environment=True,
            required_capabilities=HOST_CAPABILITIES,
            host_call_handler=host_call,
        )
        try:
            response = worker.request(
                {
                    "operation": "load",
                    "plugin_id": manifest.id,
                    "entry_path": str(entry_path),
                    "permissions": list(manifest.permissions),
                },
                timeout=45.0,
                capability="request",
            )
            self._raise_for_error(response)
            self._register_descriptors(worker, host_api, info, response)
            staged_search_sources = list(host_api._staged_search_sources)
            if not host_api.commit_staged():
                raise RuntimeError(f"插件 {manifest.id} 注册事务失败")
            info.registered_commands = list(host_api._registered_ids)
            info.registered_search_sources = staged_search_sources
            info.registered_modules = dict(host_api._registered_modules)
            self._workers[manifest.id] = worker
        except Exception:
            worker.close()
            raise

    def _register_descriptors(
        self,
        worker: PersistentPluginWorker,
        host_api: Any,
        info: Any,
        response: dict[str, Any],
    ) -> None:
        for descriptor in list(response.get("commands") or []):
            if not isinstance(descriptor, dict):
                continue
            command_id = str(descriptor.get("id") or "")
            title = str(descriptor.get("title") or command_id)
            kind = str(descriptor.get("kind") or "command")
            kwargs = {key: value for key, value in descriptor.items() if key not in {"id", "title", "kind"}}

            def handler(context: CommandContext, command_id: str = command_id):
                result = worker.request(
                    {"operation": "execute_command", "command_id": command_id, "context": _context_payload(context)},
                    timeout=30.0,
                )
                self._raise_for_error(result)
                return result.get("result")

            register = host_api.register_builtin_command if kind == "builtin" else host_api.register_command
            if not register(id=command_id, title=title, handler=handler, **kwargs):
                raise RuntimeError(f"isolated plugin command registration rejected: {command_id}")

        for descriptor in list(response.get("search_sources") or []):
            if not isinstance(descriptor, dict):
                continue
            source_id = str(descriptor.get("id") or "")

            def search(query: str, source_id: str = source_id):
                result = worker.request(
                    {"operation": "search", "source_id": source_id, "query": query},
                    timeout=5.0,
                )
                self._raise_for_error(result)
                rows = result.get("results")
                return rows if isinstance(rows, list) else []

            before = len(host_api._staged_search_sources)
            host_api.register_search_source(source_id, search)
            if len(host_api._staged_search_sources) == before:
                raise RuntimeError(f"isolated plugin search registration rejected: {source_id}")

        for descriptor in list(response.get("modules") or []):
            if isinstance(descriptor, dict):
                host_api.register_module(
                    str(descriptor.get("id") or ""),
                    str(descriptor.get("manifest_path") or "module.json"),
                )

    @staticmethod
    def _raise_for_error(response: dict[str, Any]) -> None:
        if response.get("status") != "error":
            return
        error = response.get("error")
        message = error.get("message") if isinstance(error, dict) else error
        raise PluginWorkerError(str(message or "isolated plugin worker failed"))

    def unload(self, plugin_id: str) -> None:
        worker = self._workers.pop(plugin_id, None)
        if worker is not None:
            worker.close()

    def snapshot(self) -> dict[str, Any]:
        return {
            plugin_id: {
                "pid": worker.pid,
                "running": worker.running,
                "quarantined": worker.quarantined,
                "capabilities": sorted(worker.negotiated_capabilities),
            }
            for plugin_id, worker in self._workers.items()
        }

    def close(self) -> None:
        for plugin_id in list(self._workers):
            self.unload(plugin_id)
