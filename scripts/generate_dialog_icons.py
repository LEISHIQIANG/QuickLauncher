"""Generate minimalist PNG line icons used by themed dialogs."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets" / "dialog_icons"

SOURCE_SIZE = 96
WORK_SIZE = SOURCE_SIZE * 4
SCALE = WORK_SIZE / SOURCE_SIZE


def sp(value: float) -> int:
    return int(round(value * SCALE))


def color(hex_color: str, alpha: int = 242) -> tuple[int, int, int, int]:
    hex_color = hex_color.lstrip("#")
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
        alpha,
    )


def new_icon() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (WORK_SIZE, WORK_SIZE), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def rounded_line(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], stroke: str, width: float) -> None:
    scaled = [(sp(x), sp(y)) for x, y in points]
    line_width = sp(width)
    draw.line(scaled, fill=color(stroke), width=line_width, joint="curve")
    radius = line_width // 2
    for x, y in scaled:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color(stroke))


def circle_outline(draw: ImageDraw.ImageDraw, stroke: str) -> None:
    draw.ellipse((sp(17), sp(17), sp(79), sp(79)), outline=color(stroke), width=sp(5.5))


def save_icon(image: Image.Image, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    image = image.resize((SOURCE_SIZE, SOURCE_SIZE), Image.Resampling.LANCZOS)
    image.save(OUT_DIR / name)


def draw_information() -> None:
    image, draw = new_icon()
    stroke = "#0a84ff"
    circle_outline(draw, stroke)
    draw.ellipse((sp(44), sp(28), sp(52), sp(36)), fill=color(stroke))
    rounded_line(draw, [(48, 45), (48, 66)], stroke, 5.5)
    save_icon(image, "information.png")


def draw_question() -> None:
    image, draw = new_icon()
    stroke = "#5e5ce6"
    circle_outline(draw, stroke)
    rounded_line(draw, [(38, 38), (38, 31), (43, 26), (51, 25), (58, 29), (60, 36)], stroke, 5.5)
    rounded_line(draw, [(60, 36), (57, 45), (49, 50), (48, 58)], stroke, 5.5)
    draw.ellipse((sp(44), sp(66), sp(52), sp(74)), fill=color(stroke))
    save_icon(image, "question.png")


def draw_warning() -> None:
    image, draw = new_icon()
    stroke = "#ff9f0a"
    points = [(48, 14), (84, 78), (12, 78)]
    scaled = [(sp(x), sp(y)) for x, y in points]
    draw.line([*scaled, scaled[0]], fill=color(stroke), width=sp(5.5), joint="curve")
    rounded_line(draw, [(48, 38), (48, 58)], stroke, 5.5)
    draw.ellipse((sp(44), sp(66), sp(52), sp(74)), fill=color(stroke))
    save_icon(image, "warning.png")


def draw_critical() -> None:
    image, draw = new_icon()
    stroke = "#ff453a"
    circle_outline(draw, stroke)
    rounded_line(draw, [(36, 36), (60, 60)], stroke, 5.8)
    rounded_line(draw, [(60, 36), (36, 60)], stroke, 5.8)
    save_icon(image, "critical.png")


def draw_download() -> None:
    image, draw = new_icon()
    stroke = "#00a6a6"
    circle_outline(draw, stroke)
    rounded_line(draw, [(48, 28), (48, 55)], stroke, 5.8)
    rounded_line(draw, [(35, 44), (48, 57), (61, 44)], stroke, 5.8)
    rounded_line(draw, [(33, 68), (63, 68)], stroke, 5.5)
    save_icon(image, "download.png")


def main() -> int:
    draw_information()
    draw_question()
    draw_warning()
    draw_critical()
    draw_download()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
