"""Qt-side asset helpers: bundled fonts, icons and garment artwork.

``libs`` never imports Qt; everything that needs a QPainter lives here.
The garment artwork is drawn, not downloaded: each item gets a flat-lay style
illustration built from its own colour + silhouette. That keeps the closet
visually coherent and free of licensing questions. Drop a real photo into
``assets/garments/<id>.jpg`` and it is used instead, automatically.
"""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS = PROJECT_ROOT / "assets"
FONT_DIR = ASSETS / "fonts"
GARMENT_DIR = ASSETS / "garments"

from libs.theme import FONT_PREFERENCES

# Resolved at runtime from available/bundled families.
_resolved_fonts = {"display": "Segoe UI", "text": "Segoe UI"}
_loaded_families: set[str] = set()
_pixmap_cache: dict[tuple, QPixmap] = {}


# ---------------------------------------------------------------- fonts
def _resolve_family(role: str) -> str:
    available = set(QFontDatabase.families()) | _loaded_families
    for name in FONT_PREFERENCES.get(role, []):
        if name in available:
            return name
    return "Segoe UI"


def load_fonts() -> list[str]:
    families: list[str] = []
    if FONT_DIR.exists():
        for pattern in ("*.ttf", "*.otf"):
            for file in sorted(FONT_DIR.glob(pattern)):
                font_id = QFontDatabase.addApplicationFont(str(file))
                if font_id >= 0:
                    families.extend(QFontDatabase.applicationFontFamilies(font_id))
    _loaded_families.update(families)
    _resolved_fonts["display"] = _resolve_family("display")
    _resolved_fonts["text"] = _resolve_family("text")
    return families


def body_font(size: int = 10, weight: int = 400) -> QFont:
    font = QFont(_resolved_fonts.get("text", "Segoe UI"), size)
    font.setWeight(_qweight(weight))
    return font


def headline_font(size: int = 14, weight: int = 600) -> QFont:
    font = QFont(_resolved_fonts.get("display", "Segoe UI"), size)
    font.setWeight(_qweight(weight))
    return font


def _qweight(weight: int) -> QFont.Weight:
    mapping = {
        400: QFont.Weight.Normal,
        500: QFont.Weight.Medium,
        600: QFont.Weight.DemiBold,
        700: QFont.Weight.Bold,
        800: QFont.Weight.ExtraBold,
    }
    return mapping.get(weight, QFont.Weight.Normal)


# ---------------------------------------------------------------- icons
def icon(name: str, color: str = "#111827", size: int = 16) -> QIcon:
    try:
        import qtawesome as qta

        return qta.icon(name, color=color, color_active=color, color_disabled="#C3C6CC")
    except Exception:  # noqa: BLE001 - never let a missing icon break the UI
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(2, 2, size - 4, size - 4))
        painter.end()
        return QIcon(pixmap)


# ------------------------------------------------------------- garments
_SILHOUETTES = {
    "shirt": "shirt_like", "polo": "shirt_like", "blouse": "shirt_like",
    "tee": "knit_like", "knit": "knit_like", "hoodie": "knit_like",
    "coat": "long_coat", "blazer": "long_coat", "jacket": "long_coat",
    "trousers": "pants", "jeans": "pants", "shorts": "shorts",
    "sneaker": "shoe_low", "loafer": "shoe_low", "oxford": "shoe_low",
    "boot": "shoe_boot",
}


def garment_pixmap(garment, width: int, height: int) -> QPixmap:
    key = (garment.id, garment.color_hex, garment.subtype, width, height,
           garment.image_path)
    if key in _pixmap_cache:
        return _pixmap_cache[key]

    photo = _photo_for(garment)
    if photo is not None and not photo.isNull():
        pixmap = _cover(photo, width, height)
    else:
        pixmap = placeholder_pixmap(garment.subtype, garment.color_hex, width, height)
    _pixmap_cache[key] = pixmap
    return pixmap


def _photo_for(garment) -> QImage | None:
    candidates = []
    if garment.image_path:
        candidates.append(Path(garment.image_path))
    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        candidates.append(GARMENT_DIR / f"{garment.id}{suffix}")
    for path in candidates:
        if path and path.exists():
            image = QImage(str(path))
            if not image.isNull():
                return image
    return None


def _cover(image: QImage, width: int, height: int) -> QPixmap:
    scaled = image.scaled(
        width, height,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - width) // 2)
    y = max(0, (scaled.height() - height) // 2)
    cropped = scaled.copy(x, y, width, height)
    return QPixmap.fromImage(_muted(cropped))


def _muted(image: QImage) -> QImage:
    """Pull mismatched stock photos towards a shared, calmer look."""
    result = image.convertToFormat(QImage.Format.Format_ARGB32)
    painter = QPainter(result)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.fillRect(result.rect(), QColor(246, 247, 249, 30))
    painter.end()
    return result


def placeholder_pixmap(subtype: str, color_hex: str, width: int, height: int) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    base = QColor(color_hex)
    if not base.isValid():
        base = QColor("#C7CBD1")

    # studio backdrop
    gradient = QLinearGradient(0, 0, 0, height)
    gradient.setColorAt(0.0, QColor("#FBFBFC"))
    gradient.setColorAt(1.0, _mix(base, QColor("#FFFFFF"), 0.90))
    painter.fillRect(0, 0, width, height, gradient)

    glow = QRadialGradient(QPointF(width * 0.5, height * 0.46), width * 0.52)
    glow.setColorAt(0.0, _alpha(base, 40))
    glow.setColorAt(1.0, _alpha(base, 0))
    painter.fillRect(0, 0, width, height, glow)

    shape = _SILHOUETTES.get(subtype, "shirt_like")
    rect = QRectF(width * 0.20, height * 0.12, width * 0.60, height * 0.74)

    # soft ground shadow
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(17, 24, 39, 16))
    painter.drawEllipse(QRectF(width * 0.30, height * 0.86, width * 0.40, height * 0.05))

    path = _shape_path(shape, rect)
    fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
    fill.setColorAt(0.0, _mix(base, QColor("#FFFFFF"), 0.10))
    fill.setColorAt(1.0, _mix(base, QColor("#000000"), 0.12))
    painter.setBrush(fill)
    painter.setPen(QPen(_mix(base, QColor("#000000"), 0.28), max(1.0, width / 240), Qt.PenStyle.SolidLine))
    painter.drawPath(path)

    _draw_details(painter, shape, rect, base, width)
    painter.end()
    return pixmap


def _shape_path(shape: str, rect: QRectF) -> QPainterPath:
    if shape == "shirt_like":
        points = [
            (0.32, 0.14), (0.42, 0.10), (0.50, 0.17), (0.58, 0.10), (0.68, 0.14),
            (0.88, 0.31), (0.81, 0.43), (0.71, 0.35), (0.71, 0.92),
            (0.29, 0.92), (0.29, 0.35), (0.19, 0.43), (0.12, 0.31),
        ]
    elif shape == "knit_like":
        points = [
            (0.30, 0.16), (0.70, 0.16), (0.90, 0.36), (0.80, 0.45),
            (0.71, 0.35), (0.71, 0.90), (0.29, 0.90), (0.29, 0.35),
            (0.20, 0.45), (0.10, 0.36),
        ]
    elif shape == "long_coat":
        points = [
            (0.35, 0.10), (0.44, 0.06), (0.56, 0.06), (0.65, 0.10),
            (0.86, 0.33), (0.78, 0.44), (0.69, 0.35), (0.72, 0.96),
            (0.28, 0.96), (0.31, 0.35), (0.22, 0.44), (0.14, 0.33),
        ]
    elif shape == "pants":
        points = [
            (0.27, 0.12), (0.73, 0.12), (0.76, 0.94), (0.57, 0.94),
            (0.50, 0.52), (0.43, 0.94), (0.24, 0.94),
        ]
    elif shape == "shorts":
        points = [
            (0.27, 0.24), (0.73, 0.24), (0.76, 0.66), (0.57, 0.66),
            (0.50, 0.44), (0.43, 0.66), (0.24, 0.66),
        ]
    elif shape == "shoe_low":
        points = [
            (0.12, 0.64), (0.13, 0.50), (0.30, 0.40), (0.45, 0.38),
            (0.58, 0.50), (0.76, 0.56), (0.88, 0.60), (0.89, 0.70),
            (0.13, 0.70),
        ]
    else:  # shoe_boot
        points = [
            (0.30, 0.22), (0.52, 0.22), (0.54, 0.58), (0.68, 0.58),
            (0.84, 0.64), (0.85, 0.74), (0.20, 0.74), (0.18, 0.58),
            (0.28, 0.58),
        ]

    path = QPainterPath()
    for index, (x, y) in enumerate(points):
        point = QPointF(rect.x() + x * rect.width(), rect.y() + y * rect.height())
        if index == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return path


def _draw_details(painter: QPainter, shape: str, rect: QRectF, base: QColor,
                  width: int) -> None:
    pen = QPen(_mix(base, QColor("#000000"), 0.35), max(1.0, width / 300))
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if shape == "shirt_like":
        painter.drawLine(
            QPointF(rect.x() + 0.50 * rect.width(), rect.y() + 0.19 * rect.height()),
            QPointF(rect.x() + 0.50 * rect.width(), rect.y() + 0.90 * rect.height()),
        )
    elif shape == "long_coat":
        painter.drawLine(
            QPointF(rect.x() + 0.50 * rect.width(), rect.y() + 0.14 * rect.height()),
            QPointF(rect.x() + 0.50 * rect.width(), rect.y() + 0.94 * rect.height()),
        )
        painter.drawLine(
            QPointF(rect.x() + 0.34 * rect.width(), rect.y() + 0.60 * rect.height()),
            QPointF(rect.x() + 0.66 * rect.width(), rect.y() + 0.60 * rect.height()),
        )
    elif shape in ("pants", "shorts"):
        painter.drawLine(
            QPointF(rect.x() + 0.27 * rect.width(), rect.y() + 0.19 * rect.height()),
            QPointF(rect.x() + 0.73 * rect.width(), rect.y() + 0.19 * rect.height()),
        )
    elif shape in ("shoe_low", "shoe_boot"):
        painter.drawLine(
            QPointF(rect.x() + 0.14 * rect.width(), rect.y() + 0.68 * rect.height()),
            QPointF(rect.x() + 0.88 * rect.width(), rect.y() + 0.68 * rect.height()),
        )


def _mix(first: QColor, second: QColor, ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, ratio))
    return QColor(
        round(first.red() * (1 - ratio) + second.red() * ratio),
        round(first.green() * (1 - ratio) + second.green() * ratio),
        round(first.blue() * (1 - ratio) + second.blue() * ratio),
    )


def _alpha(color: QColor, alpha: int) -> QColor:
    tinted = QColor(color)
    tinted.setAlpha(alpha)
    return tinted


def rounded_pixmap(pixmap: QPixmap, radius: int, width: int, height: int) -> QPixmap:
    target = QPixmap(width, height)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap.scaled(
        width, height,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    ))
    painter.end()
    return target


def clear_cache() -> None:
    _pixmap_cache.clear()


def asset_path(*parts: str) -> str:
    return os.path.join(ASSETS, *parts)
