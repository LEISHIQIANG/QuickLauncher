from core.data_models import AppData
from core.diagnostics import collect_diagnostics


class _Manager:
    def __init__(self, tmp_path):
        self.data = AppData()
        self.app_dir = tmp_path
        self.icons_dir = tmp_path / "icons"
        self.icons_dir.mkdir()

    def get_config_status(self):
        return {"status": "ok", "source": "test", "issues": []}

    def get_settings(self):
        return self.data.settings

    def get_icon_cache_stats(self):
        return {"total_files": 0, "total_size_mb": 0}


def test_collect_diagnostics_returns_core_sections(tmp_path):
    items = collect_diagnostics(_Manager(tmp_path))
    titles = {item.title for item in items}

    assert "配置文件" in titles
    assert "Hook DLL" in titles
    assert "最近错误" in titles
