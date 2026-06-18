# QuickLauncher

[![CI](https://github.com/LEISHIQIANG/QuickLauncher/actions/workflows/ci.yml/badge.svg)](https://github.com/LEISHIQIANG/QuickLauncher/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-lightgrey.svg)](https://www.microsoft.com/windows)

[简体中文](README.md) | [English](README_EN.md) | [完整文档](README_FULL.md) | [Full Docs](README_FULL_EN.md) | [Plugin Dev](plugins/PLUGIN_DEV.md)

**Press the middle mouse button, or any keyboard / mouse trigger you configure, to open your launcher anywhere.**

QuickLauncher is a Windows 10 / 11 desktop quick launcher and lightweight automation tool. It launches apps, folders, URLs, hotkeys, commands, action chains, and batch launch groups, and it can be extended with local plugins.

The current source version is defined in [core/version.py](core/version.py): `1.6.3.3` stable. Installer and portable builds ship their own runtime, so end users do not need Python installed. Python is required only for source runs and builds.

## Core Capabilities

| Capability | Current implementation |
|---|---|
| Global trigger | Middle mouse by default; configurable keyboard, mouse, or hybrid triggers; special apps can use a separate trigger such as Ctrl+middle |
| Shortcuts | 7 types: file/app, folder, URL, hotkey, command, action chain, batch launch |
| Search | Fuzzy matching, Chinese Pinyin full/initial search, aliases, tags, web search prefixes, plugin search sources |
| Command system | CMD, PowerShell, Python, Git Bash, built-in commands; parameter forms, variable templates, environment variables, live output, result actions |
| Built-in commands | 33 built-in commands for JSON/JWT/Base64/Hash/TLS/CIDR/Git/process/port/Wi-Fi/Hosts/plugin management and more |
| Action chains | Visual canvas with 189 built-in processors for text, math, lists, JSON, HTTP, files, system info, images, validation, and more |
| Batch launch | Dedicated `batch_launch` shortcut type for ordered multi-target launch without recursive references |
| Plugins | `.qlzip` packages, hot loading, enable/disable, failure quarantine, permission declarations, built-in command registration, search sources, chain processors, persistent workers |
| UI | Dark/light/follow-system themes, Acrylic/image/solid backgrounds, Windows 10 shadows, global UI scaling, Dock, pinned and draggable popups |
| Safety | Atomic saves, config history, automatic backups, import sanitization, path traversal defense, safe URL fetching, SHA-256 verification |

## Installation

Recommended release package:

1. Open [Releases](https://github.com/LEISHIQIANG/QuickLauncher/releases).
2. Download `QuickLauncher_Setup_<version>.exe` or `QuickLauncher_Portable_<version>.zip`.
3. The installer uses Inno Setup. The portable package runs directly from `QuickLauncher.exe`.

Run from source:

```powershell
git clone https://github.com/LEISHIQIANG/QuickLauncher.git
cd QuickLauncher
py -3.12 -m pip install -r requirements.txt
py -3.12 main.py
```

Source runs require Windows 10 / 11 and 64-bit CPython 3.12.

## 30-Second Start

1. Launch the app; it stays in the system tray.
2. Press the middle mouse button and type to search.
3. Type `/` to browse built-in commands, or type a command alias directly.
4. Add files, folders, URLs, hotkeys, commands, action chains, or batch launch items in Settings.
5. Double-tap Alt to pause / resume triggers. CAD and 3D apps can use a separate special trigger profile.

## Built-In Command Examples

| Input | Purpose |
|---|---|
| `/json` | Format, minify, or validate JSON |
| `/jwt` | Decode JWT header and payload |
| `/hash` | Hash a selected file with MD5/SHA1/SHA256/SHA512 |
| `/tls` | Inspect TLS protocol, issuer, and expiry for a domain |
| `/cidr` | Calculate IPv4 / IPv6 network ranges |
| `/port` | Query port usage, with optional `kill` action |
| `/wifi` | Inspect saved Wi-Fi profiles |
| `/hosts` | Edit the hosts file through the elevated path |
| `/git` | Run status, branch, log, diff, fetch, pull, checkout |
| `/plugin-list` | List loaded plugins |

See [README_FULL_EN.md](README_FULL_EN.md) for the full command and parameter reference.

## Official Plugin Packages

The `.plugins/` directory contains official `.qlzip` packages. They are unpacked into the runtime `plugins/` directory only after installation. Release builds do not bundle source plugin folders directly; they ship an empty plugin installation directory.

| Package | Capability |
|---|---|
| `api_tester.qlzip` | HTTP API testing |
| `disk_cleaner.qlzip` | Disk usage analysis and safe cleanup |
| `event_inspector.qlzip` | Windows Event Log inspection and aggregation |
| `file_tools.qlzip` | Selected-file path copy and file hashing |
| `network_tools.qlzip` | Ping and DNS lookup |
| `process_tools.qlzip` | Process ranking and lookup |
| `qr_code_scanner.qlzip` | Screenshot QR-code recognition |
| `screenshot_ocr.qlzip` | Screenshot OCR |
| `startup_tools.qlzip` | Startup audit and PATH health check |
| `text_tools.qlzip` | Text reverse/count/case conversion |

Plugin development is documented in [plugins/PLUGIN_DEV.md](plugins/PLUGIN_DEV.md).

## Development And Verification

```powershell
# Install dependencies
py -3.12 -m pip install -r requirements.txt -r requirements-dev.txt

# Local release gate: ruff, pytest + coverage, broad-exception audit, compileall, metadata, package smoke
py -3.12 scripts/release_gate.py --skip-smoke

# CI-equivalent light gate
py -3.12 scripts/release_gate.py --skip-tests --skip-smoke
py -3.12 -m mypy --follow-imports=skip services/update

# Safe-mode smoke
py -3.12 main.py --safe-mode --smoke-test
```

Build installer and portable artifacts:

```powershell
scripts\build_win11_setup.bat
```

The build chain uses CPython 3.12, Nuitka, PyQt5, an MSVC/MinGW64-capable toolchain, and Inno Setup 6.

## Documentation

- [Complete Chinese documentation](README_FULL.md)
- [Full English documentation](README_FULL_EN.md)
- [Plugin development guide](plugins/PLUGIN_DEV.md)
- [Hook DLL notes](hooks_dll/README.md)
- [System icon notes](assets/system_icons/README.md)
- [GitHub maintenance guide](.github/GITHUB_GUIDE.md)

## License

[MIT](LICENSE)

---

> QuickLauncher - Efficiency at your fingertips.
