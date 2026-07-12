"""Tests for selected text service."""

from core.selected_text_service import SelectedTextError, SelectedTextResult, SelectedTextService, selected_text_service


class TestSelectedTextResult:
    def test_default_construction(self):
        result = SelectedTextResult(text="", success=False, method="none")
        assert not result.success
        assert result.text == ""
        assert result.method == "none"
        assert result.error == ""

    def test_success_construction(self):
        result = SelectedTextResult(text="hello world", success=True, method="clipboard_copy")
        assert result.success
        assert result.text == "hello world"
        assert result.method == "clipboard_copy"

    def test_duration_ms_defaults_zero(self):
        result = SelectedTextResult(text="", success=False, method="none")
        assert result.duration_ms == 0.0


class TestSelectedTextError:
    def test_code_stored(self):
        err = SelectedTextError(code="timeout", message="reading timed out")
        assert err.code == "timeout"
        assert "timed out" in str(err)

    def test_detail_dict(self):
        err = SelectedTextError(code="test", detail={"hwnd": 12345})
        assert err.detail["hwnd"] == 12345


class TestSelectedTextService:
    def test_singleton_exists(self):
        assert selected_text_service is not None
        assert isinstance(selected_text_service, SelectedTextService)

    def test_get_selected_text_no_window_returns_no_strategy(self):
        result = selected_text_service.get_selected_text(
            foreground_hwnd=0,
            allow_clipboard_fallback=False,
        )
        assert not result.success
        assert result.method == "none"

    def test_get_selected_text_self_window_fallback_disabled(self):
        result = selected_text_service.get_selected_text(
            foreground_hwnd=0,
            foreground_process_name="test.exe",
            foreground_window_title="Test",
            allow_clipboard_fallback=False,
        )
        assert not result.success
        assert result.error == "no_strategy"

    def test_check_uipi_blocked_no_hwnd(self):
        assert SelectedTextService.check_uipi_blocked(0) is False

    def test_is_locked_screen_returns_bool(self):
        result = SelectedTextService.is_locked_screen()
        assert isinstance(result, bool)

    def test_get_self_hwnd_returns_int(self):
        hwnd = SelectedTextService._get_self_hwnd()
        assert isinstance(hwnd, int)
