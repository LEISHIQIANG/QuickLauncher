# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all
import certifi

datas = [
    (certifi.where(), 'certifi'),
]
binaries = []
hiddenimports = [
    'pynput', 'pynput.mouse._win32', 'pynput.keyboard._win32',
    'win32gui', 'win32ui', 'win32con', 'win32api', 'win32process',
    'psutil', 'PIL', 'PIL.Image',
    'PIL.BmpImagePlugin', 'PIL.GifImagePlugin', 'PIL.IcoImagePlugin',
    'PIL.JpegImagePlugin', 'PIL.PngImagePlugin', 'PIL.WebPImagePlugin',
    'PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'PyQt5.QtNetwork', 'PyQt5.QtSvg',
    # UI 模块 - 修复打包后设置面板无法加载的问题
    'ui.config_window.settings_panel',
    'ui.config_window.settings_helpers',
    'ui.config_window.folder_panel',
    'ui.config_window.icon_grid',
    'ui.config_window.theme_helper',
    # core.commands 在 1.6.3.2 拆分为 10 个子模块，shim 经相对导入
    # 触发，PyInstaller 静态分析在 optimize=2 下容易漏包，补充到这里
    # 防止 "内置命令管理" 列表为空。
    'core.commands',
    'core.commands_clipboard',
    'core.commands_encoding',
    'core.commands_network',
    'core.commands_text',
    'core.commands_utils',
    'core.commands_plugins',
    'core.commands_system',
    'core.commands_windows',
    'core.commands_maintenance',
    'core.commands_git',
]
tmp_ret = collect_all('PyQt5')

_UNWANTED_DLLS = {
    'qt5printsupport.dll', 'qxdgdesktopportal.dll',
}
_UNWANTED_PYD = {'PyQt5.QtPrintSupport.pyd', '_avif.pyd'}

_filtered_datas = []
for entry in tmp_ret[0]:
    name = entry[0] if isinstance(entry, tuple) else entry
    basename = os.path.basename(name).lower()
    if basename not in _UNWANTED_DLLS:
        _filtered_datas.append(entry)
datas += _filtered_datas

_filtered_binaries = []
for entry in tmp_ret[1]:
    name = entry[0] if isinstance(entry, tuple) else entry
    basename = os.path.basename(name).lower()
    if basename not in _UNWANTED_DLLS and basename not in _UNWANTED_PYD:
        _filtered_binaries.append(entry)
binaries += _filtered_binaries

_filtered_hiddenimports = [
    hi for hi in tmp_ret[2]
    if not hi.lower().startswith('pyqt5.qtprintsupport')
]
hiddenimports += _filtered_hiddenimports


a = Analysis(
    ['../main.py'],
    pathex=[],
    binaries=[],
    datas=datas + [
        ('../assets', 'assets'),
        ('../plugins', 'plugins'),
        ('../qt_compat.py', '.')
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'pandas', 'scipy', 'IPython', 'jupyter', 'pypinyin',
        'PIL.AvifImagePlugin',
    ],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='QuickLauncher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx_exclude=['vcruntime140.dll', 'python311.dll'],
    name='QuickLauncher',
)
