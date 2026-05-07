# build.spec
# -*- mode: python ; coding: utf-8 -*-

import sys
import os

block_cipher = None

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))

a = Analysis(
    [os.path.join(ROOT_DIR, 'main.py')],
    pathex=[ROOT_DIR],
    binaries=[],
    datas=[
        # 添加资源文件
        (os.path.join(ROOT_DIR, 'assets'), 'assets'),
        # 添加内置图标
        (os.path.join(ROOT_DIR, 'builtin_icons'), 'builtin_icons'),
    ],
    hiddenimports=[
        'pynput',
        'pynput.mouse',
        'pynput.mouse._win32',
        'pynput.keyboard',
        'pynput.keyboard._win32',
        'win32gui',
        'win32ui',
        'win32con',
        'win32api',
        'win32process',
        'psutil',
        'PIL',
        'PIL.Image',
        # UI 模块
        'ui.config_window.settings_panel',
        'ui.config_window.settings_helpers',
        'ui.config_window.folder_panel',
        'ui.config_window.icon_grid',
        'ui.config_window.theme_helper',
        'ui.tooltip_helper',
        'ui.utils.font_manager',
        'ui.utils.window_effect',
        'ui.styles.style',
        'ui.styles.themed_messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pypinyin'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 排除 VC++ 运行时 DLL，使用系统自带的
# 这样可以避免安装时 DLL 被占用的问题
a.binaries = [
    (name, path, typ) for name, path, typ in a.binaries
    if not any([
        # 排除多余的 PyQt5 组件以极致减小体积
        'qt5quick' in name.lower(),
        'qt5qml' in name.lower(),
        'qt5multimedia' in name.lower(),
        'qt5webengine' in name.lower(),
        'qt5webchannel' in name.lower(),
        'qt5websockets' in name.lower(),
        'qt5dbus' in name.lower(),
        'qt53d' in name.lower(),
        'qt5designer' in name.lower(),
        'qt5help' in name.lower(),
        'qt5location' in name.lower(),
        'qt5positioning' in name.lower(),
        'qt5sensors' in name.lower(),
        'qt5serialport' in name.lower(),
        'qt5sql' in name.lower(),
        'qt5test' in name.lower(),
        'qt5xml' in name.lower(),
        'qt5script' in name.lower(),
        'qt5texttospeech' in name.lower(),
        'qt5bluetooth' in name.lower(),
        'qt5nfc' in name.lower(),
        'qt5virtualkeyboard' in name.lower(),
        'opengl32sw.dll' in name.lower(),
        'd3dcompiler_' in name.lower(),
        # 排除所有 VC++ 运行时 DLL（包括 PyQt5 自带的）
        name.lower().endswith('msvcp140.dll'),
        name.lower().endswith('msvcp140_1.dll'),
        name.lower().endswith('msvcp140_2.dll'),
        name.lower().endswith('msvcp140_atomic_wait.dll'),
        name.lower().endswith('msvcp140_codecvt_ids.dll'),
        name.lower().endswith('vcruntime140.dll'),
        name.lower().endswith('vcruntime140_1.dll'),
        name.lower().endswith('vcruntime140_threads.dll'),
        name.lower().endswith('concrt140.dll'),
        name.lower().endswith('vcomp140.dll'),
        name.lower().endswith('ucrtbase.dll'),
        # 排除 api-ms-win-crt-*.dll
        'api-ms-win-crt-' in name.lower(),
    ])
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='QuickLauncher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # False = 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../assets/app.ico',
)
