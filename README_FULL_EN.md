# QuickLauncher Full Documentation

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-yellow.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20|%2011-lightgrey.svg)](https://www.microsoft.com/windows)

[简体中文](README.md) | [English](README_EN.md) | [完整文档](README_FULL.md) | [Full Docs](README_FULL_EN.md)

QuickLauncher is a **Windows desktop quick launcher** built with **Python + PyQt5**. Press the middle mouse button to summon the launcher panel, quickly start programs, open files/folders/URLs, execute commands, and send hotkeys. It supports Pinyin search, a plugin system, and bilingual (Chinese/English) UI. It aims to provide the lightest possible access to your most frequently used tools, putting efficiency at your fingertips.

---

## Table of Contents

- [Core Features Overview](#core-features-overview)
- [Launcher Popup System](#1-launcher-popup-system)
- [Shortcut System](#2-shortcut-system)
- [Command System and Slash Commands](#3-command-system-and-slash-commands)
- [Command Variables and Template Engine](#4-command-variables-and-template-engine)
- [Command Preprocessing Pipeline](#5-command-preprocessing-pipeline)
- [Command Risk Assessment](#6-command-risk-assessment)
- [Action Chain (CHAIN)](#7-action-chain-chain)
- [Configuration Window](#8-configuration-window)
- [System Tray](#9-system-tray)
- [Global Hooks and Hotkey System](#10-global-hooks-and-hotkey-system)
- [Theme and Visual System](#11-theme-and-visual-system)
- [Plugin System](#12-plugin-system)
- [Data Management and Security](#13-data-management-and-security)
- [Auto-Update System](#14-auto-update-system)
- [Internationalization (i18n)](#15-internationalization-i18n)
- [Performance and Stability](#16-performance-and-stability)
- [Project Structure](#17-project-structure)
- [Tech Stack](#18-tech-stack)
- [Getting Started](#getting-started)
- [Development Guide](#development-guide)
- [Contributing](#contributing)
---

## Core Features Overview

| Dimension | Capability |
|-----------|------------|
| **Trigger Methods** | Middle mouse button global summon, Alt double-click to pause/resume, CAD/3D software compatibility mode |
| **Shortcut Types** | 6 types: FILE (file/app), FOLDER (folder), URL (web address), HOTKEY (hotkey), COMMAND (command), CHAIN (action chain) |
| **Search Capabilities** | Fuzzy matching, Pinyin search (full Pinyin + initials), alias/tag search, Web search engine prefixes, plugin-extended search sources |
| **Command System** | CMD / PowerShell / Python / Git Bash / Built-in command modes, 50+ built-in commands, command variable templates, output capture, 5-layer security preprocessing |
| **Action Chains** | Up to 50 sequential steps, inter-step data passing, error interruption control, cancellable execution |
| **Appearance** | Dark/light themes, frosted glass acrylic effect, custom image backgrounds, configurable icons/grid/columns |
| **Plugins** | Permission management, hot load/unload, .qlzip packaging and installation, custom command and search source registration |
| **Data** | Atomic save, auto-backup, configuration history (20 snapshots), full backup/restore ZIP, shareable config export, automatic config corruption recovery |
| **Security** | 5-layer command preprocessing pipeline, path boundary validation for directory traversal prevention, SSRF protection (Favicon fetching), command variable injection protection, ZIP bomb protection, symbolic link rejection |
| **Multilingual** | Chinese (Simplified) / English bilingual, runtime switching |
| **Auto-Update** | GitHub Releases source, Ed25519 release signatures, SHA-256 verification, background download, skip version, silent install |

---

## 1. Launcher Popup System

### 1.1 Summon and Dismiss

- **Middle Mouse Button**: Press the middle mouse button anywhere on the desktop to summon the launcher panel. The popup follows the mouse position and supports multi-monitor DPI-aware coordinate conversion.
- **Alt Double-Click**: Quickly press the Alt key twice to toggle the middle mouse button pause/resume state (when paused, the middle button no longer triggers the popup).
- **Escape**: Clears the search box content; press Escape again to close the popup.
- **Click Outside**: The popup automatically closes (except in pinned mode).

### 1.2 Popup Visuals

- **Frameless Window**: Uses `Qt.FramelessWindowHint`, combined with Windows DWM API for frosted glass acrylic effect.
- **Windows 10 / 11 Compatible**: Windows 10 uses `WS_EX_LAYERED` layered windows; Windows 11 uses `DwmSetWindowAttribute` for rounded corners and dark title bars.
- **Three Background Modes**:
  - **Follow Theme**: Automatically matches dark/light theme color
  - **Image Background**: User selects a background image, automatically blurred
  - **Acrylic Background**: System-level frosted glass blur effect
- **Adjustable Transparency**: Background transparency configurable from 0-255, supports real-time adjustment via `Ctrl + Scroll Wheel`.
- **Animations**: 100ms transparency fade + reveal progress animation for popup/dismiss, sliding animation for category switching.

### 1.3 Search System

Type directly after the popup opens to search. Search matching follows this priority:

1. **Web Search Engine Prefixes**: Type `g keyword` to open Google search, `b` for Baidu, `y` for Yandex, `e` for Bing.
2. **Slash Commands**: Type `/` to enter command mode, fuzzy matching all registered commands.
3. **Local Shortcuts**: Fuzzy matching on names, aliases, and tags.
4. **Pinyin Search**: Supports full Pinyin and initial abbreviation matching (e.g., typing `kb` matches "keyboard" in Chinese).
5. **Plugin Search Sources**: Plugins can register custom search sources that participate in the popup search.

### 1.4 Icon Grid

- **Configurable Grid**: Icon size 16-64px, grid cell size 32-80px, columns 3-12.
- **Category Tabs**: Shortcuts organized by folders (categories), with a tab bar at the top, supporting scroll wheel pagination.
- **Keyboard Operation**: Arrow keys to select, Enter to execute, Escape to clear/close.
- **Drag and Drop Support**: Drag to reorder icons, drag external files to create shortcuts, drag shortcuts to other categories.
- **Pin Mode**: Pinning the popup keeps it visible, with support for opening up to 2 additional popup windows.

### 1.5 Dock Bar

- Independent Dock panel displaying pinned frequently-used shortcuts.
- Resident at the bottom or side of the popup for one-click access to high-frequency tools.

### 1.6 Inline Command Result Display

Command execution results can be rendered directly within the popup:

- **Display Types**: Text, tables, key-value pairs, progress bars, QR codes, color blocks.
- **Selectable Text**: `QTextEdit` overlay supports `Ctrl+C` copy, `Ctrl+A` select all.
- **Action Buttons**: Copy, open URL, open file/folder, save text, save file, create shortcut, close QR code server.
- **Favorite/Star**: Supports bookmarking command results.
- **QR Code**: Supports QR code generation with smart clipboard detection (URLs open directly, file paths start a local HTTP file server for mobile scanning and download).

### 1.7 Quick Operations

| Operation | Description |
|-----------|-------------|
| Middle Mouse Button | Show/hide popup |
| Direct Input | Search shortcuts |
| Enter | Execute search result |
| Escape | Clear search / close popup |
| Arrow Keys | Navigate pages or select search results |
| Alt + Left Click | Force launch in new process |
| Ctrl + Scroll Wheel | Adjust background transparency |
| Shift + Scroll Wheel | Adjust icon transparency |

---

## 2. Shortcut System

QuickLauncher supports **6 shortcut types**, each with its own configuration dialog:

### 2.1 FILE — File/Application

Launch applications, open files or folders.

- **Target Path**: Supports automatic `.lnk` shortcut resolution (COM `IShellLink` interface or PowerShell fallback)
- **Launch Arguments**: Command-line argument passing
- **Working Directory**: Custom working directory
- **Run as Admin**: Configurable administrator launch
- **Window Activation**: If the target is already running, automatically brings the existing window to the foreground (instead of launching a duplicate)
- **Permission Matrix**: Four-quadrant permission handling — normal->normal, normal->admin, admin->normal (via Explorer Token downgrade channel), admin->admin

### 2.2 FOLDER — Folder

Open a folder and display it in Explorer.

- Supports selecting a specific file within the folder
- Supports linking physical folders for automatic synchronization

### 2.3 URL — Web Address

Open a URL in the browser.

- **Auto-Complete**: Automatically prepends `https://` prefix
- **Custom Browser**: Can specify browser path and launch arguments
- **Variable Support**: URLs support `{{clipboard}}`, `{{date}}`, `{{time}}`, and other variables
- **Latency Test**: Tests URL reachability via HEAD/GET requests, results color-coded (green/yellow/red)
- **Safe Scheme Whitelist**: Only allows `http`, `https`, `file`, `mailto`, `tel`, `ms-settings`, `steam`, `vscode`, `obsidian`; blocks dangerous schemes like `javascript`, `data`, `vbscript`
- **Automatic Favicon Fetching**: Automatically fetches website icons and caches as 512x512 PNG (with SSRF protection, DNS Rebinding detection, SVG sanitization)

### 2.4 HOTKEY — Hotkey

Send keyboard combinations to the current window.

- **Key Recording**: Visual recording of key combinations
- **Modifier Key Differentiation**: Distinguishes left/right Ctrl, Alt, Shift
- **Trigger Modes**:
  - `immediate`: Trigger immediately
  - `after_close`: Close panel first, restore original window focus, then trigger
- **Supported Keys**: All standard modifier keys, function keys, arrow keys, special keys (Tab, Enter, Esc, Space, etc.)
- **Implementation**: Prioritizes Windows `SendInput` API + scan code mapping, with `pynput` as fallback

### 2.5 COMMAND — Command

Execute commands with five runtime options.

- **Command Subtypes**:
  - `cmd`: Windows CMD Shell commands (default)
  - `powershell`: PowerShell script execution
  - `python`: Python script execution
  - `git_bash`: Git Bash command execution
  - `builtin`: Built-in application commands
- **Execution Modes**:
  - **Silent Mode** (`show_window=False`): Background execution, `/c` closes window
  - **Show Window** (`show_window=True`): Shows CMD window, `/k` keeps window open
- **Output Capture**: Optional stdout/stderr capture, supports streaming updates (150ms throttle), cancellable, timeout control (default 10s), output truncation (default 20000 characters)
- **Encoding Detection**: Auto-detects OEM code page -> preferred encoding -> gbk -> utf-8 -> utf-16 -> cp437 fallback chain
- **Parameterized**: Supports defining command parameters (text, dropdown selection, boolean, file selection, folder selection)
- **Environment Variables**: Configurable custom environment variables
- **Multi-line Commands**: Multi-line CMD commands are automatically wrapped in a temporary `.cmd` file for execution

### 2.6 CHAIN — Action Chain

See [Chapter 7: Action Chain](#7-action-chain-chain).

---

## 3. Command System and Slash Commands

### 3.1 Command Registration Architecture

QuickLauncher has a unified command registration system `CommandRegistry`:

- **Registration Deduplication**: Rejects duplicate IDs
- **Alias Mapping**: Case-insensitive alias lookup
- **Category Index**: Commands organized by category
- **Fuzzy Search**: Exact match -> prefix match -> substring match, searching across id, title, description, category, aliases, search_terms
- **Plugin Commands**: Indexed by owner, automatically cleaned up on plugin unload

### 3.2 Complete Built-in Command List

#### Application Control

| Command | Alias | Function |
|---------|-------|----------|
| `/quit` | `quit_app` | Quit application |
| `/restart` | `restart_app` | Restart application |
| `/log` | `show_log` | View runtime log |
| `/about` | `show_about` | About dialog |
| `/help` | `show_help` | Help information |

#### Window Management

| Command | Alias | Function |
|---------|-------|----------|
| `/topmost` | `pin`, `toggle_topmost` | Toggle window topmost |
| `/pin-on` | `topmost_on` | Force enable topmost |
| `/pin-off` | `unpin`, `topmost_off` | Force disable topmost |

#### Configuration and Diagnostics

| Command | Alias | Function |
|---------|-------|----------|
| `/config` | `show_config_window` | Open configuration window |
| `/diagnostics` | `zhenduan` | Diagnostics center |
| `/shortcut-health` | `health`, `icons` | Shortcut and icon health check |
| `/config-history` | `peizhi lishi` | View configuration change history |
| `/clean-icon-cache` | `icon-cache` | Clean icon cache |
| `/clean-cache` | `qingli huan cun` | Clean project cache (`__pycache__`, `pytest_cache`, etc.) |
| `/reload-hooks` | `hooks`, `chongzhuang gouzi` | Reload global hooks |

#### Windows System Shortcuts

| Command | Alias | Function |
|---------|-------|----------|
| `/control` | `open_control_panel` | Control Panel |
| `/thispc` | `open_this_pc` | This PC |
| `/recycle` | `open_recycle_bin` | Recycle Bin |
| `/taskmgr` | `task-manager`, `renwu guanliqi` | Task Manager |
| `/ms-settings` | `windows设置` | Windows Settings |
| `/services` | `services.msc`, `fuwu` | Services Management Console |
| `/devmgmt` | `devmgmt.msc`, `shebei guanliqi` | Device Manager |
| `/diskmgmt` | `diskmgmt.msc`, `cipan guanli` | Disk Management |
| `/ncpa` | `ncpa.cpl`, `wangluo lianjie` | Network Connections |
| `/startup` | `shell-startup`, `qidong wenjianjia` | Startup Folder |
| `/msinfo32` | `systeminfo`, `xitong xinxi` | System Information |

#### Internal Path Shortcuts

| Command | Alias | Function |
|---------|-------|----------|
| `/config-file` | `data.json` | Open config file in Notepad |
| `/icons-dir` | `图标目录` | Open icons directory |
| `/history-dir` | `历史目录` | Open history directory |
| `/auto-backups` | `备份目录` | Open auto-backup directory |
| `/error-log` | `错误日志` | Open error log in Notepad |
| `/data-dir` | `数据目录` | Open application data directory |
| `/install-dir` | `安装目录` | Open installation directory |

#### Developer/DevOps Tool Commands

| Command | Alias | Function |
|---------|-------|----------|
| `/urlencode` | `bianma`, `jiema` | URL encode/decode |
| `/color` | — | HEX to RGB/RGBA color values |
| `/ip` | — | View local IP (`local`/`public` mode) |
| `/copy-path` | — | Copy selected file path from Explorer (`name`/`dir`/full path) |
| `/hash` | — | File hash calculation (MD5/SHA1/SHA256) |
| `/uuid` | — | Generate UUID v4 |
| `/timestamp` | — | Current Unix timestamp / timestamp to date |
| `/base64` | — | Base64 encode/decode (256KB limit) |
| `/qr` | — | Generate QR code (smart clipboard detection: URL->open link, file->HTTP file server) |
| `/json` | — | JSON pretty-print/minify/validate (`pretty`/`min`/`validate`) |
| `/jwt` | — | Decode JWT Token (Header + Payload) |
| `/netdiag` | — | Network diagnostics (DNS resolution, TCP port connectivity, Ping) |
| `/cidr` | — | CIDR subnet calculator (network/mask/broadcast/host range, IPv4 & IPv6) |
| `/tls` | — | TLS certificate check (protocol version, issuer, validity, SAN) |
| `/path-audit` | `PATH 体检` | PATH environment variable audit (invalid directories/duplicates/shadow commands) |
| `/wifi` | `wlan`, `无线密码` | List saved Wi-Fi networks and query plaintext passwords |
| `/hosts` | — | Open hosts file as administrator |
| `/port` | `netstat` | Find processes using ports, supports `kill` to terminate |
| `/dns` | `flushdns` | Flush DNS cache |
| `/env` | — | Open environment variable editor |
| `/git` | `git-status`, `git-pull` | Git operations (status/branch/log/diff/fetch/pull/checkout) |
| `/process` | — | Process viewer (sort by memory/CPU, search, kill) |
| `/sysreport` | — | System snapshot (platform, CPU, memory, disk, network, battery) |
| `/plugin list` | — | List all loaded plugins |
| `/plugin reload` | — | Reload plugins |
| `/plugin new` | — | Create new plugin from template |
| `/conflict` | `冲突` | Hotkey conflict detection (internal duplicates, system shortcuts, Windows global hotkey registration) |
| `/god` | — | Open Windows God Mode |
| `/explorer` | — | Restart Windows Explorer |

---

## 4. Command Variables and Template Engine

Command shortcuts support `{{variable_name}}` syntax for dynamic substitution. Use `{{{{` and `}}}}` to escape literal braces.

> **Note**: The legacy single-brace `{variable_name}` syntax is deprecated and automatically migrated to double-brace `{{variable_name}}` on config load.

### 4.1 Variable List

| Variable | Description | Example Output |
|----------|-------------|----------------|
| `{{clipboard}}` | Current clipboard text | `Hello World` |
| `{{selected_text}}` | Selected text in foreground window (`after_close` mode) | Selected content |
| `{{selected_file}}` | First selected Explorer file, preserving the existing single-file behavior | `C:\file1.txt` |
| `{{selected_file_name}}` | File name of the first selected file | `file1.txt` |
| `{{selected_file_dir}}` | Parent directory of the first selected file | `C:\work` |
| `{{selected_files}}` | All selected Explorer files, newline-delimited when unquoted | `C:\file1.txt` |
| `{{selected_files:q}}` | All selected Explorer files, each safely quoted for the active command type | `"C:\file 1.txt" C:\file2.txt` |
| `{{date}}` | Current date | `2026-05-27` |
| `{{time}}` | Current time | `14:30:00` |
| `{{app_dir}}` | Application installation directory | `C:\Program Files\QuickLauncher` |
| `{{config_dir}}` | Configuration directory | `<app_dir>\config` |
| `{{input}}` | Runtime user input (no prompt) | User-entered content |
| `{{input:prompt_text}}` | Runtime user input (with prompt) | User-entered content |
| `{{param:parameter_name}}` | Command parameter value | Custom value |
| `{{chain:variable_name}}` | Variable passed from action chain | Previous step output |
| `{{lan_ip}}` | Local default outbound IPv4 address | `192.168.1.100` |
| `{{wan_ip}}` | Public IPv4 address | `203.0.113.1` |

### 4.2 Safe Quoting (`:q` Suffix)

To prevent command injection, when using external input variables in CMD/PowerShell/Bash type commands, you **must** add the `:q` suffix for safe quoting:

```
echo {{clipboard:q}}        ✅ Safe: auto-escaped
echo {{input:filename:q}}    ✅ Safe: auto-escaped
echo {{clipboard}}           ❌ Dangerous: execution will be rejected
```

- The system automatically detects unquoted external variables and rejects execution, prompting the correct `{{name:q}}` syntax
- External input maximum 1MB, Null bytes automatically stripped
- Pure variable commands (e.g., `{{clipboard}}` alone as a command) are recognized and rejected — because it's just a string, not an executable command

### 4.3 Escape Syntax

Use `{{{{` and `}}}}` to output literal braces, e.g.:

```
echo {{{{date}}}}           → Output: {{date}} (not expanded)
echo {{{{clipboard:q}}}}    → Output: {{clipboard:q}} (not expanded)
```

---

## 5. Command Preprocessing Pipeline

Commands pass through a 5-layer security preprocessing pipeline before execution. Layers execute sequentially, and any layer can short-circuit and terminate.

### 5.1 Pipeline Stages

| Layer | Name | Function |
|-------|------|----------|
| 1 | Syntax Validation | Input sanitization, command length check (max 10000 characters) |
| 2 | Semantic Validation | Verify command type, check if working directory exists, ensure required parameters are non-empty |
| 3 | Security Scan | Injection detection, variable quoting check, path safety, dangerous pattern matching |
| 4 | Business Rules | Rate limiting by shortcut ID |
| 5 | Audit Log | Log validation failures and security warnings |

### 5.2 Security Scan Capabilities

- **Command Injection Detection**: Identifies dangerous characters like `;`, `&`, `|`, `<`, `>`, `` ` `` and chained patterns (`&&`, `||`)
- **Dangerous Pattern Matching**: 40+ regex patterns covering file deletion, disk formatting, registry operations, process termination, credential theft, lateral movement, defense evasion, etc.
- **Path Traversal Protection**: Rejects `..` in paths, validates paths are within allowed root directories
- **Variable Quoting Enforcement**: External input variables must use the `:q` suffix
- **Environment Variable Validation**: Detects dangerous `LD_PRELOAD`-style hijacking variables

### 5.3 Pipeline Configuration

The pipeline can be adjusted through settings:

| Configuration Item | Description |
|--------------------|-------------|
| `enabled` | Whether to enable the preprocessing pipeline |
| `strict_mode` | Strict mode — security warnings cannot be overridden |
| `rate_limiting` | Enable rate limiting |
| `audit_enabled` | Enable audit logging |
| `block_dangerous_patterns` | Block dangerous pattern matches |
| `require_variable_quoting` | Enforce variable quoting |
| `raw_mode` | Skip variable quoting checks (advanced users) |

---

## 6. Command Risk Assessment

Before executing a command, the system automatically assesses the risk level and prompts the user, but does not block execution.

### 6.1 Information-Level Prompts

| Risk Code | Trigger Condition |
|-----------|-------------------|
| `run_as_admin` | Running as administrator |
| `shell_command` | Executing through system Shell (CMD type) |
| `clipboard_variable` | Using clipboard variable |
| `selected_text_variable` | Using selected text variable |

### 6.2 Warning-Level Prompts

| Risk Code | Match Pattern | Description |
|-----------|---------------|-------------|
| `delete_tree` | `rmdir /s`, `rd /s`, `rd /q` | Recursive directory deletion |
| `delete_file` | `del /f`, `del /q`, `del /s`, `erase` | File deletion |
| `format_disk` | `format [drive]:` | Disk formatting |
| `shutdown` | `shutdown /s`, `/r`, `/g`, `/p` | Shutdown/restart |
| `registry_delete` | `reg delete` | Delete registry entries |
| `powershell_remove` | `Remove-Item`/`rm` + `-Recurse`/`-Force` | PowerShell force delete |
| `powershell_exec_policy` | `Set-ExecutionPolicy` / `-ExecutionPolicy Bypass` | Bypass execution policy |
| `service_control` | `sc delete/stop/start` / `net delete/stop/start` | Service control |
| `diskpart` | `diskpart`, `bcdedit`, `bootrec` | Disk/boot configuration |
| `takeown_icacls` | `takeown` / `icacls` + `/grant`, `/reset`, `/f` | Modify ownership/ACL |
| `cmd_chain_delete` | `cmd /c del` / `cmd /k rd` | Chained deletion |
| `taskkill_force` | `taskkill /f` | Force terminate process |

---

## 7. Action Chain (CHAIN)

Action chains allow chaining multiple shortcuts for sequential execution, suitable for automation workflows.

### 7.1 Step Structure

Each step contains:

| Field | Description |
|-------|-------------|
| `shortcut_id` | Target shortcut ID |
| `enabled` | Whether this step is enabled |
| `stop_on_error` | Whether to interrupt the chain on failure (default `True`) |
| `delay_ms` | Delay before execution (0-60000ms) |
| `use_previous_output` | Use previous step's output as the current step's `{{input}}` |

### 7.2 Execution Mechanism

- Maximum **50 steps**, with circular reference prevention (rejects nested chains and self-references)
- After each step, chain variables are collected: `{{N.success}}`, `{{N.exit_code}}`, `{{N.stdout}}`, `{{N.stderr}}`, `{{N.output}}`, and `prev.*` shortcuts
- Supports **cancellation** (`threading.Event`)
- Inter-step delays support cancellation-aware sleep
- Returns a list-type `CommandResult` displaying all step statuses and durations

### 7.3 Typical Scenarios

```
Chain: Deployment Check
  Step 1: /git status           → Check Git status
  Step 2: /git pull             → Pull latest code (delay 2000ms)
  Step 3: Execute test command   → Pass previous step output
  Step 4: /sysreport            → Generate system report
```

---

## 8. Configuration Window

### 8.1 Opening Methods

- Left-click on system tray icon
- Type `/config` in the popup
- Tray right-click menu -> Settings

### 8.2 Window Features

- Frameless design + frosted glass acrylic effect
- Custom title bar (supports dragging, themed settings gear icon)
- Status bar: Admin status indicator (red=admin, green=normal, purple=code mode), Windows version, app version
- 240ms slide-in animation

### 8.3 Shortcut Management (Launcher View)

- **Visual Editor**: Folder panel + icon grid
- **Right-Click Menu**: Edit, delete, move, copy
- **Ctrl/Shift Multi-Select**: Batch delete, move, enable, disable, undo
- **Start Menu/Desktop Scan**: Auto-discover installed applications
- **Icon Repository**: Merged display of system icons bundled with the software and user's own icon repository, with support for copying to regular categories for editing
- **Drag and Drop Sorting**: Drag to reorder icons and categories
- **System Icon Protection**: System icons bundled with the software cannot be edited/deleted/disabled

### 8.4 Settings Panel (Settings)

The settings panel is navigated via a sidebar and contains the following pages:

#### Appearance

- Background mode switching (Follow Theme / Image Background / Acrylic Background)
- Image background file selection
- Layout configuration: icon size (16-64px), grid cell size (32-80px), columns (3-12)
- Theme switching (dark/light)

#### Popup Behavior

- Popup alignment mode, hover leave delay, auto-close, pin multi-open, double-click interval, etc.

#### System

- **Auto-Start on Boot**: Implemented via Windows Task Scheduler (not registry Run key, more reliable)
- **Show Settings Window on Startup**
- **Hardware Acceleration**: Elevate process priority
- **Hide Tray Icon** (still accessible via `/config` command)
- **Light Sleep Mode**: Reduce resource usage after 10 seconds of idle
- **Log Control**: Disable logging / enable debug logging
- **Auto-Update Check**
- **Sort Mode**: Custom sort vs. Smart sort (based on usage count and recency)

#### Command Management

- Command-related settings

#### Plugin Management

- Enable/disable installed plugins

#### Data

- **Full Configuration Backup/Restore**: ZIP containing data.json + icons + background images
- **Shareable Config Export**: Exports only hotkeys/URLs/commands, automatically hides sensitive paths
- **Factory Reset**: Clear registry keys, icon cache, app data, reset to default configuration
- **Configuration History Browser**: 20 compressed JSON snapshots with one-click restore

#### Support / About

- Help links, version info, acknowledgments

### 8.5 Shortcut Edit Dialogs

Each shortcut type has its own edit dialog:

| Dialog | Edit Content |
|--------|--------------|
| **ShortcutDialog** | FILE/FOLDER: name, target path, arguments, working directory, icon, tags, run as admin |
| **UrlDialog** | URL: name, URL, custom browser, icon |
| **CommandDialog** | COMMAND: name, command text, type (CMD/PowerShell/Python/Git Bash/Built-in), parameters, environment variables, encoding, timeout, output capture |
| **HotkeyDialog** | HOTKEY: name, key combination recording, trigger mode |
| **ChainDialog** | CHAIN: step list, per-step configuration (target, delay, error handling, data passing) |

---

## 9. System Tray

### 9.1 Tray Icon

- Custom icon displayed in Windows system tray
- Tooltip: `QuickLauncher\nLeft=Settings | Middle=Launcher`
- Left-click/Double-click: Open configuration window
- Right-click: Pop up custom menu (frosted glass effect + inline submenus)

### 9.2 Tray Menu

| Menu Item | Function |
|-----------|----------|
| Settings | Open configuration window |
| Restart | Restart application (VBS script mechanism) |
| Runtime Log | Open log viewer |
| Diagnostics Center | Open diagnostics window |
| Exit | Quit application |

### 9.3 Background Services

The tray application runs the following background timers:

| Timer | Interval | Function |
|-------|----------|----------|
| Settings Sync | 120ms debounce | Sync settings changes |
| Memory Check | 120s | Run `MemoryGuard` memory optimization |
| Process Check | 10s | Monitor CAD/3D and other special application processes |
| Deferred Init | 10ms | Pre-initialize popup, preload icons, initialize folder watching |

---

## 10. Global Hooks and Hotkey System

### 10.1 C++ Hook DLL

QuickLauncher uses a custom **C++ DLL** (`hooks/hooks.dll`) for global mouse and keyboard hooks, based on the Win32 `SetWindowsHookEx` API:

- **Mouse Hook**: Globally captures `WM_MBUTTONDOWN` (middle mouse button), triggers the popup
- **Keyboard Hook**: Captures Alt key double-click, toggles middle button pause/resume state
- **Dedicated Thread Management**: Hooks run on a separate thread, synchronized via Ready Event
- **Mutex Protection**: Shared data such as the special application list is protected by mutex

### 10.2 Special Application Compatibility

Built-in list of 35+ CAD/3D applications (AutoCAD, Revit, 3ds Max, Blender, Maya, SolidWorks, CATIA, etc.). When these applications are detected running:

- Middle mouse button trigger is changed to **Ctrl + Middle Button** to avoid conflicts with CAD/3D software's own middle-button operations (such as pan, rotate)
- Process status is monitored every 10 seconds, and hooks are automatically reinstalled when special applications are detected

### 10.3 Python Fallback

When the DLL is unavailable, automatically falls back to Python/system API implementation for hook functionality.

### 10.4 Hotkey Conflict Detection

The `/conflict` command scans for:

- Internal duplicate hotkeys
- Conflicts with Windows system shortcuts
- Windows global hotkey registration collisions (detected via Windows API)

### 10.5 Alt Double-Click Pause

Quickly press the Alt key twice to toggle the middle mouse button enabled/paused state. When paused:

- The middle mouse button no longer triggers the popup
- Press Alt double-click again to resume

---

## 11. Theme and Visual System

### 11.1 Design Language

Adopts an Apple-style design system with a complete color palette:

- Primary, secondary, accent colors
- Background, surface, card colors
- Text colors (primary/secondary/tertiary)
- Border, divider, shadow colors
- Status colors (success/warning/error/info)
- Complete dark/light color palettes

### 11.2 Theme Modes

- **Dark Theme** (default): Dark background + light text
- **Light Theme**: Light background + dark text
- One-click switching in settings panel

### 11.3 Frosted Glass Effect

- Based on Windows DWM API (`dwmapi.dll`)
- `DwmExtendFrameIntoClientArea` extends client area into the border
- Windows 11 rounded corners controlled via `DWMWA_WINDOW_CORNER_PREFERENCE`
- Dark title bar implemented via `DWMWA_USE_IMMERSIVE_DARK_MODE`

### 11.4 Custom Styled Components

- **Buttons**: primary / secondary / danger / ghost variants
- **Input Fields**: Focus state animations
- **Scrollbars**: Thin rounded design
- **Dropdowns**: Custom arrows
- **Group Boxes**: Title decorations
- **Sliders**: Custom handles
- **Popup Menus**: Frosted glass background, inline submenus, hover highlight animation, rounded corners, icon support

### 11.5 Background Customization

| Mode | Description |
|------|-------------|
| Follow Theme | Automatically matches current dark/light theme |
| Image Background | Select local image, automatic Gaussian blur processing |
| Acrylic Background | System-level frosted glass blur effect |

Each mode can independently configure transparency, blur radius, and edge opacity.

---

## 12. Plugin System

### 12.1 Plugin Architecture

- Plugins reside in the `plugins/` directory, one subdirectory per plugin
- Entry file `main.py` + manifest file `manifest.json`
- Dynamically loaded using `importlib`
- Supports hot load/unload

### 12.2 Plugin API

Plugins receive a `PluginAPI` object providing the following capabilities:

| Method | Description |
|--------|-------------|
| `register_command(def)` | Register slash command to CommandRegistry |
| `register_search_source(name, cb)` | Register custom search source to popup |
| `read_clipboard()` / `write_clipboard(text)` | Clipboard read/write |
| `get_selected_files()` | Get selected files in Explorer |
| `launch_target(target)` | Launch file/URL |
| `run_command(command_id)` | Execute another registered command |

### 12.3 Permission Management

Plugins declare required permissions in `manifest.json`:

| Permission | Description | Risk Level |
|------------|-------------|------------|
| `clipboard.read` | Read clipboard | Normal |
| `clipboard.write` | Write clipboard | Normal |
| `file.read` | Read file | Normal |
| `file.write` | Write file | **High Risk** |
| `open.url` | Open URL | Normal |
| `open.file` | Open file | Normal |
| `process.run` | Execute process | **High Risk** |
| `network.request` | Network request | Normal |
| `admin.required` | Requires administrator privileges | **High Risk** |

High-risk permissions require explicit user authorization.

### 12.4 Transactional Registration

- Commands are collected first, then committed atomically
- Automatic rollback of all commands on batch registration failure
- Indexed by owner, automatically cleaned up on plugin unload

### 12.5 .qlzip Packaging and Installation

- Plugins can be packaged as `.qlzip` files (standard ZIP archive)
- Installation flow: Backup existing plugin -> Extract -> Manifest validation
- Security measures: Path traversal protection, symbolic link rejection

### 12.6 Built-in Plugins

| Plugin | Function |
|--------|----------|
| **process_tools** | Process list, terminate, management |
| **startup_tools** | Startup item management |
| **file_tools** | File operation tools |
| **event_inspector** | Windows event viewer |
| **disk_cleaner** | Disk cleanup tools |
| **api_tester** | HTTP API testing tool |
| **network_tools** | Network diagnostics tools |
| **text_tools** | Text processing (reverse, count, case conversion) |

---

## 13. Data Management and Security

### 13.1 Data Storage

Configuration data is stored in `config/data.json` with the following structure:

```json
{
  "version": "2.5",
  "settings": { ... },
  "folders": [
    {
      "id": "dock",
      "name": "Dock",
      "is_dock": true,
      "items": [ ... ]
    },
    {
      "id": "default",
      "name": "常用",
      "items": [ ... ]
    }
  ]
}
```

The user's own icon repository is stored separately in `icon_repo.json` in the same directory; system icons bundled with the software come from `assets/system_icons/config.json`:

```json
{
  "version": "1.0",
  "items": [ ... ]
}
```

### 13.2 Data Security Mechanisms

| Mechanism | Description |
|-----------|-------------|
| **Atomic Save** | Write to temporary file then `os.replace()` to replace, preventing data corruption from crashes |
| **Dual Lock** | Memory lock (`RLock`) + I/O lock separation, avoiding deadlocks |
| **Throttled Save** | 500ms debounce, batch rapid changes trigger only one disk write |
| **Batch Update** | `batch_update()` context manager for transactional multi-operation |
| **Auto Backup** | Automatic backup before each save, retaining latest 5 copies (with timestamps) |
| **Configuration History** | Up to 20 compressed JSON snapshots, with one-click restore to any historical version |
| **Config Corruption Recovery** | Automatic recovery from latest backup when `data.json` is corrupted, generating a recovery report |

### 13.3 Configuration Repair and Recovery

Each time the configuration is loaded on startup, the system automatically performs:

- **Syntax Migration**: Legacy single-brace `{clipboard}` automatically upgraded to `{{clipboard}}`
- **Unknown Variable Detection**: Identifies unregistered variables and reports them, without breaking custom content
- **Corruption Isolation**: Corrupted configuration files are automatically isolated, recovered from the latest 5 auto-backups
- **Recovery Report**: Recovery details written to `recovery/` directory, including status, reason, and path

### 13.4 Backup and Restore

- **Full Backup**: ZIP containing data.json + icons + background images
- **Shareable Export**: Exports only hotkeys/URLs/command types, automatically hides sensitive paths (such as local file paths), supports extracting icons from EXE/DLL
- **Factory Reset**: Clear registry keys, icon cache, app data, reset to default AppData
- **Icon Path Redirection**: When fixing a missing icon path, automatically redirects other missing icons in the same directory
- **Import Security**: ZIP imports validate path traversal, file size limits, background/icon path whitelists

### 13.5 Path Security (path_security)

| Function | Description |
|----------|-------------|
| `resolve_existing(path)` | Safe path resolution (supports `~` expansion) |
| `is_safe_child(root, candidate)` | Verify path is within root directory |
| `resolve_under(root, candidate)` | Throws `UnsafePathError` when path is out of bounds |
| `safe_rmtree_child(root, target)` | Safe deletion (confirmed child paths only, rejects symbolic links) |

Applied in ZIP import, cache cleanup, factory reset scenarios to prevent directory traversal attacks.

### 13.6 Secure Favicon Fetching

- Blocks requests to localhost, internal IPs, loopback addresses, etc. (anti-SSRF)
- DNS resolution check defends against DNS Rebinding attacks
- Redirect limit of 5 hops, each hop validates the target
- SVG sanitization: removes `<script>`, `<foreignObject>`, `<image>` and external `href`
- File size limits: icons 5MB, HTML 1MB, Manifest/SVG 512KB
- Image pixel limit: 16 megapixels

### 13.7 Icon Cache Cleanup

- Removes EXE/DLL files (should not be cached as icons)
- Removes oversized files (>10MB)
- Removes orphaned icons not referenced by any shortcut
- Removes duplicate icons by content hash (MD5 detection)
- Supports dry-run mode to preview cleanup effects

### 13.8 Smart Sort

Automatic sorting based on `use_count` (usage count) and `last_used_at` (recent usage time), but **does not override the user's manually dragged custom order**.

---

## 14. Auto-Update System

### 14.1 Data Sources

- **Primary**: GitHub Releases API (`LEISHIQIANG/QuickLauncher`)
- **Fallback**: Generic API endpoint
- Automatically extracts SHA-256 hash from Release Body or Asset Digest
- Ed25519 release signatures are required by default; missing public keys make update validation fail closed

### 14.2 Update Flow

```
Startup -> UpdateChecker background check (enabled by default)
         ↓
    New version found -> Pop up UpdateNotification dialog
         ↓
    Release signature verification -> URL and hash validation
         ↓
    User choice: Download / Skip this version
         ↓
    Download -> Real-time progress events -> SHA-256 verification
         ↓
    Install -> Launch Inno Setup installer (/VERYSILENT)
         ↓
    Exit current process, installer completes the update
```

### 14.3 Security Measures

| Measure | Description |
|---------|-------------|
| HTTPS Enforcement | Only HTTPS downloads allowed |
| Allowed Host Whitelist | Validates download URL host |
| Ed25519 Release Signature | Verifies release signatures with configured public keys; empty keys fail closed |
| SHA-256 Verification | Verify file hash after download |
| Size Validation | Content-Length check + max 200MB limit |
| Temporary Files | Uses temporary files + atomic rename |
| Trusted Directory | Validates installer is within a trusted directory during installation |

### 14.4 Configuration

- Auto-update toggle (System settings page)
- Skip version record (`.update_state.json`)
- Signature public keys (an empty configuration disables updates instead of bypassing verification)
- Checks once per startup after enabled (not continuous polling)

---

## 15. Internationalization (i18n)

### 15.1 Supported Languages

| Language | Identifier |
|----------|------------|
| Chinese (Simplified) | `zh_CN` (default) |
| English | `en_US` |

### 15.2 Implementation

- `core/i18n.py`: String key-value translation dictionary
- `tr(text, **kwargs)`: Translation function, supports formatting parameters (e.g., `tr("Hello {}", name)`)
- `using_language()`: Context manager for temporary language switching
- `normalize_language()`: Handles multiple input formats (`zh`, `en`, `zh_CN`, `en_US`)
- All UI strings are translated through `tr()`
- One-click language switching in settings panel

---

## 16. Performance and Stability

### 16.1 Memory Management

`MemoryGuard` monitors process USS memory with a three-level cleanup strategy:

| Level | Threshold | Action |
|-------|-----------|--------|
| Light | 100MB | Basic cleanup |
| Medium | 150MB | Deep cleanup |
| Severe | 200MB | Force cleanup |

Checked every 120 seconds. Cleanup callbacks include: icon cache cleanup, search cache cleanup, GC collection.

### 16.2 Light Sleep Mode

Automatically enters low-power state after configured idle time (default 10 seconds):

- Reduces process priority
- Stops memory and process check timers
- Closes folder watching
- Cleans icon cache
- Stops hotkey manager
- Executes memory cleanup

Middle mouse button wakes immediately.

### 16.3 Folder Sync and Watching

- **Folder Sync**: Incremental sync between physical Windows folders and shortcut database
- **Folder Watcher**: Based on `watchdog` library, monitors folder changes and automatically triggers incremental sync
- Watching automatically stopped during sleep mode to save resources

### 16.4 Crash Protection

- **Python faulthandler**: Enables crash log recording
- **Windows VEH** (Vectored Exception Handler): Captures hard crashes (access violations, stack overflows, etc.), directly writes to `crash.log` via Win32 API
- **Rotating Log**: 2MB x 3 backup file log
- **Single Instance**: QLocalServer/QLocalSocket ensures only one instance runs

### 16.5 DPI Awareness

Automatic adaptation on startup:

1. `SetProcessDpiAwarenessContext` (Windows 10 1703+)
2. `SetProcessDpiAwareness` (Windows 8.1+)
3. `SetProcessDPIAware` (Windows Vista+)

Three-level fallback ensures correct scaling in multi-monitor environments.

---

## 17. Project Structure

```
QuickLauncher/
├── main.py                          # Entry point
├── README.md                        # Project overview
├── README_FULL.md                   # Full documentation (this file)
├── pyproject.toml                   # Tool config (black/ruff)
├── requirements.txt                 # Production dependencies (8)
├── requirements-dev.txt             # Development dependencies (6)
│
├── bootstrap/                       # Startup bootstrap
│   ├── dpi.py                       #   DPI awareness setup
│   ├── deps.py                      #   Auto dependency install
│   ├── ipc.py                       #   Single instance IPC
│   ├── venv.py                      #   Virtual environment detection
│   └── logging_init.py              #   Logging + crash handling
│
├── core/                            # Core logic (~50 modules)
│   ├── data_models.py               #   Data models (ShortcutItem, AppSettings, etc.)
│   ├── data_manager.py              #   Data management (CRUD, backup, history, atomic save)
│   ├── command_registry.py          #   Command registration system
│   ├── commands.py                  #   Command implementations
│   ├── builtin_commands.py          #   Built-in command aliases
│   ├── command_variables.py         #   Command variable template engine
│   ├── command_risk.py              #   Command risk assessment
│   ├── command_execution_service.py #   Command execution service
│   ├── shortcut_chain_exec.py       #   Action chain execution
│   ├── config_repairs.py            #   Config repair and syntax migration
│   ├── plugin_manager.py            #   Plugin management
│   ├── i18n.py                      #   Internationalization
│   ├── pinyin_search.py             #   Pinyin search
│   ├── favicon_cache.py             #   Favicon caching
│   ├── path_security.py             #   Path security
│   ├── memory_guard.py              #   Memory management
│   ├── diagnostics.py               #   Diagnostics center
│   ├── preprocessing/               #   Command preprocessing pipeline
│   │   ├── pipeline.py              #     5-layer pipeline orchestration
│   │   ├── security.py              #     Injection detection, dangerous patterns
│   │   ├── validators.py            #     Path/URL/variable validation
│   │   └── ...
│   └── ...                          #   More core modules
│
├── ui/                              # User interface (~70 modules)
│   ├── tray_app.py                  #   Tray application main controller
│   ├── tray_mixins/                 #   TrayApp mixin splits
│   │   ├── update_mixin.py          #     Auto-update
│   │   ├── hooks_mixin.py           #     Hook management
│   │   ├── sleep_mixin.py           #     Light sleep
│   │   ├── popup_mixin.py           #     Popup display
│   │   └── ...
│   ├── launcher_popup/              #   Popup system
│   │   ├── popup_window.py          #     Popup main class
│   │   ├── popup_search.py          #     Search logic
│   │   ├── popup_command_result.py  #     Command result display
│   │   └── ...
│   ├── config_window/               #   Configuration window
│   │   ├── main_window.py           #     Main window
│   │   ├── command_dialog.py        #     Command editor
│   │   ├── chain_dialog.py          #     Action chain editor
│   │   └── ...
│   ├── command_panel_window.py      #   Standalone command panel
│   ├── styles/style.py              #   Design system and themes
│   └── ...
│
├── hooks/                           # Python hook wrappers
│   ├── hooks_wrapper.py             #   DLL wrapper
│   ├── mouse_hook_dll.py            #   Mouse hook
│   ├── keyboard_hook_dll.py         #   Keyboard hook
│   └── hotkey_manager.py            #   Hotkey manager
│
├── hooks_dll/                       # C++ Hook DLL source
│   ├── hooks.cpp                    #   Hook implementation (SetWindowsHookEx)
│   ├── hooks.h                      #   Header file
│   └── build.bat                    #   MSVC build script
│
├── services/                        # Service layer
│   └── update/                      #   Auto-update system
│       ├── checker.py               #     Version check
│       ├── downloader.py            #     Downloader
│       ├── installer.py             #     Installer
│       └── ui.py                    #     Update notification UI
│
├── plugins/                         # Plugin directory
│   └── text_tools/                  #   Text tools plugin (example)
│
├── tests/                           # Tests (48 test files)
│   ├── test_data_manager.py
│   ├── test_command_registry.py
│   ├── test_shortcut_chain_exec.py
│   └── ...
│
├── assets/                          # App icons, system icon resources
│   └── system_icons/                #   System icons bundled with install
├── config/                          # User data (gitignored)
│   ├── data.json                    #   Configuration data
│   ├── icon_repo.json               #   User icon repository config
│   └── icons/                       #   Icon cache
│
└── .github/                         # GitHub configuration
    ├── ISSUE_TEMPLATE/              #   Issue templates
    └── PULL_REQUEST_TEMPLATE.md     #   PR template
```

---

## 18. Tech Stack

| Category | Technology |
|----------|------------|
| **Language** | Python 3.12 |
| **GUI Framework** | PyQt5 5.15.11 |
| **Global Hooks** | C++ 17 DLL (Win32 SetWindowsHookEx) |
| **System Interaction** | pywin32 (COM, registry, Shell), psutil (process/memory), pynput (input simulation) |
| **Image Processing** | Pillow (PIL), Qt QImage |
| **File Watching** | watchdog |
| **QR Code** | qrcode |
| **Packaging** | Nuitka (compilation) + Inno Setup (installer) |
| **Code Quality** | ruff (lint), black (formatting), mypy (type checking) |
| **Testing** | pytest + pytest-cov |

### Production Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| PyQt5 | ==5.15.11 | GUI framework |
| PyQt5-Qt5 | ==5.15.2 | Qt5 runtime |
| pywin32 | >=305 | Windows API / COM |
| Pillow | >=9.0.0 | Image processing |
| psutil | >=5.9.0 | Process/system monitoring |
| pynput | >=1.7.6 | Input simulation |
| watchdog | >=3.0.0 | File system watching |
| qrcode | >=7.4 | QR code generation |

---

## Getting Started

### Requirements

- **Operating System**: Windows 10 / Windows 11
- **Python**: 3.12 (test baseline), best effort compatibility with 3.8+

### Install Dependencies

```bash
py -3.12 -m pip install -r requirements.txt
```

### Run

```bash
py -3.12 main.py
```

After first launch:

1. Automatically resides in the system tray
2. Press **middle mouse button** to summon the launcher panel
3. Type directly in the popup to search
4. Type `/` to see all available commands

### Build Hook DLL

```bat
cd hooks_dll
build.bat
```

Requires Visual Studio 2022+ or MinGW-w64. After successful build, update `hooks/hooks.dll`.

---

## Development Guide

### Running Tests

```bash
py -3.12 -m pytest tests/ -v
py -3.12 -m compileall -q core hooks ui tests main.py
```

### Lint and Formatting

```bash
py -3.12 -m ruff check core/ ui/ hooks/ services/
ruff format core/ ui/ hooks/ services/
```

### Code Conventions

- Line width 120 (`pyproject.toml`)
- Large class splits use Mixin pattern: filename `*_mixin.py`, class name `*Mixin`, no `__init__` defined
- Signals (`pyqtSignal`) defined in the main class, mixins emit via `self.<signal>.emit()`
- Lazy imports (import within methods) to reduce startup time
- Mixins only import `qt_compat` and `core`, avoiding circular imports

---

---

## Contributing

Issues and Pull Requests are welcome!

- **Bug Reports**: Use the Bug Report template, include reproduction steps, expected/actual behavior, environment info, screenshots, and logs
- **Feature Requests**: Use the Feature Request template
- **Pull Requests**: Use the PR template, check the change type (Bug fix/Feature/Performance/Refactor/Docs), ensure passing ruff, black, mypy checks

---

> **QuickLauncher** — Efficiency at your fingertips.
