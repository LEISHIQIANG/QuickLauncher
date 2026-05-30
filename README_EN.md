# QuickLauncher

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20|%2011-lightgrey.svg)](https://www.microsoft.com/windows)

[简体中文](README.md) | [English](README_EN.md) | [完整文档](README_FULL.md) | [Full Docs](README_FULL_EN.md)

**Press your mouse middle button. Launch anything, anywhere.**

QuickLauncher is a Windows desktop quick launcher — press the mouse middle button anywhere on screen to summon a panel for searching and launching apps, folders, URLs, and commands. Lightweight, fast, and ready to use out of the box.

---

## Why QuickLauncher?

**One click, instant access.** No path memorization, no menu digging. Press the middle button, type to search — with Chinese Pinyin support. Type `kb` to find anything related to "键盘" (keyboard).

**Powerful command system, infinite extensibility.** Supports CMD, PowerShell, Python, and Git Bash runtimes, paired with parameterized templates and dynamic variables (clipboard, date, IP, etc.) to accomplish virtually any operation. Command output is captured and displayed in real-time within the panel — timeout controllable, cancellable anytime.

**More than just opening files.** 6 shortcut types cover every scenario: launch apps, open folders, visit URLs, send hotkey combos, run scripts, chain multi-step action flows for automation. Action chains support up to 50 steps with inter-step data passing — build your own efficiency pipeline.

**Multi-layered security, use with confidence.** Commands are automatically risk-assessed before execution — not blocked, but you're informed. Config file corrupted? Auto-restored from backup — no manual repair needed. ZIP imports, icon downloads, and all external operations are security-validated against injection, path traversal, and more.

**Highly customizable, premium feel.** Switch between dark/light themes, frosted glass acrylic effects, custom image backgrounds. Icon size, grid spacing, columns — all adjustable to make the panel truly yours.

**Plugin ecosystem, unlimited expansion.** Supports custom plugins with `.qlzip` one-click packaging and hot-loading. Plugins can register slash commands and custom search sources with tiered permission management. 8 built-in plugins cover process management, disk cleanup, network diagnostics, and more.

**Chinese / English bilingual, switch at runtime without restart.**

## Installation

**Download installer (recommended):** Head to [Releases](https://github.com/LEISHIQIANG/QuickLauncher/releases) and grab the latest version.

**Run from source:**

```bash
git clone https://github.com/LEISHIQIANG/QuickLauncher.git
cd QuickLauncher
py -3.12 -m pip install -r requirements.txt
py -3.12 main.py
```

> Requires Python 3.12, Windows 10 / 11.

## 30-Second Getting Started

1. The app lives in your **system tray** after launch
2. **Mouse middle button** to summon the launcher panel
3. Start typing to search — supports Pinyin, fuzzy matching, alias search
4. Type `/` to browse all available commands
5. **Double-tap Alt** to pause / resume middle button triggering

## Feature Overview

| Capability | Description |
|------|------|
| Global Trigger | Mouse middle button, auto-compatible with CAD/3D software |
| Smart Search | Fuzzy matching + Pinyin (full/initials) + aliases/tags + engine prefixes |
| Command System | CMD / PowerShell / Python / Git Bash, parameterized templates, real-time output capture |
| Action Chains | Multi-step sequential execution with inter-step data passing |
| Command Variables | `{{clipboard}}`, `{{date}}`, `{{lan_ip}}`, `{{wan_ip}}`, `{{input}}` and more |
| Security Preprocessing | 5-layer pipeline: syntax → semantic → security scan → business rules → audit log |
| Appearance | Dark/light themes, acrylic background, custom images, free layout configuration |
| Plugin System | Permission management, hot-loading, `.qlzip` packaging, custom commands & search sources |
| Data Safety | Atomic saves, auto-backup, 20 config snapshots, corrupted-config auto-recovery |
| Auto-Update | GitHub Releases source, SHA-256 verification, silent install |

## Use With Confidence

| What You Care About | The Reality |
|----------|----------|
| Needs admin rights? | Elevated on demand only — no persistent admin required |
| Writes files to C drive? | All data lives in the app directory — no system drive pollution |
| Writes to registry? | No. Auto-start uses Task Scheduler — easy to disable |
| Phones home? | No network activity except auto-update checks |
| Resource hog at idle? | CPU 0-2%, RAM < 100MB when idle |
| Clean uninstall? | Just delete the app folder — no registry or system file residue |

## Contributing

Issues and PRs welcome!

```bash
# Run tests
py -3.12 -m pytest tests/ -v

# Lint
py -3.12 -m ruff check core/ ui/ hooks/ services/
```

## License

[MIT](LICENSE)

---

> **QuickLauncher** — Efficiency at your fingertips.
