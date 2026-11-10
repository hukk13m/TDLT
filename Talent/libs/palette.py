"""Small colour utilities shared by the form and the scoring model."""

from __future__ import annotations

import colorsys


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return (204, 204, 204)
    try:
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (204, 204, 204)


def luminance(value: str) -> float:
    r, g, b = (channel / 255 for channel in hex_to_rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def family_for_hex(value: str) -> str:
    """Classify a colour into the three families the recommender uses."""
    r, g, b = (channel / 255 for channel in hex_to_rgb(value))
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    degrees = hue * 360
    if saturation < 0.16 or lightness < 0.16 or lightness > 0.94:
        return "neutral"
    if 185 <= degrees <= 285:
        return "cool"
    if 60 <= degrees < 185:
        return "earth"
    return "warm"


def contrasting_text(value: str) -> str:
    return "#111827" if luminance(value) > 0.55 else "#FFFFFF"
