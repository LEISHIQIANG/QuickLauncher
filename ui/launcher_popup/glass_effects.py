"""Pure image-processing helpers for the glass-background renderer.

All functions are stateless helpers operating on raw bytes / PIL images.
Extracted from :mod:`glass_background` to keep each module focused.
"""

from __future__ import annotations

import logging

from PIL import Image as PILImage
from PIL import ImageFilter

logger = logging.getLogger(__name__)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _apply_saturation(pixels: bytearray, factor: float, *, channels: int = 4) -> None:
    if abs(factor - 1.0) < 1e-3:
        return
    if channels == 4:
        for index in range(0, len(pixels), 4):
            b = pixels[index]
            g = pixels[index + 1]
            r = pixels[index + 2]
            luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
            nr = max(0, min(255, int(round(luma + (r - luma) * factor))))
            ng = max(0, min(255, int(round(luma + (g - luma) * factor))))
            nb = max(0, min(255, int(round(luma + (b - luma) * factor))))
            pixels[index] = nb
            pixels[index + 1] = ng
            pixels[index + 2] = nr
    else:
        for index in range(0, len(pixels), 3):
            r = pixels[index]
            g = pixels[index + 1]
            b = pixels[index + 2]
            luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
            nr = max(0, min(255, int(round(luma + (r - luma) * factor))))
            ng = max(0, min(255, int(round(luma + (g - luma) * factor))))
            nb = max(0, min(255, int(round(luma + (b - luma) * factor))))
            pixels[index] = nr
            pixels[index + 1] = ng
            pixels[index + 2] = nb


def _build_radial_highlight(width: int, height: int, strength: float) -> PILImage.Image | None:
    if strength <= 0.0:
        return None
    radius_w = max(1, int(round(width * 0.85)))
    radius_h = max(1, int(round(height * 0.85)))
    cx = int(round(width * 0.10))
    cy = int(round(height * 0.10))
    max_alpha = int(round(strength * 0.25 * 255))
    if max_alpha <= 0:
        return None
    w = max(1, width)
    h = max(1, height)
    try:
        import numpy as np

        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        dx = (xs - cx) / max(1, radius_w)
        dy = (ys - cy) / max(1, radius_h)
        d2 = dx * dx + dy * dy
        t = np.clip(1.0 - d2, 0.0, 1.0)
        alpha = np.clip((max_alpha * t * t).astype(np.int32), 0, 255).astype(np.uint8)
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[..., 0:3] = 255
        rgba[..., 3] = alpha
        return PILImage.fromarray(rgba, "RGBA")
    except Exception:
        pixels = bytearray(w * h * 4)
        for y in range(h):
            dy = (y - cy) / max(1, radius_h)
            for x in range(w):
                dx = (x - cx) / max(1, radius_w)
                d2 = dx * dx + dy * dy
                if d2 >= 1.0:
                    continue
                t = 1.0 - d2
                alpha = int(round(max_alpha * t * t))
                if alpha <= 0:
                    continue
                offset = (y * w + x) * 4
                cur = pixels[offset + 3]
                new = cur + alpha
                if new > 255:
                    new = 255
                pixels[offset + 3] = new
                pixels[offset] = max(pixels[offset], 255)
                pixels[offset + 1] = max(pixels[offset + 1], 255)
                pixels[offset + 2] = max(pixels[offset + 2], 255)
        return PILImage.frombuffer("RGBA", (w, h), bytes(pixels), "raw", "RGBA", 0, 1)


def _build_inner_highlight(width: int, height: int, strength: float) -> PILImage.Image | None:
    if strength <= 0.0:
        return None
    w = max(1, width)
    h = max(1, height)
    if w <= 3 or h <= 3:
        return None
    inner_max = int(round(strength * 0.75 * 255))
    inner_min = int(round(0.02 * 255))
    if inner_max <= 0 and inner_min <= 0:
        return None
    try:
        import numpy as np

        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        tx = np.clip((xs - 1.5) / max(1, w - 3), 0.0, 1.0)
        ty = np.clip((ys - 1.5) / max(1, h - 3), 0.0, 1.0)
        t = np.clip(1.0 - np.maximum(tx, ty), 0.0, 1.0)
        alpha_f = inner_max * t + inner_min * (1.0 - t)
        alpha = np.clip(alpha_f, 0, 255).astype(np.uint8)
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[..., 0:3] = 255
        rgba[..., 3] = alpha
        return PILImage.fromarray(rgba, "RGBA")
    except Exception:
        pixels = bytearray(w * h * 4)
        denom_x = max(1, w - 3)
        denom_y = max(1, h - 3)
        for y in range(1, h - 2):
            ty = (y - 1.5) / denom_y
            for x in range(1, w - 2):
                tx = (x - 1.5) / denom_x
                t = max(0.0, 1.0 - max(tx, ty))
                alpha = int(round(inner_max * t + inner_min * (1.0 - t)))
                if alpha <= 0:
                    continue
                offset = (y * w + x) * 4
                cur = pixels[offset + 3]
                new = cur + alpha
                if new > 255:
                    new = 255
                pixels[offset + 3] = new
                pixels[offset] = max(pixels[offset], 255)
                pixels[offset + 1] = max(pixels[offset + 1], 255)
                pixels[offset + 2] = max(pixels[offset + 2], 255)
        return PILImage.frombuffer("RGBA", (w, h), bytes(pixels), "raw", "RGBA", 0, 1)


def _build_dark_border(width: int, height: int, strength: int) -> PILImage.Image | None:
    if strength <= 0 or width <= 1 or height <= 1:
        return None
    w = max(1, width)
    h = max(1, height)
    try:
        import numpy as np

        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[..., 0] = 15
        rgba[..., 1] = 23
        rgba[..., 2] = 42
        rgba[0, :, 3] = strength
        rgba[h - 1, :, 3] = strength
        rgba[:, 0, 3] = strength
        rgba[:, w - 1, 3] = strength
        return PILImage.fromarray(rgba, "RGBA")
    except Exception:
        pixels = bytearray(w * h * 4)
        for x in range(w):
            offset_top = x * 4
            offset_bottom = (h - 1) * w * 4 + x * 4
            for channel in range(3):
                pixels[offset_top + channel] = 15
                pixels[offset_bottom + channel] = 15
            pixels[offset_top + 3] = strength
            pixels[offset_bottom + 3] = strength
            pixels[offset_top + 1] = max(pixels[offset_top + 1], 23)
            pixels[offset_top + 2] = max(pixels[offset_top + 2], 42)
            pixels[offset_bottom + 1] = max(pixels[offset_bottom + 1], 23)
            pixels[offset_bottom + 2] = max(pixels[offset_bottom + 2], 42)
        for y in range(h):
            offset_left = y * w * 4
            offset_right = y * w * 4 + (w - 1) * 4
            for channel in range(3):
                pixels[offset_left + channel] = 15
                pixels[offset_right + channel] = 15
            pixels[offset_left + 3] = strength
            pixels[offset_right + 3] = strength
            pixels[offset_left + 1] = max(pixels[offset_left + 1], 23)
            pixels[offset_left + 2] = max(pixels[offset_left + 2], 42)
            pixels[offset_right + 1] = max(pixels[offset_right + 1], 23)
            pixels[offset_right + 2] = max(pixels[offset_right + 2], 42)
        return PILImage.frombuffer("RGBA", (w, h), bytes(pixels), "raw", "RGBA", 0, 1)


def _build_noise_layer(width: int, height: int, opacity: float = 0.015) -> PILImage.Image | None:
    """Pre-render a monochromatic noise texture layer to add physical frosted glass grain."""
    return None


def _render_frame(
    captured_bgra: bytes,
    width: int,
    height: int,
    stride: int,
    *,
    blur_radius: float,
    saturation: float,
    highlight: float,
    brightness: float,
    opacity: float,
    downsample: float = 0.25,
    theme: str = "dark",
    glass_quality: str = "auto",
    precomputed_layers: dict | None = None,
) -> bytes:
    """Replicate the Direct2D layer order on top of a captured BGRA frame."""
    if width <= 0 or height <= 0:
        return b""
    src = PILImage.frombuffer("RGBA", (width, height), captured_bgra, "raw", "BGRA", stride, 1)

    if blur_radius > 0.0:
        downscale = max(1, int(round(width * downsample)))
        downscale_h = max(1, int(round(height * downsample)))
        if downscale < width or downscale_h < height:
            small = src.resize((downscale, downscale_h), PILImage.Resampling.BILINEAR)
            if glass_quality in ("low", "auto"):
                blurred_small = small.filter(ImageFilter.BoxBlur(radius=blur_radius / 2.0))
            else:
                blurred_small = small.filter(ImageFilter.GaussianBlur(radius=blur_radius / 2.0))
            blurred = blurred_small.resize((width, height), PILImage.Resampling.BILINEAR)
        else:
            if glass_quality in ("low", "auto"):
                blurred = src.filter(ImageFilter.BoxBlur(radius=blur_radius / 2.0))
            else:
                blurred = src.filter(ImageFilter.GaussianBlur(radius=blur_radius / 2.0))
    else:
        blurred = src

    rgb = blurred.convert("RGB")
    if abs(saturation - 1.0) > 1e-3:
        try:
            # Removed upper clamp to allow proper saturation boost > 1.0
            sat_clamped = max(0.0, float(saturation))
            gray_rgb = rgb.convert("L").convert("RGB")
            rgb = PILImage.blend(gray_rgb, rgb, sat_clamped)
        except Exception:
            pixels = bytearray(rgb.tobytes())
            _apply_saturation(pixels, saturation, channels=3)
            rgb = PILImage.frombytes("RGB", (width, height), bytes(pixels))

    tint_alpha = _clamp(opacity, 0.0, 1.0)
    if tint_alpha > 0.0:
        # Dynamic theme-adaptive tint color
        if theme == "dark":
            base_r = int(round(28.0 * _clamp(brightness, 0.0, 2.0)))
            base_g = int(round(28.0 * _clamp(brightness, 0.0, 2.0)))
            base_b = int(round(30.0 * _clamp(brightness, 0.0, 2.0)))
        else:
            base_r = int(round(242.0 * _clamp(brightness, 0.0, 1.0)))
            base_g = int(round(242.0 * _clamp(brightness, 0.0, 1.0)))
            base_b = int(round(247.0 * _clamp(brightness, 0.0, 1.0)))
        try:
            tint_image = PILImage.new("RGB", rgb.size, (base_r, base_g, base_b))
            rgb = PILImage.blend(rgb, tint_image, tint_alpha)
        except Exception:
            pixels = bytearray(rgb.tobytes())
            for index in range(0, len(pixels), 3):
                r = pixels[index]
                g = pixels[index + 1]
                b = pixels[index + 2]
                pixels[index] = int(round(r * (1.0 - tint_alpha) + base_r * tint_alpha))
                pixels[index + 1] = int(round(g * (1.0 - tint_alpha) + base_g * tint_alpha))
                pixels[index + 2] = int(round(b * (1.0 - tint_alpha) + base_b * tint_alpha))
            rgb = PILImage.frombytes("RGB", (width, height), bytes(pixels))

    composited = rgb.convert("RGBA")
    if precomputed_layers is not None:
        radial = precomputed_layers.get("radial")
        if radial is not None:
            composited = PILImage.alpha_composite(composited, radial)
        noise = precomputed_layers.get("noise")
        if noise is not None:
            composited = PILImage.alpha_composite(composited, noise)
        if highlight > 0.0:
            # We skip dark_border in PIL (drawn in Qt vector space instead)
            inner = precomputed_layers.get("inner")
            if inner is not None:
                composited = PILImage.alpha_composite(composited, inner)
    else:
        radial = _build_radial_highlight(width, height, _clamp(highlight, 0.0, 1.0))
        if radial is not None:
            composited = PILImage.alpha_composite(composited, radial)
        noise = _build_noise_layer(width, height, opacity=0.015)
        if noise is not None:
            composited = PILImage.alpha_composite(composited, noise)
        if highlight > 0.0:
            inner = _build_inner_highlight(width, height, _clamp(highlight, 0.0, 1.0))
            if inner is not None:
                composited = PILImage.alpha_composite(composited, inner)

    return composited.tobytes()


def _make_highlight_layers(width: int, height: int, highlight: float, brightness: float) -> dict:
    """Build size/parameter-dependent static layers used by ``_render_frame``."""
    highlight_clamped = _clamp(highlight, 0.0, 1.0)
    layers: dict = {
        "radial": _build_radial_highlight(width, height, highlight_clamped),
        "noise": _build_noise_layer(width, height, opacity=0.015),
    }
    if highlight > 0.0:
        dark_alpha = max(0, min(255, int(round(0.14 * (1.0 - _clamp(brightness, 0.0, 1.0) * 0.4) * 255))))
        layers["dark_border"] = _build_dark_border(width, height, dark_alpha) if dark_alpha > 0 else None
        layers["inner"] = _build_inner_highlight(width, height, highlight_clamped)
    else:
        layers["dark_border"] = None
        layers["inner"] = None
    return layers


__all__ = [
    "_render_frame",
    "_make_highlight_layers",
    "_clamp",
]
