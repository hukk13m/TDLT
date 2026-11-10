"""Design tokens for the Acloset Studio app.

Single source of truth for colours, radii, spacing and type sizes.
The QSS file uses ``{{token}}`` placeholders that are filled from these
values when the stylesheet is loaded, so there is only one place to edit.
"""

# --------------------------------------------------------------------------
# Palette A - "Editorial": charcoal ink for actions, amber as the accent,
# emerald for positive signals. No violet anywhere.
# --------------------------------------------------------------------------
COLORS = {
    "ink": "#111827",
    "inkHover": "#1F2937",
    "inkPressed": "#0B1220",
    "inkSoft": "#F3F4F6",
    "amber": "#F59E0B",
    "amberSoft": "#FEF3C7",
    "amberDeep": "#B45309",
    "success": "#10B981",
    "successSoft": "#ECFDF5",
    "successDeep": "#047857",
    "danger": "#EF4444",
    "dangerSoft": "#FEF2F2",
    "dangerDeep": "#B91C1C",
    "bg": "#F6F7F9",
    "surface": "#FFFFFF",
    "surfaceAlt": "#F8FAFC",
    "surfaceSunken": "#F1F2F4",
    "border": "#E7E8EB",
    "borderStrong": "#D5D7DC",
    "text": "#111827",
    "textMuted": "#6B7280",
    "textFaint": "#9CA3AF",
    "white": "#FFFFFF",
}

RADII = {"sm": 8, "md": 12, "lg": 16, "pill": 999}

SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}

# Prefer Apple SF Pro when installed (macOS), Be Vietnam Pro for Vietnamese UI
# (bundled in assets/fonts), with Inter/Plus Jakarta Sans/Segoe UI fallbacks.
FONTS = {
    "display": '"SF Pro Display", ".SF NS Display", "Be Vietnam Pro", "Plus Jakarta Sans", "Segoe UI"',
    "text": '"SF Pro Text", ".SF NS Text", "SF Pro Display", "Be Vietnam Pro", "Inter", "Segoe UI"',
    # Back-compat keys used by existing templates.
    "headline": '"SF Pro Display", ".SF NS Display", "Be Vietnam Pro", "Plus Jakarta Sans", "Segoe UI"',
    "body": '"SF Pro Text", ".SF NS Text", "Be Vietnam Pro", "Inter", "Segoe UI"',
}

FONT_PREFERENCES = {
    "display": [
        "SF Pro Display", ".SF NS Display", "SF Pro", "Be Vietnam Pro",
        "Plus Jakarta Sans", "Segoe UI", "Arial",
    ],
    "text": [
        "SF Pro Text", ".SF NS Text", "SF Pro", "Be Vietnam Pro",
        "Inter", "Segoe UI", "Arial",
    ],
}

# Human readable type scale. Qt uses px in QSS; widget code uses point sizes
# through :func:`pt`.
TYPE_SCALE = {
    "display": 26,
    "h1": 20,
    "h2": 16,
    "body": 13,
    "small": 12,
    "label": 11,
}

# --------------------------------------------------------------------------
# Wear freshness thresholds (single source of truth for badges + scoring)
# --------------------------------------------------------------------------
FRESHNESS = {
    "danger_days": 1,   # worn yesterday or today -> "skip"
    "warning_days": 4,  # worn 2-4 days ago  -> "careful"
    "sleeping_days": 14,
}


def color(name: str) -> str:
    return COLORS[name]


def render_qss(raw: str) -> str:
    """Replace ``{{token}}`` placeholders with palette values."""
    out = raw
    for key, value in COLORS.items():
        out = out.replace("{{" + key + "}}", value)
    for key, value in RADII.items():
        out = out.replace("{{r" + key + "}}", str(value) + "px")
    for key, value in TYPE_SCALE.items():
        out = out.replace("{{t" + key + "}}", str(value) + "px")
    for key, value in FONTS.items():
        out = out.replace("{{f" + key + "}}", value)
    return out
