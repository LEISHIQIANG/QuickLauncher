"""Item execution logic for LauncherPopup."""

import logging
import os
import threading
import time

from core.data_models import ShortcutItem, ShortcutType
from qt_compat import QTimer

logger = logging.getLogger(__name__)

try:
    from core import ShortcutExecutor

    HAS_EXECUTOR = True
except ImportError:
    HAS_EXECUTOR = False


class PopupItemExecutionMixin:
    """Execute shortcut items: commands, URLs, files, with command panel v2 support."""

    def _execute_item(self, item: ShortcutItem, force_new: bool = False):
        """执行项目"""
        if self._executing:
            return

        if self._should_wait_for_selection(item, force_new):
            return

        selected_files_for_item = []
        if item.type in (ShortcutType.COMMAND, ShortcutType.CHAIN):
            selected_files_for_item = self._take_valid_selected_files_for_click()
            if selected_files_for_item:
                try:
                    item._runtime_selected_files = list(selected_files_for_item)
                except Exception:
                    pass

        # 检查是否有选中文件需要打开
        files_to_use = []
        if item.type in (ShortcutType.FILE, ShortcutType.FOLDER):
            files_to_use = self._take_valid_selected_files_for_click()

        if files_to_use:
            logger.info(f"使用Explorer选中文件启动: {item.name}, 文件: {files_to_use}")
            if not self.is_pinned:
                self.hide()
            self._clear_selected_files_context()
            self._execute_drop(item, files_to_use)
            return

        # ===== 优化修复：运行时输入 `{{input}}` 参数收集 =====
        input_prompts = []
        if item.type == ShortcutType.COMMAND and item.command:
            try:
                from core.command_variables import should_expand_command_variables

                command_type = getattr(item, "command_type", "cmd")
                enabled = getattr(item, "command_variables_enabled", None)
                if should_expand_command_variables(command_type, enabled):
                    from core.command_variables import collect_input_prompts

                    input_prompts = collect_input_prompts(item.command)
            except Exception as e:
                logger.error(f"提取命令输入变量失败: {e}")
        elif item.type == ShortcutType.URL and item.url:
            try:
                from core.command_variables import collect_input_prompts

                input_prompts = collect_input_prompts(item.url)
            except Exception as e:
                logger.error(f"提取URL输入变量失败: {e}")

        if input_prompts and item.type == ShortcutType.COMMAND and getattr(item, "command_type", "") == "builtin":
            try:
                from core import registry
                from core.builtin_commands import canonical_builtin_command
                from core.command_registry import COMMAND_INTERACTION_PANEL, _CallbackHandler

                parts = (item.command or "").strip().lstrip("/").split(None, 1)
                cmd_word = parts[0].lower() if parts else ""
                cmd_def = None
                if registry is not None and cmd_word:
                    cmd_def = (
                        registry.get(cmd_word)
                        or registry.get(registry.get_canonical(cmd_word))
                        or registry.get(canonical_builtin_command(cmd_word))
                    )
                if (
                    cmd_def is not None
                    and getattr(cmd_def, "interaction_mode", "") == COMMAND_INTERACTION_PANEL
                    and not isinstance(cmd_def.handler, _CallbackHandler)
                ):
                    input_prompts = []
            except Exception:
                pass

        if input_prompts:
            try:
                from ui.styles.themed_messagebox import ThemedInputDialog

                runtime_inputs = {}
                for prompt in input_prompts:
                    label = prompt or "输入内容"
                    val, ok = ThemedInputDialog.getText(self, "运行参数", label)
                    if not ok:
                        logger.info("用户取消了运行时参数输入，快捷方式执行终止")
                        return
                    runtime_inputs[prompt] = val
                    if not prompt:
                        runtime_inputs["input"] = val
                item._runtime_input_values = runtime_inputs
            except Exception as e:
                logger.error(f"交互式参数收集失败: {e}")

        execute_item = item
        force_close_builtin_direct = False

        # Phase 2: route builtin slash commands by explicit interaction metadata.
        cmd_text = (item.command or "").strip()
        cmd_str = cmd_text.lower()
        if item.type == ShortcutType.COMMAND and item.command_type == "builtin" and cmd_str:
            force_close_builtin_direct = True
            if (
                cmd_text.startswith("/")
                and not (getattr(self, "search_query", "") or "").strip()
                and not bool(self.__dict__.get("_search_execute_from_keyboard", False))
                and hasattr(self, "_set_search_query")
            ):
                try:
                    self._set_search_query(cmd_text)
                except Exception:
                    self.search_query = cmd_text
            try:
                from core import registry
                from core.command_registry import (
                    COMMAND_INTERACTION_PANEL,
                    CommandContext,
                    CommandResult,
                    _CallbackHandler,
                )

                if registry is not None and registry.count() > 0:
                    from core.builtin_commands import canonical_builtin_command

                    command_parts = cmd_text.lstrip("/").split(None, 1)
                    cmd_word = command_parts[0].lower() if command_parts else ""
                    args_text = command_parts[1].strip() if len(command_parts) > 1 else ""
                    canonical = canonical_builtin_command(cmd_word)
                    registry_canonical = registry.get_canonical(cmd_word)
                    command_canonical = canonical or registry_canonical or cmd_word
                    cmd_def = registry.get(cmd_word) or registry.get(registry_canonical) or registry.get(canonical)

                    query = getattr(self, "search_query", "").strip()
                    if query:
                        query_text = query[1:] if query.startswith("/") else query
                        query_parts = query_text.split(None, 1)
                        query_cmd = query_parts[0].lower() if query_parts else ""
                        query_args = query_parts[1].strip() if len(query_parts) > 1 else ""
                        query_canonical = (
                            canonical_builtin_command(query_cmd) or registry.get_canonical(query_cmd) or query_cmd
                        )
                        if query_args and (query_cmd == cmd_word or query_canonical == command_canonical):
                            args_text = query_args

                    if cmd_def is not None:
                        if getattr(cmd_def, "params", None) and "{" in args_text and "}" in args_text:
                            args_text = ""
                        command_to_execute = cmd_def.id
                        if args_text:
                            command_to_execute = f"{command_to_execute} {args_text}"
                        if getattr(cmd_def, "interaction_mode", "") != COMMAND_INTERACTION_PANEL:
                            try:
                                from dataclasses import replace

                                execute_item = replace(item, command=command_to_execute)
                            except Exception:
                                item.command = command_to_execute
                                execute_item = item
                        elif not isinstance(cmd_def.handler, _CallbackHandler):
                            query_for_panel = f"/{cmd_def.id}"
                            if args_text:
                                query_for_panel = f"{query_for_panel} {args_text}"
                            auto_fill_command = not bool(self.__dict__.get("_search_execute_from_keyboard", False))
                            if auto_fill_command and hasattr(self, "_set_search_query"):
                                self._set_search_query(query_for_panel)

                            clipboard_text = ""
                            try:
                                clipboard_text = self._read_clipboard_text()
                            except Exception:
                                pass

                            selected_files = []
                            try:
                                if selected_files_for_item:
                                    selected_files = list(selected_files_for_item)
                                elif self.__dict__.get("_selected_files_status", "") == "ready":
                                    selected_files = list(self.__dict__.get("_selected_files", []) or [])
                            except Exception:
                                pass

                            tray_app = getattr(self, "tray_app", None)
                            if tray_app is not None and hasattr(tray_app, "show_command_panel"):
                                self._launched_app = True
                                self.hide()
                                tray_app.show_command_panel(
                                    command_id=cmd_def.id,
                                    args_text=args_text,
                                    raw_input=query_for_panel,
                                    context_meta={
                                        "clipboard_text": clipboard_text,
                                        "selected_files": selected_files,
                                    },
                                )
                                return

                            def _on_update(update: CommandResult) -> None:
                                self.show_command_result(update, cmd_def.id)

                            ctx = CommandContext(
                                raw_input=query_for_panel,
                                args_text=args_text,
                                clipboard_text=clipboard_text,
                                selected_files=selected_files,
                                update_callback=_on_update,
                            )
                            result = cmd_def.handler(ctx)
                            self.show_command_result(result, cmd_def.id)
                            return
            except Exception as e:
                logger.exception("Panel command handoff failed: %s", e)
            finally:
                if self.__dict__.get("_executing", False):
                    self._executing = False

        self._executing = True
        self._launched_app = True  # 启动外部程序，隐藏时不恢复焦点
        logger.info(f"执行: {item.name} (类型: {item.type})")

        force_close_capture_command = (
            item.type == ShortcutType.COMMAND
            and getattr(item, "command_type", "cmd") in ("cmd", "python", "powershell")
            and bool(getattr(item, "capture_output", False))
            and not bool(getattr(item, "show_window", False))
            and not bool(getattr(item, "run_as_admin", False))
        )
        force_close_param_command = (
            item.type == ShortcutType.COMMAND
            and getattr(item, "command_type", "cmd") in ("cmd", "python", "powershell")
            and bool(getattr(item, "command_params", []))
        )
        force_close_chain = item.type == ShortcutType.CHAIN
        should_close = (
            force_close_builtin_direct
            or force_close_capture_command
            or force_close_param_command
            or force_close_chain
            or not self.is_pinned
        )

        if should_close:
            self.hide()

        if force_close_param_command or force_close_capture_command:
            tray_app = getattr(self, "tray_app", None)
            if tray_app is not None and hasattr(tray_app, "show_command_panel"):
                try:
                    if tray_app.show_command_panel(shortcut=item, raw_input=item.command or ""):
                        self._executing = False
                        return
                except Exception:
                    logger.exception("Command panel handoff failed; falling back to worker execution")

        # 使用线程执行，避免阻塞 UI
        def do_execute_thread():
            try:
                if HAS_EXECUTOR and ShortcutExecutor:
                    if force_close_chain:
                        try:
                            from core.command_execution_service import CommandExecutionRequest, CommandExecutionService
                            from core.command_results import CommandResultStore

                            tray_app = getattr(self, "tray_app", None)
                            result_store = (
                                getattr(tray_app, "command_result_store", None) if tray_app is not None else None
                            )
                            if tray_app is not None and result_store is None:
                                result_store = CommandResultStore()
                                tray_app.command_result_store = result_store
                            service = CommandExecutionService(result_store)
                            request = CommandExecutionRequest(
                                command_id=item.id,
                                raw_input=item.name or item.id,
                                source="shortcut_chain",
                                shortcut=item,
                                context_meta={"data_manager": getattr(self, "data_manager", None)},
                            )
                            pending, _duration, result_id = service.execute_shortcut_chain_sync(request)
                            if isinstance(getattr(pending, "payload", None), dict):
                                pending.payload["_stored_result_id"] = result_id
                            # chain_result_window="none" 时不显示结果面板
                            crw = getattr(item, "chain_result_window", "medium")
                            if crw != "none" and hasattr(self, "command_panel_result_ready"):
                                self.command_panel_result_ready.emit(pending, item.id, item.name)
                            return
                        except Exception:
                            logger.exception("Action chain service execution failed")
                    if force_close_capture_command:
                        try:
                            from core.command_execution_service import CommandExecutionRequest, CommandExecutionService
                            from core.command_results import CommandResultStore

                            tray_app = getattr(self, "tray_app", None)
                            result_store = (
                                getattr(tray_app, "command_result_store", None) if tray_app is not None else None
                            )
                            if tray_app is not None and result_store is None:
                                result_store = CommandResultStore()
                                tray_app.command_result_store = result_store
                            service = CommandExecutionService(result_store)
                            request = CommandExecutionRequest(
                                command_id=item.id,
                                raw_input=item.command or "",
                                source="shortcut",
                                shortcut=item,
                            )
                            pending, _duration, result_id = service.execute_shortcut_capture_sync(request)
                            if isinstance(getattr(pending, "payload", None), dict):
                                pending.payload["_stored_result_id"] = result_id
                            if hasattr(self, "command_panel_result_ready"):
                                self.command_panel_result_ready.emit(pending, item.id, item.name)
                            return
                        except Exception:
                            logger.exception("命令捕获服务执行失败")
                    success, error_msg = ShortcutExecutor.execute(execute_item, force_new)
                    had_pending_result = False
                    try:
                        from core.command_registry import take_pending_command_result

                        pending = take_pending_command_result()
                        if pending is not None and hasattr(self, "command_panel_result_ready"):
                            had_pending_result = True
                            self.command_panel_result_ready.emit(pending, item.id, item.name)
                    except Exception:
                        logger.debug("读取命令捕获结果失败", exc_info=True)
                    if not success and error_msg and not had_pending_result:
                        self.execution_error.emit(item.name, error_msg)
                else:
                    if item.target_path:
                        try:
                            os.startfile(item.target_path)
                        except Exception as e:
                            self.execution_error.emit(item.name, str(e))
            except Exception as e:
                logger.error(f"执行失败: {e}")
                self.execution_error.emit(item.name, str(e))
            finally:
                self._executing = False

        threading.Thread(target=do_execute_thread, daemon=True, name="ItemExecutor").start()

    def _should_wait_for_selection(self, item: ShortcutItem, force_new: bool = False) -> bool:
        """Briefly defer execution while the Explorer/Desktop selection probe is still running."""
        if self.__dict__.get("_selected_files_status", "idle") != "pending":
            self.__dict__.pop("_selection_defer_started_at", None)
            return False

        selection_sensitive = item.type in (ShortcutType.FILE, ShortcutType.FOLDER)
        if item.type == ShortcutType.COMMAND:
            command = getattr(item, "command", "") or ""
            selection_sensitive = (
                getattr(item, "command_type", "") == "builtin"
                or "{{selected_file" in command
                or "{{selected_files" in command
            )
        elif item.type == ShortcutType.CHAIN:
            selection_sensitive = True

        if not selection_sensitive:
            return False

        now = time.monotonic()
        started = float(self.__dict__.get("_selection_defer_started_at", 0.0) or 0.0)
        if started <= 0.0:
            started = now
            self.__dict__["_selection_defer_started_at"] = started

        if now - started >= 0.25:
            self.__dict__.pop("_selection_defer_started_at", None)
            return False

        QTimer.singleShot(35, lambda: self._execute_item(item, force_new))
        return True

    def _on_execution_error(self, name: str, error: str):
        """启动失败的处理"""
        try:
            from ui.styles.themed_messagebox import ThemedMessageBox

            ThemedMessageBox.critical(self.window(), "启动失败", f"无法启动: {name}\n\n原因: {error}")
        except Exception as e:
            logger.error(f"显示错误弹窗失败: {e}")

    def _on_command_panel_result_ready(self, result, command_id: str, command_title: str):
        """Show captured command output in the independent command panel."""
        tray_app = getattr(self, "tray_app", None)
        if tray_app is not None and hasattr(tray_app, "show_command_panel"):
            try:
                if getattr(tray_app, "command_result_store", None) is None:
                    from core.command_results import CommandResultStore

                    tray_app.command_result_store = CommandResultStore()
                payload = getattr(result, "payload", {}) if isinstance(getattr(result, "payload", {}), dict) else {}
                result_id = str(payload.get("_stored_result_id") or "")
                if not result_id:
                    result_id = tray_app.command_result_store.add(
                        result,
                        command_id=command_id,
                        command_title=command_title,
                        raw_input=payload.get("command", ""),
                        source="shortcut",
                        duration=payload.get("duration", 0.0),
                    )
                if tray_app.show_command_panel(result_id=result_id):
                    return
                logger.warning("Command panel did not open; falling back to popup command result")
            except Exception:
                logger.exception("显示命令面板结果失败")
        if hasattr(self, "show_command_result"):
            self.show_command_result(result, command_id)
