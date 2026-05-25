import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from services.api.base_client import ApiClient, ApiError


class TestApiClient:
    def setup_method(self):
        self.client = ApiClient("https://example.com/api", timeout=5)

    @patch("services.api.base_client.urlopen")
    def test_get_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = self.client.get("/test", {"key": "val"})

        assert result == {"ok": True}
        call_url = mock_urlopen.call_args[0][0].full_url
        assert "key=val" in call_url

    @patch("services.api.base_client.urlopen")
    def test_get_without_path(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.client.get()

        assert mock_urlopen.call_args[0][0].full_url == "https://example.com/api"

    @patch("services.api.base_client.urlopen")
    def test_post_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"id": 1}).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = self.client.post("/create", {"name": "test"})

        assert result == {"id": 1}

    @patch("services.api.base_client.urlopen")
    def test_http_error(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError("http://example.com", 404, "Not Found", {}, None)

        with pytest.raises(ApiError, match="HTTP 404"):
            self.client.get("/notfound")

    @patch("services.api.base_client.urlopen")
    def test_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("connection refused")

        with pytest.raises(ApiError, match="Network error"):
            self.client.get("/fail")

    def test_user_agent(self):
        from core.version import APP_VERSION

        assert self.client._headers["User-Agent"] == f"QuickLauncher/{APP_VERSION}"
