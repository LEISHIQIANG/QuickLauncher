"""Item execution logic for LauncherPopup."""

import logging
import os
import time

from core.background_tasks import start_background_thread
from core.data_models import ShortcutItem, ShortcutType
from core.i18n import tr
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
        if item.type in (ShortcutType.COMMAND, ShortcutType.CHAIN, ShortcutType.BATCH_LAUNCH, ShortcutType.URL):
            selected_files_for_item = self._take_valid_selected_files_for_click()

        # 检查是否有选中文件需要打开
        files_to_use = []
        if item.type in (ShortcutType.FILE, ShortcutType.FOLDER):
            files_to_use = self._take_valid_selected_files_for_click()

        if files_to_use:
            logger.debug(f"使用Explorer选中文件启动: {item.name}, 文件: {files_to_use}")
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

                input_prompts = collect_input_prompts(
                    f"{item.url or ''} {getattr(item, 'preferred_browser_args', '') or ''}"
                )
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
            except Exception as exc:
                logger.debug("检查命令交互模式失败: %s", exc, exc_info=True)

        runtime_inputs = {}
        if input_prompts:
            try:
                from ui.styles.themed_messagebox import ThemedInputDialog

                for prompt in input_prompts:
                    label = prompt or "输入内容"
                    val, ok = ThemedInputDialog.getText(self, "运行参数", label)
                    if not ok:
                        logger.info("用户取消了运行时参数输入，快捷方式执行终止")
                        return
                    runtime_inputs[prompt] = val
                    if not prompt:
                        runtime_inputs["input"] = val
            except Exception as e:
                logger.error(f"交互式参数收集失败: {e}")

        execute_item = item
        force_close_builtin_direct = False
        destructive_confirmed = False

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
                            except Exception as exc:
                                logger.debug("读取剪贴板文本失败: %s", exc, exc_info=True)

                            selected_files = []
                            try:
                                if selected_files_for_item:
                                    selected_files = list(selected_files_for_item)
                                elif self.__dict__.get("_selected_files_status", "") == "ready":
                                    selected_files = list(self.__dict__.get("_selected_files", []) or [])
                            except Exception as exc:
                                logger.debug("获取选中文件列表失败: %s", exc, exc_info=True)

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
                                        "input_values": dict(runtime_inputs),
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
                                context_meta={"input_values": dict(runtime_inputs)} if runtime_inputs else {},
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
        logger.debug(f"执行: {item.name} (类型: {item.type})")

        force_close_capture_command = (
            item.type == ShortcutType.COMMAND
            and getattr(item, "command_type", "cmd") in ("cmd", "python", "powershell", "bash")
            and bool(getattr(item, "capture_output", False))
            and not bool(getattr(item, "show_window", False))
            and not bool(getattr(item, "run_as_admin", False))
        )
        force_close_param_command = (
            item.type == ShortcutType.COMMAND
            and getattr(item, "command_type", "cmd") in ("cmd", "python", "powershell", "bash")
            and bool(getattr(item, "command_params", []))
        )
        force_close_chain = item.type == ShortcutType.CHAIN
        force_close_batch = item.type == ShortcutType.BATCH_LAUNCH
        should_close = (
            force_close_builtin_direct
            or force_close_capture_command
            or force_close_param_command
            or force_close_chain
            or force_close_batch
            or not self.is_pinned
        )

        if should_close:
            self.hide()

        if force_close_param_command or force_close_capture_command:
            tray_app = getattr(self, "tray_app", None)
            if tray_app is not None and hasattr(tray_app, "show_command_panel"):
                try:
                    context_meta = {}
                    if runtime_inputs:
                        context_meta["input_values"] = dict(runtime_inputs)
                    if selected_files_for_item:
                        context_meta["selected_files"] = list(selected_files_for_item)
                    if tray_app.show_command_panel(
                        shortcut=item, raw_input=item.command or "", context_meta=context_meta
                    ):
                        self._executing = False
                        return
                except Exception:
                    logger.exception("Command panel handoff failed; falling back to worker execution")

        # 在 UI 线程预检查破坏性命令（避免确认流程导致面板被打开）
        if (
            HAS_EXECUTOR
            and ShortcutExecutor
            and item.type == ShortcutType.COMMAND
            and not bool(getattr(item, "capture_output", False))
        ):
            try:
                risks = ShortcutExecutor.command_requires_confirmation(item)
                if risks:
                    from ui.styles.themed_messagebox import ThemedMessageBox

                    risk_lines = "\n".join(f"- {risk.get('message') or risk.get('code')}" for risk in risks)
                    command_text = str(getattr(item, "command", "") or "").strip()
                    message = (
                        "该命令包含不可逆或强破坏性操作，确认后执行。\n\n" f"{risk_lines}\n\n" f"命令: {command_text}"
                    )
                    reply = ThemedMessageBox.question(
                        self,
                        "确认危险命令",
                        message,
                        ThemedMessageBox.Yes | ThemedMessageBox.No,
                    )
                    if reply != ThemedMessageBox.Yes:
                        self._executing = False
                        return
                    destructive_confirmed = True
            except Exception:
                logger.debug("破坏性命令预检查失败", exc_info=True)

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
                                context_meta={
                                    "data_manager": getattr(self, "data_manager", None),
                                    "selected_files": list(selected_files_for_item or []),
                                },
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
                    if force_close_batch:
                        try:
                            from core.batch_launch_exec import execute_batch_launch

                            pending = execute_batch_launch(
                                item,
                                getattr(self, "data_manager", None),
                            )
                            if not getattr(pending, "success", False):
                                self.execution_error.emit(item.name, pending.error or pending.message)
                            return
                        except Exception as exc:
                            logger.exception("Batch launch execution failed")
                            self.execution_error.emit(item.name, str(exc))
                            return
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
                                context_meta={
                                    "input_values": dict(runtime_inputs),
                                    "selected_files": list(selected_files_for_item or []),
                                },
                            )
                            pending, _duration, result_id = service.execute_shortcut_capture_sync(request)
                            if isinstance(getattr(pending, "payload", None), dict):
                                pending.payload["_stored_result_id"] = result_id
                            if hasattr(self, "command_panel_result_ready"):
                                self.command_panel_result_ready.emit(pending, item.id, item.name)
                            return
                        except Exception:
                            logger.exception("命令捕获服务执行失败")
                    runtime_execute_item = execute_item
                    if runtime_inputs or selected_files_for_item or destructive_confirmed:
                        try:
                            from core.command_io import CommandInvocationSnapshot, prepare_runtime_shortcut

                            runtime_execute_item = prepare_runtime_shortcut(
                                execute_item,
                                CommandInvocationSnapshot(
                                    command_id=getattr(execute_item, "id", ""),
                                    command_title=getattr(execute_item, "name", ""),
                                    input_values=dict(runtime_inputs),
                                    selected_files=list(selected_files_for_item or []),
                                    context_meta={"destructive_confirmed": destructive_confirmed},
                                ),
                            )
                        except Exception:
                            logger.debug("构建运行时快捷方式副本失败", exc_info=True)
                    success, error_msg = ShortcutExecutor.execute(runtime_execute_item, force_new)
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

        self._item_execution_thread = start_background_thread(
            name="ItemExecutor",
            target=do_execute_thread,
            owner=self,
        )

    def _should_wait_for_selection(self, item: ShortcutItem, force_new: bool = False) -> bool:
        """Briefly defer execution while the Explorer/Desktop selection probe is still running."""
        if self.__dict__.get("_selected_files_status", "idle") != "pending":
            self.__dict__.pop("_selection_defer_started_at", None)
            return False

        selection_sensitive = item.type in (ShortcutType.FILE, ShortcutType.FOLDER)
        if item.type == ShortcutType.COMMAND:
            from core.command_variables import uses_selected_file_variables

            command = getattr(item, "command", "") or ""
            selection_sensitive = getattr(item, "command_type", "") == "builtin" or uses_selected_file_variables(
                command
            )
        elif item.type == ShortcutType.URL:
            from core.command_variables import uses_selected_file_variables

            url_text = f"{getattr(item, 'url', '') or ''} {getattr(item, 'preferred_browser_args', '') or ''}"
            selection_sensitive = uses_selected_file_variables(url_text)
        elif item.type == ShortcutType.CHAIN:
            selection_sensitive = True
        elif item.type == ShortcutType.BATCH_LAUNCH:
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

        if "_lifecycle_generation" in self.__dict__ and hasattr(self, "_defer_lifecycle_callback"):
            generation = int(self.__dict__.get("_lifecycle_generation", 0) or 0)
            self._defer_lifecycle_callback(
                35,
                self._execute_item_after_selection_probe,
                item,
                force_new,
                generation=generation,
            )
        else:
            QTimer.singleShot(35, lambda: self._execute_item_after_selection_probe(item, force_new))
        return True

    def _execute_item_after_selection_probe(self, item: ShortcutItem, force_new: bool = False):
        if bool(getattr(self, "_closing", False)):
            return
        try:
            if not self.isVisible():
                return
        except RuntimeError:
            return
        except Exception as exc:
            logger.debug("检查弹窗可见状态失败: %s", exc, exc_info=True)
            return
        self._execute_item(item, force_new)

    def _on_execution_error(self, name: str, error: str):
        """启动失败的处理"""
        try:
            from ui.styles.themed_messagebox import ThemedMessageBox

            ThemedMessageBox.critical(
                self.window(), tr("启动失败"), tr("无法启动: {name}\n\n原因: {error}", name=name, error=error)
            )
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
