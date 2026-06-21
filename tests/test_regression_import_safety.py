"""Regression tests for import safety after multi-author refactoring.

Covers: validation.py, restricted_module.py, icon_extractor chain,
icon_grid_helpers Worker signal contracts, icon_widget QtCompat usage,
and the `from core import Xxx` → `from core.xxx import Xxx` fixes.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.ui


# ── validation.py 导入链 ─────────────────────────────────────────────────


def test_validate_manifest_imports_safe_relative_path():
    """_safe_relative_plugin_path 在 validation.py 中不再 NameError"""
    from core.plugin.paths import safe_relative_plugin_path

    assert safe_relative_plugin_path is not None
    assert callable(safe_relative_plugin_path)
    assert safe_relative_plugin_path("main.py") == "main.py"
    assert safe_relative_plugin_path("../bad.py") is None


def test_validate_manifest_entry_safety(monkeypatch):
    """带不安全 entry 的 manifest 返回错误而非崩溃"""
    from core.plugin.models import PluginManifest
    from core.plugin.validation import validate_manifest

    m = PluginManifest(
        id="test",
        name="Test",
        version="1.0",
        entry="../unsafe.py",
        permissions=[],
    )
    err = validate_manifest(m)
    assert "不安全" in err


def test_validate_manifest_ok():
    """合法 manifest 验证通过"""
    from core.plugin.models import PluginManifest
    from core.plugin.validation import validate_manifest

    m = PluginManifest(
        id="test",
        name="Test",
        version="1.0",
        entry="main.py",
        permissions=["clipboard.read"],
        commands=[{"id": "test.hello", "title": "Hello"}],
    )
    assert validate_manifest(m) == ""


# ── restricted_module.py 导入链 ──────────────────────────────────────────


def test_make_plugin_builtins_imports_builtins():
    """_make_plugin_builtins 可以访问 builtins 模块"""
    from core.plugin.restricted_module import _make_plugin_builtins

    builtins_dict = _make_plugin_builtins("test_plugin", [], restricted=False)
    assert isinstance(builtins_dict, dict)
    assert "print" in builtins_dict
    assert "__import__" in builtins_dict


def test_make_plugin_builtins_restricted_mode():
    """受限模式下 eval/exec 被禁用"""
    from core.plugin.restricted_module import _make_plugin_builtins

    builtins_dict = _make_plugin_builtins("test_plugin", ["file.read"], restricted=True)
    assert builtins_dict["eval"] is None
    assert builtins_dict["exec"] is None
    assert callable(builtins_dict["__import__"])
    assert callable(builtins_dict["open"])


def test_make_plugin_builtins_constants_available():
    """PLUGIN_BLOCKED_IMPORT_ROOTS / PLUGIN_OS_BLOCKED_ATTRS 可在受限导入中使用"""
    from core.plugin.restricted_module import _make_plugin_builtins, _RestrictedPluginModule

    builtins_dict = _make_plugin_builtins("test_plugin", ["file.read"], restricted=True)
    restricted_import = builtins_dict["__import__"]

    result = restricted_import("os", None, None, [], 0)
    assert isinstance(result, _RestrictedPluginModule)
    assert result.__name__ == "os"


# ── icon_extractor 导入链 ────────────────────────────────────────────────


def test_icon_extractor_imports_qt_available():
    """QT_AVAILABLE 从 helpers 正确导入"""
    from core.icon_extractor import QT_AVAILABLE

    assert QT_AVAILABLE is True


def test_icon_extractor_imports_all_qt_types():
    """所有必需的 Qt 类型都已导入到 icon_extractor 命名空间"""
    from core.icon_extractor import (
        IconExtractor,
        QApplication,
        QColor,
        QIcon,
        QImage,
        QPainter,
        QPixmap,
        Qt,
    )

    assert QApplication is not None
    assert QColor is not None
    assert QIcon is not None
    assert QImage is not None
    assert QPainter is not None
    assert QPixmap is not None
    assert Qt is not None
    assert IconExtractor is not None


def test_icon_extractor_has_logger():
    """logger 在 icon_extractor 中已定义（避免 NameError）"""
    from core.icon_extractor import logger

    assert logger is not None


def test_icon_extractor_helpers_importable():
    """icon_extractor_helpers 可独立导入"""
    from core.icon_extractor_helpers import (
        _CUSTOM_RESOURCE_EXTS,
        HAS_WIN32,
        QT_AVAILABLE,
        _derive_default_icon_text,
        _pick_default_accent,
        _render_default_icon_pixmap,
    )

    assert _CUSTOM_RESOURCE_EXTS == {".exe", ".dll"}
    assert isinstance(HAS_WIN32, bool)
    assert QT_AVAILABLE is True
    assert callable(_derive_default_icon_text)
    assert callable(_pick_default_accent)
    assert callable(_render_default_icon_pixmap)


def test_derive_default_icon_text_importable_from_helpers():
    """_derive_default_icon_text 应从 helpers 而非主文件导入"""
    from core.icon_extractor_helpers import _derive_default_icon_text

    assert callable(_derive_default_icon_text)
    assert _derive_default_icon_text("Visual Studio Code") == "VS"


# ── icon_extractor 功能回归 ──────────────────────────────────────────────


def test_icon_extractor_extract_exe_target(qapp):
    """exe 目标文件可以提取图标"""
    from core.icon_extractor import IconExtractor

    target = r"C:\Windows\notepad.exe"
    if not os.path.exists(target):
        pytest.skip("notepad.exe not available")

    IconExtractor.clear_cache()
    result = IconExtractor.extract(target, target, 26)
    assert result is not None
    assert not result.isNull()


def test_icon_extractor_from_file_with_custom_path(qapp, tmp_path):
    """from_file 可以加载自定义图标文件"""
    from core.icon_extractor import IconExtractor
    from qt_compat import QColor, QImage

    icon_path = tmp_path / "test.png"
    image = QImage(10, 20, QImage.Format_ARGB32)
    image.fill(QColor(255, 0, 0))
    assert image.save(str(icon_path))

    IconExtractor.clear_cache()
    result = IconExtractor.from_file(str(icon_path), 26)
    assert result is not None
    assert not result.isNull()


def test_icon_extractor_extract_without_fallback(qapp):
    """fallback_to_default=False 时返回 None"""
    from core.icon_extractor import IconExtractor

    result = IconExtractor.extract(
        r"Z:\nonexistent\file.exe",
        r"Z:\nonexistent\file.exe",
        26,
        fallback_to_default=False,
    )
    assert result is None


def test_icon_extractor_should_invert_icon_importable():
    """should_invert_icon 可从正确路径导入"""
    from core.icon_extractor import should_invert_icon

    assert callable(should_invert_icon)


# ── IconGrid Worker 信号合约 ──────────────────────────────────────────────


def test_icon_load_worker_emits_for_all_targets(monkeypatch):
    """Worker 对 exe 和不存在的 target 都发信号"""
    from core.icon_extractor import IconExtractor
    from ui.config_window.icon_grid_helpers import _IconLoadWorker

    capture = []

    def fake_extract(file_path, target_path, size, return_image=False, fallback_to_default=False):
        capture.append(("extract", file_path, target_path))
        if "notepad.exe" in str(file_path):
            from qt_compat import QColor, QImage

            img = QImage(size, size, QImage.Format_ARGB32)
            img.fill(QColor(1, 2, 3))
            return img
        return None

    def fake_from_file(icon_path, size, return_image=False):
        capture.append(("from_file", icon_path))
        return None

    monkeypatch.setattr(IconExtractor, "extract", fake_extract)
    monkeypatch.setattr(IconExtractor, "from_file", fake_from_file)

    tasks = [
        ("id_exe", "", "C:\\Windows\\notepad.exe", 26, "FILE"),
        ("id_missing", "", "Z:\\missing\\file.exe", 26, "FILE"),
        ("id_png", "C:\\icon.png", "C:\\app.exe", 26, "FILE"),
    ]

    worker = _IconLoadWorker(tasks)
    emitted = []

    def on_finished(sid, image):
        emitted.append((sid, image))

    worker.finished.connect(on_finished)
    worker.run()

    assert len(emitted) == 3
    assert emitted[0][0] == "id_exe"
    assert emitted[0][1] is not None  # 真实 exe 返回有效图像
    assert emitted[1][0] == "id_missing"
    assert emitted[1][1] is None  # 不存在的文件返回 None
    assert emitted[2][0] == "id_png"
    assert len(capture) >= 3  # from_file + extract 都有调用


def test_icon_load_worker_exe_not_skipped(monkeypatch):
    """exe target 不会被 _is_pixmap_preferred_resource 跳过"""
    from core.icon_extractor import IconExtractor
    from ui.config_window.icon_grid_helpers import _IconLoadWorker

    extract_called = []

    def fake_extract(file_path, target_path, size, return_image=False, fallback_to_default=False):
        extract_called.append(str(file_path))
        return None

    monkeypatch.setattr(IconExtractor, "extract", fake_extract)
    monkeypatch.setattr(IconExtractor, "from_file", lambda *a, **kw: None)

    tasks = [("id1", "", "D:\\test\\app.exe", 26, "FILE")]

    worker = _IconLoadWorker(tasks)
    worker.finished.connect(lambda sid, img: None)
    worker.run()

    assert len(extract_called) == 1, f"exe target was skipped, extract_called={extract_called}"


def test_icon_load_worker_signal_connected():
    """Worker 的 finished 信号类型匹配 (str, object)"""
    from ui.config_window.icon_grid_helpers import _IconLoadWorker

    worker = _IconLoadWorker([])
    received = []

    def on_finish(sid, img):
        received.append((sid, img))

    worker.finished.connect(on_finish)
    worker.finished.emit("test_id", None)
    assert received == [("test_id", None)]


# ── BatchFaviconFetchWorker 信号合约 ─────────────────────────────────────


def test_batch_favicon_worker_has_result_signal():
    """result 信号存在且签名为 (str, str, str)"""
    from ui.config_window.icon_grid_helpers import _BatchFaviconFetchWorker

    worker = _BatchFaviconFetchWorker([])
    assert hasattr(worker, "result")
    received = []

    def on_result(sid, icon_path, error):
        received.append((sid, icon_path, error))

    worker.result.connect(on_result)
    worker.result.emit("sid1", "/path/icon.png", "")
    assert received == [("sid1", "/path/icon.png", "")]


def test_batch_favicon_worker_has_progress_signal():
    """progress 信号存在且签名为 (int, int)"""
    from ui.config_window.icon_grid_helpers import _BatchFaviconFetchWorker

    worker = _BatchFaviconFetchWorker([])
    assert hasattr(worker, "progress")
    received = []

    def on_progress(completed, total):
        received.append((completed, total))

    worker.progress.connect(on_progress)
    worker.progress.emit(5, 10)
    assert received == [(5, 10)]


def test_batch_favicon_worker_completed_signal():
    """completed 信号签名为 (int, int)"""
    from ui.config_window.icon_grid_helpers import _BatchFaviconFetchWorker

    worker = _BatchFaviconFetchWorker([])
    assert hasattr(worker, "completed")
    received = []

    def on_completed(success, total):
        received.append((success, total))

    worker.completed.connect(on_completed)
    worker.completed.emit(3, 10)
    assert received == [(3, 10)]


def test_batch_favicon_worker_unpacks_task_tuples(monkeypatch):
    """run() 正确解包 (sid, name, url) 三元组"""

    from ui.config_window.icon_grid_helpers import _BatchFaviconFetchWorker

    results = []
    worker = _BatchFaviconFetchWorker([("abc", "Test", "http://example.com")])

    def fake_fetch(url):
        return url + "/favicon.ico"

    monkeypatch.setattr(
        "core.favicon_cache.fetch_favicon",
        staticmethod(fake_fetch),
    )

    worker.result.connect(lambda sid, path, err: results.append((sid, path, err)))
    worker.run()
    assert len(results) == 1
    assert results[0][0] == "abc"
    assert "favicon.ico" in results[0][1]


# ── QtCompat 属性安全 ────────────────────────────────────────────────────


def test_qtcompat_wa_opaque_paint_event_from_qt():
    """WA_OpaquePaintEvent 应从 Qt 而非 QtCompat 取值"""
    from qt_compat import Qt

    assert hasattr(Qt, "WA_OpaquePaintEvent")
    assert isinstance(Qt.WA_OpaquePaintEvent, int)


def test_qtcompat_wa_transparent_for_mouse_events_from_qt():
    """WA_TransparentForMouseEvents 应从 Qt 取值"""
    from qt_compat import Qt

    assert hasattr(Qt, "WA_TransparentForMouseEvents")


def test_qtcompat_wa_translucent_background_available():
    """QtCompat 暴露已知的 WA_* 属性"""
    from qt_compat import QtCompat

    assert QtCompat.WA_TranslucentBackground is not None
    assert QtCompat.WA_NoSystemBackground is not None
    assert QtCompat.WA_StyledBackground is not None
    assert QtCompat.WA_ShowWithoutActivating is not None
    assert QtCompat.WA_DeleteOnClose is not None


def test_icon_widget_uses_qt_not_qtcompat_for_wa(qapp):
    """IconWidget 子控件使用 Qt.WA_* 而非 QtCompat.WA_*"""
    from core.data_models import ShortcutItem, ShortcutType
    from qt_compat import Qt
    from ui.config_window.icon_widget import IconWidget

    shortcut = ShortcutItem(
        id="test_widget",
        name="Test",
        type=ShortcutType.FILE,
        target_path="C:\\test.exe",
    )
    widget = IconWidget(shortcut, icon_size=24, cell_size=65)
    try:
        assert widget.icon_frame.testAttribute(Qt.WA_TransparentForMouseEvents)
        assert widget.icon_label.testAttribute(Qt.WA_TransparentForMouseEvents)
        assert widget.name_label.testAttribute(Qt.WA_TransparentForMouseEvents)
    finally:
        widget.deleteLater()


# ── Popup 图标导入路径 ────────────────────────────────────────────────────


def test_popup_icons_imports_icon_extractor_correctly():
    """popup_icons 使用 from core.icon_extractor import IconExtractor"""
    from ui.launcher_popup.popup_icons import HAS_ICON_EXTRACTOR, IconExtractor

    assert HAS_ICON_EXTRACTOR is True
    assert IconExtractor is not None


def test_popup_data_refresh_imports_icon_extractor_correctly():
    """popup_data_refresh 使用正确的导入路径"""
    from ui.launcher_popup.popup_data_refresh import HAS_ICON_EXTRACTOR

    assert HAS_ICON_EXTRACTOR is True


def test_shortcut_executor_import_correct():
    """popup_item_execution 使用正确的 ShortcutExecutor 导入路径"""
    from ui.launcher_popup.popup_item_execution import HAS_EXECUTOR

    assert HAS_EXECUTOR is True


# ── icon_widget RoundedFrame 渲染 ────────────────────────────────────────


def test_rounded_frame_creates_without_crash(qapp):
    """RoundedFrame 创建不崩溃"""
    from ui.config_window.icon_widget import RoundedFrame

    frame = RoundedFrame()
    try:
        assert frame.width() >= 1 or frame.width() == 0  # default size may vary
    finally:
        frame.deleteLater()


def test_icon_widget_placeholder_renders(qapp):
    """IconWidget 占位图标渲染不崩溃"""
    from core.data_models import ShortcutItem, ShortcutType
    from ui.config_window.icon_widget import IconWidget

    shortcut = ShortcutItem(
        id="test_placeholder",
        name="TestApp",
        type=ShortcutType.FILE,
        target_path="C:\\test.exe",
    )
    widget = IconWidget(shortcut, icon_size=24, cell_size=65)
    try:
        pixmap = widget.icon_label.pixmap()
        assert pixmap is not None
        assert not pixmap.isNull()
    finally:
        widget.deleteLater()


# ── TrayApp stop 方法 ────────────────────────────────────────────────────


def test_tray_app_has_stop_method():
    """TrayApp 有 stop() 方法供 lifecycle 注册"""
    from ui.tray_app import TrayApp

    assert hasattr(TrayApp, "stop")
    assert callable(TrayApp.stop)


# ── _is_builtin_plugin_package 导入链 ───────────────────────────────────


def test_is_builtin_plugin_package_importable():
    """_is_builtin_plugin_package 函数存在且不使用未导入符号"""
    from core.plugin.validation import _is_builtin_plugin_package

    assert callable(_is_builtin_plugin_package)


def test_is_builtin_plugin_package_non_existent_returns_false():
    """不存在的包返回 False"""
    from core.plugin.validation import _is_builtin_plugin_package

    result = _is_builtin_plugin_package("Z:\\nonexistent.qlzip", "nonexistent")
    assert result is False
