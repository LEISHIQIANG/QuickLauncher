# QuickLauncher Full Documentation

[简体中文](README.md) | [English](README_EN.md) | [完整文档](README_FULL.md)

QuickLauncher is a Windows 10 / 11 desktop quick launcher and lightweight automation tool. It centers on a global popup and brings app launch, files, folders, URLs, hotkeys, commands, action chains, batch launch groups, and local plugins into one searchable surface.

The current source version is defined in [core/version.py](core/version.py): `1.6.3.1`, release status `stable`. Installer and portable builds ship the runtime. Source runs and builds require 64-bit CPython 3.12.

## Table Of Contents

- [1. Capability Overview](#1-capability-overview)
- [2. Install And Run](#2-install-and-run)
- [3. Popup Trigger And Search](#3-popup-trigger-and-search)
- [4. Shortcut Model](#4-shortcut-model)
- [5. Command System](#5-command-system)
- [6. Action Chains](#6-action-chains)
- [7. Batch Launch](#7-batch-launch)
- [8. Plugins](#8-plugins)
- [9. Settings, Themes, And UI](#9-settings-themes-and-ui)
- [10. Global Hooks And Input Recording](#10-global-hooks-and-input-recording)
- [11. Data, Safety, And Updates](#11-data-safety-and-updates)
- [12. Build, Tests, And CI](#12-build-tests-and-ci)
- [13. Project Structure](#13-project-structure)
- [14. Maintenance Rules](#14-maintenance-rules)

## 1. Capability Overview

| Area | Current capability |
|---|---|
| Popup entry | Middle mouse by default; configurable keyboard, mouse, or hybrid trigger; separate special-app trigger profile |
| Search | Fuzzy matching, Chinese Pinyin full/initial search, aliases, tags, web search prefixes, plugin search sources |
| Shortcuts | 7 types: FILE, FOLDER, URL, HOTKEY, COMMAND, CHAIN, BATCH_LAUNCH |
| Commands | CMD, PowerShell, Python, Git Bash, built-in commands; templates, parameter forms, captured output, result actions |
| Built-in commands | 33 commands for developer tools, network diagnostics, system tools, plugin management, and maintenance |
| Action chains | Visual canvas, node links, parameter binding, node snapshots, cancel support, 189 built-in processors |
| Plugins | `.qlzip` installation, hot loading, enable/disable, failure quarantine, permissions, built-in commands, search sources, chain processors, persistent workers |
| Hooks | Native `hooks.dll` for low-level mouse/keyboard hooks, Raw Input fallback, RegisterHotKey, macro recording/playback |
| Data safety | Atomic saves, config backups, history snapshots, import sanitization, path traversal defense, controlled URL access |
| Release safety | GitHub Releases, Ed25519 release signatures, SHA-256 verification, trusted installer path checks |

## 2. Install And Run

### 2.1 Release Packages

Download from [GitHub Releases](https://github.com/LEISHIQIANG/QuickLauncher/releases):

- `QuickLauncher_Setup_<version>.exe`: installer package built with Inno Setup.
- `QuickLauncher_Portable_<version>.zip`: portable package, run `QuickLauncher.exe` after extraction.

Release packages include QuickLauncher runtime dependencies. End users do not need a system Python installation.

### 2.2 Run From Source

```powershell
git clone https://github.com/LEISHIQIANG/QuickLauncher.git
cd QuickLauncher
py -3.12 -m pip install -r requirements.txt
py -3.12 main.py
```

Source runs require:

- Windows 10 / 11 x64.
- CPython 3.12.
- Runtime dependencies from `requirements.txt`: PyQt5, pywin32, Pillow, psutil, pynput, watchdog, qrcode, and related packages.

### 2.3 Runtime Modes

```powershell
py -3.12 main.py
py -3.12 main.py --safe-mode
py -3.12 main.py --safe-mode --smoke-test
py -3.12 main.py --plugin-helper <script.py> --plugin-site <site-packages> -- ...
```

`--safe-mode` disables plugins, hooks, update checks, and custom backgrounds for troubleshooting. `--plugin-helper` is the controlled child-process entry used by packaged builds to load plugin-bundled Python libraries.

## 3. Popup Trigger And Search

### 3.1 Triggers

The default trigger is the middle mouse button. Settings can configure:

| Field | Meaning |
|---|---|
| `popup_trigger_mode` | Normal trigger mode: `mouse`, `keyboard`, `hybrid` |
| `popup_trigger_button` | Mouse button: `left`, `right`, `middle`, `x1`, `x2` |
| `popup_trigger_keys` | Main keyboard keys |
| `popup_trigger_modifiers` | Modifiers: `ctrl`, `alt`, `shift`, `win` |
| `popup_special_trigger_*` | Separate trigger profile for special apps, default Ctrl+middle |

The special-app list covers CAD, 3D modeling, and graphics software. Mouse triggers use the window under the pointer. Keyboard triggers use the foreground window.

Double-tap Alt pauses or resumes triggers. While paused, middle mouse, keyboard triggers, and special triggers do not open the popup.

### 3.2 Popup Behavior

- Popup alignment: mouse center, mouse top-left, screen center, bottom-right.
- Pinned popup mode with drag movement.
- Optional auto-close on mouse leave.
- Optional new popup when triggering again while pinned.
- Tab switches between title bar and search bar defaults.
- Dock supports one, two, or three rows.

### 3.3 Search Sources

Search merges:

- User shortcut names, aliases, and tags.
- Chinese Pinyin full and initial matching.
- Built-in command aliases.
- Web search prefixes.
- Plugin search sources.
- System icon and command entries.

Typing `/` opens built-in command browsing. Command aliases can also execute directly.

## 4. Shortcut Model

QuickLauncher currently supports 7 shortcut types. The data model lives in [core/data_models.py](core/data_models.py).

| Type | Purpose | Key fields |
|---|---|---|
| `file` | Launch app or open file | `target_path`, `target_args`, `working_dir`, `run_as_admin` |
| `folder` | Open folder | `target_path`, `run_as_admin` |
| `url` | Open URL | `url`, `preferred_browser_path`, `preferred_browser_args` |
| `hotkey` | Send keyboard shortcut | `hotkey_modifiers`, `hotkey_key`, `hotkey_keys` |
| `command` | Run shell or built-in command | `command`, `command_type`, `command_params`, `capture_output` |
| `chain` | Run action chain | `chain_steps`, `chain_canvas`, `chain_data`, `module_id` |
| `batch_launch` | Launch a group in order | `batch_launch_steps`, `module_id` |

Common fields include `name`, `enabled`, `tags`, `alias`, `icon_path`, `order`, `use_count`, `smart_order`, and `trigger_mode`.

### 4.1 Command Shortcuts

Supported `command_type` values:

- `cmd`
- `powershell`
- `python`
- `bash`
- `builtin`

Commands can use variable templates, output capture, timeout limits, output length limits, parameter forms, environment variables, and encoding options. The default command timeout is 10 seconds. The default output cap is 20,000 characters.

### 4.2 URL Shortcuts

URL shortcuts can use the default browser or a specified browser with arguments. URL templates can include runtime values such as `{{input}}` and selected-file variables. URL latency probing uses a controlled request path and avoids blocking the UI thread.

### 4.3 Privilege-Aware Launching

Files, folders, URLs, and commands can request administrator launch. If QuickLauncher itself is elevated and the target does not need elevation, launch routes through Explorer's standard-user token so child apps are not tied to QuickLauncher privilege or process lifetime. Installer/update cleanup stops QuickLauncher itself only and does not kill programs launched by it.

## 5. Command System

### 5.1 Registration

Commands go through `CommandRegistry`:

- Legacy slash commands remain as a compatibility layer.
- New built-ins are registered from [core/builtin_command_catalog.py](core/builtin_command_catalog.py).
- Plugin commands are indexed by owner and removed when the plugin unloads.
- Plugin built-in commands use a `plugin-builtin:<plugin_id>` source.

There are currently 33 built-in command definitions:

| Command | Title | Category | Purpose |
|---|---|---|---|
| `uuid` | UUID | developer | Generate UUID / GUID |
| `timestamp` | Timestamp | developer | Current Unix timestamp |
| `base64` | Base64 | developer | Encode / decode Base64 |
| `urlencode` | URL Encoding | developer | Encode / decode URL text |
| `color` | Color | developer | HEX/RGB/RGBA conversion |
| `ip` | IP | network | Local and public IP lookup |
| `copy-path` | Copy Path | system | Copy current path |
| `hash` | Hash | developer | File hash with MD5/SHA1/SHA256/SHA512 |
| `qr` | QR Code | developer | Generate QR code |
| `json` | JSON Tool | developer | Format, minify, validate JSON |
| `jwt` | JWT Decode | developer | Decode header and payload without signature validation |
| `netdiag` | Network Diagnostics | network | DNS, TCP port, and ping latency checks |
| `cidr` | CIDR Calculator | network | Network, mask, broadcast, usable range |
| `tls` | TLS Certificate Check | network | Protocol, issuer, expiry, SAN |
| `path-audit` | PATH Audit | developer | Invalid paths, duplicates, command shadowing |
| `process` | Process Analysis | system | Top processes, search, terminate PID |
| `sysreport` | System Snapshot | system | CPU, memory, disk, network, uptime |
| `plugin-list` | Plugin List | plugin | List loaded plugins |
| `plugin-reload` | Reload Plugin | plugin | Reload plugins |
| `plugin-new` | New Plugin | plugin | Create plugin template |
| `wifi` | Wi-Fi Passwords | system | Inspect saved Wi-Fi profiles |
| `hosts` | Edit Hosts | system | Open hosts edit path |
| `port` | Port Usage | developer | Query port usage, optional kill |
| `dns` | Flush DNS | network | Flush Windows DNS cache |
| `clean-cache` | Clean Cache | internal | Clean project temporary cache |
| `config-repair` | Config Repair | system | Scan/fix old variable syntax |
| `explorer` | Restart Explorer | system | Safely restart Windows Explorer |
| `conflict` | Hotkey Conflict Check | system | Check shortcut conflicts and occupied keys |
| `git` | Git | developer | status, branch, log, diff, fetch, pull, checkout |
| `selected` | Selected Text | system | Show selected-text details |
| `clip` | Clipboard | system | Show clipboard content and type |
| `env` | Environment Variables | system | Open Windows environment variable editor |
| `god` | God Mode | system | Open the God Mode folder |

### 5.2 Parameters And Results

Command parameter fields include `name`, `type`, `required`, `default`, `choices`, `label`, `placeholder`, `help`, `source`, `validator`, `remember`, `sensitive`, and `advanced`. Sensitive parameters are not persisted in history.

Command handlers return `CommandResult`:

- `success` / `message` / `error`
- `display_type`
- `payload`
- `actions`

The result panel supports copy, open URL, open file/folder, and similar action buttons.

### 5.3 Variable Templates

Common variables:

| Variable | Meaning |
|---|---|
| `{{clipboard}}` | Clipboard text |
| `{{input}}` | Runtime input |
| `{{date}}` / `{{time}}` / `{{datetime}}` | Current date/time |
| `{{lan_ip}}` / `{{wan_ip}}` | Local / public IP |
| `{{selected_file}}` | Current selected file |
| `{{selected_files}}` | Current selected files |
| `{{selected_file_name}}` | Selected file name |
| `{{selected_file_dir}}` | Selected file directory |
| `{{app_dir}}` | Application directory |
| `{{config_dir}}` | Configuration directory |

Command and URL editors highlight variable templates. Commands support safe quoting semantics such as `:q` to avoid inserting external values unquoted.

### 5.4 Preprocessing And Risk Checks

The preprocessing pipeline covers:

1. Syntax.
2. Semantics.
3. Security scan.
4. Business rules.
5. Audit log.

Settings control preprocessing, strict mode, audit logging, rate limiting, dangerous pattern blocking, and variable quoting requirements.

## 6. Action Chains

Action chains are the `chain` shortcut type provided by built-in module `quicklauncher.action_chain`. The module manifest is [modules/action_chain/module.json](modules/action_chain/module.json).

### 6.1 Capabilities

- Visual canvas with compatibility for legacy step data.
- Nodes can reference shortcuts or processors.
- Parameter binding, input binding, per-step enable/disable, stop-on-error, delays.
- Node-level snapshots during execution.
- Cancel support and configurable result window size.
- Recursive chain and batch launch references are blocked.

### 6.2 Processors

There are currently 189 built-in processors. Main categories:

- Text, formatting, regex.
- Math, advanced math, lists, sets, dictionaries.
- JSON, HTTP, URL, network tools.
- Files and paths.
- Date and time.
- Encoding/decoding, hash, compression.
- Validation.
- System info and environment variables.
- Image operations.
- Input/debug and logic control.

Dangerous processors declare safety metadata. File writes, downloads, and Python cell execution require confirmation or explicit capability.

## 7. Batch Launch

Batch launch is a dedicated `batch_launch` shortcut type. It is no longer modeled as an action chain. It launches multiple existing targets in order and fits work-start setups, project tool groups, and repeatable troubleshooting bundles.

The runtime:

- Skips disabled items.
- Blocks references to itself, action chains, and other batch launch entries when they would recurse.
- Reuses normal shortcut execution paths.
- Respects per-step delay limits.

## 8. Plugins

### 8.1 Distribution Model

QuickLauncher no longer preinstalls official plugin source folders into the runtime. The current model is:

- `.plugins/`: official `.qlzip` packages in the source repo.
- `plugins/`: runtime plugin installation directory.
- Release builds include an empty `plugins/` directory and `PLUGIN_DEV.md`, not source plugin folders.
- Installing a `.qlzip` package unpacks it into `plugins/<plugin_id>/`.

### 8.2 Official Plugin Packages

| Package | Description | Permission highlights |
|---|---|---|
| `api_tester.qlzip` | HTTP API tester with request methods and formatted responses | `network.request` |
| `disk_cleaner.qlzip` | Directory size analysis, safe recycle/cache/temp cleanup | `file.read`, `file.write`, `process.run`, `admin.required` |
| `event_inspector.qlzip` | Windows Event Log search and aggregation | `file.read`, `process.run` |
| `file_tools.qlzip` | Copy selected-file paths and file hash | `clipboard.write`, `file.read` |
| `network_tools.qlzip` | Ping and DNS lookup | `network.request`, `process.run` |
| `process_tools.qlzip` | Process ranking and name/PID lookup | no high-risk permission |
| `qr_code_scanner.qlzip` | Screenshot QR-code recognition with copy/open actions | `builtin.command`, `clipboard.write`, `open.url`, `process.run` |
| `screenshot_ocr.qlzip` | Screenshot OCR with command-panel result | `builtin.command`, `file.read`, `clipboard.write`, `process.run` |
| `startup_tools.qlzip` | Startup audit and PATH health check | `file.read` |
| `text_tools.qlzip` | Text reverse/count/case conversion | `clipboard.read`, `clipboard.write` |

### 8.3 Plugin API

Plugin entry files expose `register(api)` from `main.py`. Common APIs:

- `register_command(...)`
- `register_builtin_command(...)`
- `register_search_source(...)`
- `register_module(...)`
- `register_chain_processor(...)`
- `read_clipboard()` / `write_clipboard(...)`
- `get_selected_files()`
- `open_url(...)` / `open_file(...)` / `open_folder(...)`
- `read_text_file(...)` / `write_data_file(...)`
- `http_request(...)`
- `run_process_capture(...)`
- `prewarm_persistent_helper(...)`
- `request_persistent_helper(...)`
- `stop_persistent_helper(...)`
- `launch_target(...)`
- `run_command(...)`

Plugin handlers run on the shared thread pool. The soft timeout is 30 seconds. Repeated failures can place a plugin into quarantine.

### 8.4 Package Limits

`.qlzip` installation validates:

- `plugin.json` is present.
- Plugin ID uses only lowercase letters, numbers, hyphen, underscore.
- Path traversal and encrypted ZIP members are rejected.
- File count limit: 1000.
- Uncompressed size limit: 150 MB.
- Overwrite install backs up the existing plugin and rolls back on failure.

Plugins currently run in compatible in-process mode. Permission declarations are risk notices and controlled API boundaries, not full process isolation. Install only trusted plugins.

## 9. Settings, Themes, And UI

Settings come from `AppSettings`:

- Theme: dark, light, follow system.
- Background: theme, image, solid color, Acrylic.
- Popup: opacity, icon size, cell size, columns, radius, max rows, position, auto-close, pinned multi-open.
- Dock: enabled, opacity, height mode.
- Global UI scale: 90%-150%.
- Windows 11 color filters: black point, white point, gamma, temperature, Acrylic, background alpha, separately for dark/light.
- Windows 10: synchronized companion shadow window for popup show/move/opacity/animation.
- Command management: favorites and disabled built-ins.
- Plugin management: install, enable, disable, reload, development mode.
- Data: import/export, share-safe export, backups, config history.
- Support/about: version, diagnostics, help.

## 10. Global Hooks And Input Recording

Global input is provided by [hooks/hooks.dll](hooks/hooks.dll). C++ sources live in [hooks_dll/](hooks_dll/).

### 10.1 Runtime Path

- Low-level mouse hook handles middle mouse and five-button mouse input.
- Low-level keyboard hook handles combinations, Alt double-tap, hotkey capture.
- Raw Input is the fallback when low-level hooks miss events or are removed by Windows.
- Single-key keyboard triggers prefer `RegisterHotKey`.
- The Python layer loads the DLL via `ctypes`, owns diagnostics, lifecycle, and Qt main-thread bridging.

### 10.2 Reliability Rules

- Low-level callbacks return quickly; Python callbacks run through an async queue.
- Callback queues are bounded to avoid blocking hook threads.
- Runtime popup triggers are suppressed while recording so capture does not immediately trigger the launcher.
- Hotkey capture, protected chord capture, and macro capture share session ownership; only one capture session can run at a time.
- Before DLL release, Python checks that hooks, playback, and capture are quiescent. On timeout, DLL and callback references are kept until process exit to avoid native crashes.

### 10.3 Macro Support

The hook DLL supports:

- Unified keyboard and mouse event recording.
- Vertical and horizontal wheels.
- Mouse movement traces.
- Key down/up events.
- Unicode input.
- Async mixed macro playback, cancel, wait, status.
- Releasing still-pressed inputs after playback end or cancel.

## 11. Data, Safety, And Updates

### 11.1 Data Locations

Source runs usually store data under repository `config/`. Installer/portable runs use the app directory root:

- `config/data.json`
- `config/icon_repo.json`
- `config/config_history/`
- `config/auto_backups/`
- `plugins/`
- `temp_icons/`

User icon repository and system icons are separate. System icons come from [assets/system_icons/config.json](assets/system_icons/config.json).

### 11.2 Configuration Safety

- Config saves are atomic.
- Imports sanitize types, ranges, colors, string lengths, list lengths, and trigger settings.
- Shortcut types must be one of the current 7 values.
- Config history keeps recoverable snapshots.
- Diagnostics can scan missing icons, invalid paths, duplicates, URLs, and command risks.

### 11.3 Path And Network Safety

- Plugin installation uses `resolve_under` and safe relative path checks.
- `.qlzip` rejects path traversal, duplicate paths, encrypted files, and oversized packages.
- HTTP processors and plugin HTTP API use controlled URL access and block localhost, private, link-local, and reserved addresses.
- Favicon and URL latency probes use bounded reads.

### 11.4 Auto Update

The default update source is GitHub Releases:

- Repository: `LEISHIQIANG/QuickLauncher`
- Latest release API: `https://api.github.com/repos/LEISHIQIANG/QuickLauncher/releases/latest`

Update flow:

1. Read latest release.
2. Compare versions.
3. Resolve installer URL, size, and SHA-256.
4. Validate URL, hash, and release signature.
5. Download into a controlled directory.
6. Launch installer.

The trust chain includes Ed25519 release signatures and SHA-256 verification. Missing public keys or validation failures fail closed.

## 12. Build, Tests, And CI

### 12.1 Local Gate

```powershell
py -3.12 -m pip install -r requirements.txt -r requirements-dev.txt
py -3.12 scripts/release_gate.py --skip-smoke
```

`scripts/release_gate.py` runs:

1. `ruff check --no-cache core ui hooks services tests`
2. `pytest` with coverage over `core`, `services`, `hooks`, fail-under 67
3. `scripts/audit_broad_exceptions.py --exclude-dir plugins --exclude-dir tools --max-total 1373 --max-unlogged 300`
4. `compileall core ui hooks services bootstrap plugins`
5. `scripts/check_release_artifacts.py --source-only --allow-source-runtime-plugins`
6. `scripts/post_package_smoke.py`

CI runs on Windows with Python 3.12. It executes `release_gate.py --skip-tests --skip-smoke`, a focused pytest subset, and `mypy --follow-imports=skip services/update`.

### 12.2 Build Release Artifacts

```powershell
scripts\build_win11_setup.bat
```

Build requirements:

- 64-bit CPython 3.12.
- Nuitka.
- PyQt5.
- MSVC/MinGW64-capable toolchain.
- Inno Setup 6.
- `hooks/hooks.dll` present, or build it first with `hooks_dll/build.bat`.

Outputs:

- `dist/QuickLauncher_Setup_<version>.exe`
- `dist/QuickLauncher_Portable_<version>.zip`
- `dist/QuickLauncher_release_<version>.json`
- `dist/QuickLauncher_Setup_<version>.sha256`
- `dist/QuickLauncher_Portable_<version>.sha256`

Release artifact verification checks the EXE, hook DLL, plugin directory policy, installer, portable ZIP, and smoke test.

### 12.3 Hook DLL Build

```powershell
cd hooks_dll
build.bat
```

The script compiles `hooks.cpp` through Visual Studio / Build Tools MSVC and the Windows SDK, writing `hooks/hooks.dll`.

## 13. Project Structure

```text
QuickLauncher/
├── main.py                         # app entry, single instance, safe-mode, plugin-helper, smoke-test
├── core/                           # data, execution, commands, plugins, action chain, safety, update logic
│   ├── builtin_command_catalog.py   # 33 built-in command definitions
│   ├── command_registry.py          # command registry and CommandResult
│   ├── data_models.py               # ShortcutItem, AppSettings, AppData
│   ├── plugin_manager.py            # plugin scan, install, load, quarantine, PluginAPI
│   ├── shortcut_command_exec.py     # command execution and output capture
│   ├── shortcut_executor.py         # file/folder/URL/hotkey/chain/batch dispatch
│   ├── shortcut_chain_exec.py       # action-chain runtime
│   ├── batch_launch_exec.py         # batch-launch runtime
│   ├── chain/                       # chain processor definitions and execution
│   └── plugin/                      # plugin package install, paths, constants
├── modules/
│   └── action_chain/                # action-chain module entry and manifest
├── ui/                              # PyQt5 UI, popup, settings, command panel, themed components
├── hooks/                           # hooks.dll Python wrapper and compatibility layers
├── hooks_dll/                       # native hook DLL source and build script
├── services/update/                 # update check, download, trust validation, UI
├── bootstrap/                       # startup tasks, dependencies, logging, IPC, venv helpers
├── assets/                          # icons, system icons, resources
├── .plugins/                        # official .qlzip plugin packages
├── plugins/                         # runtime plugin directory and plugin development guide
├── scripts/                         # build, release gate, artifact checks, installer script
├── tests/                           # pytest suite
└── .github/                         # CI and GitHub templates
```

## 14. Maintenance Rules

- Version metadata comes from [core/version.py](core/version.py). Installer script, manifest, and release metadata must match it.
- Before release, run `py -3.12 scripts/release_gate.py --skip-smoke`.
- After packaging-policy changes, run `scripts/check_release_artifacts.py --source-only --allow-source-runtime-plugins`.
- After plugin API or official package changes, update [plugins/PLUGIN_DEV.md](plugins/PLUGIN_DEV.md) and `.plugins/README.md`.
- After hook DLL changes, update [hooks_dll/README.md](hooks_dll/README.md) and verify DLL version/capabilities match the Python wrapper.
- After system icon schema changes, update [assets/system_icons/README.md](assets/system_icons/README.md).
- Documentation counts should come from code or package manifests: 7 shortcut types, 33 built-ins, 189 action-chain processors, 10 official plugin packages.

---

> QuickLauncher - Efficiency at your fingertips.
