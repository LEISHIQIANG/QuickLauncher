"""
安全原生文件选择与消息框测试用例
验证同步暂停与复原的安全钩子生命周期管道
"""


class MockMouseHook:
    def __init__(self):
        self.paused = False
        self.reinstalled = False
        self.callback = None
        self.keyboard_hook = None
        self._callback = "dummy_mouse_callback"

    def set_paused(self, paused: bool):
        self.paused = paused

    def install(self, callback):
        self.callback = callback
        self.reinstalled = True

    def set_keyboard_hook(self, kb_hook):
        self.keyboard_hook = kb_hook


class MockKeyboardHook:
    def __init__(self):
        self.uninstalled = False
        self.reinstalled = False
        self.callback = None
        self._on_alt_double_tap = "dummy_kbd_callback"

    def uninstall(self):
        self.uninstalled = True

    def install(self, callback):
        self.callback = callback
        self.reinstalled = True


def test_safe_file_dialog_hook_lifecycle_pipeline():
    """验证在原生文件框同步调用的整个生命周期中，鼠标钩子暂停与复原机制被 100% 完整执行，排除任何卡死风险"""
    from ui.utils.safe_file_dialog import (
        _execute_dialog_synchronously,
        set_global_keyboard_hook,
        set_global_mouse_hook,
    )

    mock_mouse = MockMouseHook()
    mock_keyboard = MockKeyboardHook()

    # 注册模拟钩子
    set_global_mouse_hook(mock_mouse)
    set_global_keyboard_hook(mock_keyboard)

    executed = False

    def mock_native_call(hwnd, *args, **kwargs):
        nonlocal executed
        executed = True

        # 在原生对话框执行期间，断言鼠标钩子被同步暂停！
        assert mock_mouse.paused is True
        return "selected_path"

    res = _execute_dialog_synchronously(None, mock_native_call, None)

    # 验证执行体是否被正确调用
    assert executed is True
    assert res == "selected_path"

    # 验证原生对话框退出后，鼠标钩子已同步解除暂停！
    assert mock_mouse.paused is False


def test_native_message_box_lifecycle_pipeline(monkeypatch, qapp):
    """验证在原生系统消息框调用的生命周期中，鼠标钩子被同步暂停与复原，彻底避免誤觸"""
    from ui.styles.themed_messagebox import _execute_native_message_box
    from ui.utils.safe_file_dialog import set_global_keyboard_hook, set_global_mouse_hook

    mock_mouse = MockMouseHook()
    mock_keyboard = MockKeyboardHook()

    # 注册模拟钩子
    set_global_mouse_hook(mock_mouse)
    set_global_keyboard_hook(mock_keyboard)

    native_called = False

    # Mock QMessageBox.exec_
    from PyQt5.QtWidgets import QMessageBox

    def mock_exec(self):
        nonlocal native_called
        native_called = True
        # 在原生 MessageBox 挂起期间，断言鼠标钩子被同步暂停！
        assert mock_mouse.paused is True
        return 1024  # Standard button OK

    monkeypatch.setattr(QMessageBox, "exec_", mock_exec)

    res = _execute_native_message_box(None, "Title", "Text", "info", 1024)

    assert native_called is True
    assert res == 1024

    # 验证退出后，鼠标已同步解除暂停
    assert mock_mouse.paused is False
