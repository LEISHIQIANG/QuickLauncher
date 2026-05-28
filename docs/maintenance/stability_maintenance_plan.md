# QuickLauncher Stability Maintenance Plan

This directory contains version-controlled maintenance documents. Drafts and local notes should stay outside this path, for example under `docs/_drafts/`.

## Current Priorities

- Keep destructive command confirmation narrow: only irreversible delete, disk/boot modification, formatting, and critical registry deletion require execution confirmation.
- Treat administrator execution, shell execution, PowerShell, and network use as audit or warning metadata unless they combine with destructive behavior.
- Keep configuration import transactional: preview before import when requested, and roll back in-memory changes plus copied assets on failure.
- Keep diagnostics export redacted by default and include redaction counts.
- Keep release metadata derived from `core/version.py` and verified in CI.
- Keep shell execution paths listed in the command execution audit table with reason, input source and mitigation.
- Keep runtime limits centralized in `core/runtime_constants.py` so models, action chains and health checks do not drift.
- Keep command profile/env value preparation in `core/command_exec/profiles.py`; `shortcut_command_exec.py` remains the compatibility facade for execution flow.
- Keep Bash fallback wrapper generation, exit marker parsing and completion polling in `core/command_exec/bash_fallback.py`; marker content, not file existence, is the completion signal.
- Keep `DataManager` as the compatibility facade. Internal config responsibilities now live behind `ConfigDataStore`, `ConfigBackupService`, `ConfigRecoveryService`, `ConfigPackageService`, `ConfigImporter` and `ConfigHistoryManager`; future work should extend those services instead of adding more file I/O to `DataManager`.
- Keep command definitions annotated with metadata from `core/command_metadata.py` for risk, administrator needs, network access, system modification and confirmation.
- Keep built-in command registration data in `core/builtin_command_catalog.py`, and move focused command handler groups such as maintenance commands out of the large `core/commands.py` facade.
- Keep plugin management built-ins in `core/commands_plugins.py`; `core.commands` should only re-export them for compatibility.
- Keep Windows utility built-ins such as environment editor and God Mode launchers in `core/commands_windows.py`; `core.commands` should only re-export them for compatibility.
- Keep Git built-ins in `core/commands_git.py`; long-running Git calls must have bounded timeouts and terminate the child process before surfacing timeout diagnostics.
- Keep process and system snapshot built-ins in `core/commands_system.py`; tolerate per-process access failures and keep kill/sysreport failure paths visible.
- Keep command profile parsing and formatting in `ui/config_window/command_profile_helpers.py`; `CommandDialog` should delegate to these helpers instead of growing more non-UI parsing logic.
- Keep icon-grid drag ordering in `ui/config_window/icon_grid_ordering.py` so reorder rules can be tested without constructing Qt widgets.
- Keep folder-panel drag/drop policy and MIME parsing in `ui/config_window/folder_panel_helpers.py`; `FolderPanel` should remain focused on widget state and signals.
- Guard delayed popup UI callbacks with lifecycle generation tokens, and stop popup timers during hide/close so stale callbacks do not mutate closed windows.
- Guard config-window delayed callbacks through `WindowLifecycleController`, and explicitly stop settings-page debounce timers before the config window closes.
- Run release artifact checks after packaging; missing exe, hooks DLL, assets, plugins, installer or hashes must fail the build.

## Required Checks

- `python -m compileall -q services core hooks ui tests main.py`
- `python -m ruff check core/ hooks/ services/ scripts/ tests/ ui/ main.py`
- `python -m ruff format --check core/ hooks/ services/ scripts/ tests/ ui/ main.py`
- `python scripts/check_release_artifacts.py --source-only`
- `python -m pytest tests/ -q --cov=core --cov=ui --cov=services --cov=hooks --cov-report=term-missing --cov-fail-under=35`
