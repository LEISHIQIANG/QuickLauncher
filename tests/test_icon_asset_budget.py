from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
COMMAND_ICON_DIR = ROOT / "assets" / "command_icons"
MAX_COMMAND_ICON_SIZE_BYTES = 64 * 1024
MAX_COMMAND_ICON_DIMENSION = 128
BUNDLED_ICO_BUDGETS = {
    "app.ico": 160 * 1024,
    "Folder.ico": 32 * 1024,
    "setting.ico": 32 * 1024,
    "setting_white.ico": 32 * 1024,
}


def test_command_icon_assets_are_small_real_pngs():
    icon_paths = sorted(COMMAND_ICON_DIR.glob("*.png"))

    assert icon_paths
    for path in icon_paths:
        assert path.stat().st_size <= MAX_COMMAND_ICON_SIZE_BYTES, path.name
        with Image.open(path) as image:
            assert image.format == "PNG", path.name
            assert image.width <= MAX_COMMAND_ICON_DIMENSION, path.name
            assert image.height <= MAX_COMMAND_ICON_DIMENSION, path.name


def test_bundled_ico_assets_stay_within_budget():
    for name, max_size in BUNDLED_ICO_BUDGETS.items():
        path = ROOT / "assets" / name

        assert path.stat().st_size <= max_size, name
        with Image.open(path) as image:
            assert image.format == "ICO", name
            sizes = sorted(image.ico.sizes())
            assert sizes, name
            assert max(width for width, _height in sizes) <= 256, name
            assert max(height for _width, height in sizes) <= 256, name
