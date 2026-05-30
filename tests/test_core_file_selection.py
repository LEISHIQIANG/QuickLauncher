"""Unit tests for core/file_selection.py."""

from unittest.mock import MagicMock, patch

from core.file_selection import _selected_item_paths, get_selected_files_for_process


def test_selected_item_paths_success():
    mock_item1 = MagicMock()
    mock_item1.Path = "C:\\file1.txt"
    mock_item2 = MagicMock()
    mock_item2.Path = "C:\\file2.txt"

    mock_items = MagicMock()
    mock_items.Count = 2
    mock_items.Item.side_effect = lambda i: mock_item1 if i == 0 else mock_item2

    paths = _selected_item_paths(mock_items)
    assert paths == ["C:\\file1.txt", "C:\\file2.txt"]


def test_selected_item_paths_exception_on_count():
    mock_items = MagicMock()
    type(mock_items).Count = property(lambda self: exec('raise Exception("error")'))

    paths = _selected_item_paths(mock_items)
    assert paths == []


def test_selected_item_paths_exception_on_item():
    mock_item1 = MagicMock()
    mock_item1.Path = "C:\\file1.txt"

    mock_items = MagicMock()
    mock_items.Count = 2
    mock_items.Item.side_effect = [mock_item1, Exception("error")]

    paths = _selected_item_paths(mock_items)
    assert paths == ["C:\\file1.txt"]


def test_get_selected_files_for_process_no_win32_shell(monkeypatch):
    import core.file_selection as file_selection

    monkeypatch.setattr(file_selection, "HAS_WIN32_SHELL", False)
    assert get_selected_files_for_process() == []


@patch("core.file_selection.HAS_WIN32_SHELL", True)
@patch("win32gui.GetForegroundWindow")
@patch("win32com.client.Dispatch")
@patch("pythoncom.CoInitialize")
@patch("pythoncom.CoUninitialize")
def test_get_selected_files_for_process_success(
    mock_co_uninit, mock_co_init, mock_dispatch, mock_get_fg_hwnd, monkeypatch
):
    import core.file_selection as file_selection

    # Mock normalize and window selection
    mock_normalize = MagicMock(return_value=123)
    mock_selection_kind = MagicMock(return_value="explorer")
    monkeypatch.setattr(file_selection, "_normalize_window_hwnd", mock_normalize)
    monkeypatch.setattr(file_selection, "_window_selection_kind", mock_selection_kind)

    mock_get_fg_hwnd.return_value = 123

    # Mock Dispatch shell application
    mock_shell = MagicMock()
    mock_dispatch.return_value = mock_shell

    mock_window = MagicMock()
    mock_window.HWND = 123

    mock_selected = MagicMock()
    mock_selected.Count = 1
    mock_selected.Item.return_value.Path = "C:\\file.txt"
    mock_window.Document.SelectedItems.return_value = mock_selected

    mock_windows = MagicMock()
    mock_windows.Count = 1
    mock_windows.Item.return_value = mock_window
    mock_shell.Windows.return_value = mock_windows

    paths = get_selected_files_for_process()
    assert paths == ["C:\\file.txt"]
    assert mock_co_init.called
    assert mock_co_uninit.called


@patch("core.file_selection.HAS_WIN32_SHELL", True)
@patch("win32gui.GetForegroundWindow")
@patch("win32com.client.Dispatch")
@patch("pythoncom.CoInitialize")
@patch("pythoncom.CoUninitialize")
def test_get_selected_files_for_process_desktop(
    mock_co_uninit, mock_co_init, mock_dispatch, mock_get_fg_hwnd, monkeypatch
):
    import core.file_selection as file_selection

    # Mock normalize and window selection
    mock_normalize = MagicMock(return_value=123)
    mock_selection_kind = MagicMock(return_value="desktop")
    mock_is_desktop = MagicMock(return_value=True)
    monkeypatch.setattr(file_selection, "_normalize_window_hwnd", mock_normalize)
    monkeypatch.setattr(file_selection, "_window_selection_kind", mock_selection_kind)
    monkeypatch.setattr(file_selection, "_is_desktop_window", mock_is_desktop)

    mock_get_fg_hwnd.return_value = 123

    mock_shell = MagicMock()
    mock_dispatch.return_value = mock_shell

    mock_window = MagicMock()
    mock_window.HWND = 123

    mock_selected = MagicMock()
    mock_selected.Count = 1
    mock_selected.Item.return_value.Path = "C:\\desktop_file.txt"
    mock_window.Document.SelectedItems.return_value = mock_selected

    mock_windows = MagicMock()
    mock_windows.Count = 1
    mock_windows.Item.return_value = mock_window
    mock_shell.Windows.return_value = mock_windows

    paths = get_selected_files_for_process()
    assert paths == ["C:\\desktop_file.txt"]


@patch("core.file_selection.HAS_WIN32_SHELL", True)
@patch("win32gui.GetForegroundWindow")
@patch("pythoncom.CoInitialize")
def test_get_selected_files_for_process_no_fg_window(
    mock_co_init,
    mock_get_fg_hwnd,
):
    mock_get_fg_hwnd.return_value = 0
    assert get_selected_files_for_process() == []


@patch("core.file_selection.HAS_WIN32_SHELL", True)
@patch("win32gui.GetForegroundWindow")
@patch("pythoncom.CoInitialize")
def test_get_selected_files_for_process_wrong_kind(mock_co_init, mock_get_fg_hwnd, monkeypatch):
    import core.file_selection as file_selection

    monkeypatch.setattr(file_selection, "_normalize_window_hwnd", lambda h: 123)
    monkeypatch.setattr(file_selection, "_window_selection_kind", lambda h: "other")

    mock_get_fg_hwnd.return_value = 123
    assert get_selected_files_for_process() == []
