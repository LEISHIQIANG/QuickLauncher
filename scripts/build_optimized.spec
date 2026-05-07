# -*- mode: python ; coding: utf-8 -*-
# 优化版打包配置 - 减小体积

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = [
    'pynput', 'pynput.mouse._win32', 'pynput.keyboard._win32',
    'win32gui', 'win32ui', 'win32con', 'win32api', 'win32process',
    'psutil', 'PIL', 'PIL.Image',
    'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'PyQt5.QtNetwork',
    'ui.config_window.settings_panel',
    'ui.config_window.settings_helpers',
    'ui.config_window.folder_panel',
    'ui.config_window.icon_grid',
    'ui.config_window.theme_helper',
]

# 只收集必要的 PyQt5 组件
tmp_ret = collect_all('PyQt5')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    ['../main.py'],
    pathex=[],
    binaries=[],
    datas=datas + [
        ('../assets', 'assets'),
        ('../builtin_icons', 'builtin_icons'),
        ('../qt_compat.py', '.')
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'IPython', 'jupyter', 'notebook',
        'test', 'tests', 'unittest', 'pypinyin',
    ],
    noarchive=False,
    optimize=2,
)

# 过滤不需要的二进制文件
a.binaries = [
    (name, path, typ) for name, path, typ in a.binaries
    if not any([
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
        'd3dcompiler_' in name.lower()
    ])
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='QuickLauncher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=['vcruntime140.dll', 'python311.dll'],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../assets/app.ico',
    manifest='../QuickLauncher.manifest',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=['vcruntime140.dll', 'python311.dll', 'Qt5Core.dll', 'Qt5Gui.dll'],
    name='QuickLauncher',
)
