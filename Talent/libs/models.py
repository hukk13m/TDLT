"""Plain data objects shared by the data, scoring and UI layers.

Nothing here imports PyQt on purpose: the whole ``libs`` package stays
GUI-free so it can be exercised from a plain script (see ``main.py --demo``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

CATEGORIES = ("top", "bottom", "shoes", "outer")

CATEGORY_LABELS = {
    "top": "Tops",
    "bottom": "Bottoms",
    "shoes": "Footwear",
    "outer": "Outerwear",
}

SLOTS = ("top", "bottom", "outer", "shoes")

SLOT_LABELS = {
    "top": "Top",
    "bottom": "Bottom",
    "outer": "Outerwear",
    "shoes": "Footwear",
}


@dataclass
class Garment:
    id: str
    name: str
    category: str
    subtype: str
    color_name: str
    color_hex: str
    color_family: str
    pattern: str
    material: str
    breathability: int  # 1..10, higher = airier
    warmth: int         # 1..10, higher = warmer
    seasons: list[str]
    occasions: list[str]
    image_path: str = ""
    created_at: str = ""

    @property
    def tags(self) -> list[str]:
        return [self.category, self.color_name, self.material, self.pattern]


@dataclass
class Outfit:
    id: str
    name: str
    score: float = 0.0
    source: str = "ai"
    is_favorite: bool = False
    created_at: str = ""
    items: dict[str, Garment] = field(default_factory=dict)

    def ordered_items(self) -> list[Garment]:
        return [self.items[s] for s in SLOTS if s in self.items]

    @property
    def item_ids(self) -> list[str]:
        return [self.items[s].id for s in SLOTS if s in self.items]


@dataclass
class WearEntry:
    id: int
    outfit_id: str
    worn_on: str
    feedback: int | None
    note: str
    outfit: Outfit | None = None


@dataclass
class Context:
    """Everything the recommender needs to know about "right now"."""

    occasion: str = "University"
    style_goal: str = "Smart Casual"
    temperature: float = 30.0
    condition: str = "Clear"
    is_rain: bool = False
    city: str = "Ho Chi Minh City"
    anti_rep_days: int = 3
    strict_anti_rep: bool = True
    outer_mode: str = "auto"  # auto | include | exclude
    today: date = field(default_factory=date.today)

    @property
    def weather_summary(self) -> str:
        return f"{round(self.temperature)}°C {self.condition}"


@dataclass
class Contribution:
    """One XAI row: a criterion, its raw sub-score and its share of the total."""

    key: str
    label: str
    detail: str
    subscore: float      # 0..1
    weight: float        # 0..1, sum of all weights == 1
    points: float        # weight * subscore * 100
    share: float         # points / total score (0..1)
    evidence: str = ""

    @property
    def percent(self) -> float:
        return self.share * 100


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def as_list(value: Iterable[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(part).strip() for part in value if str(part).strip()]


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return date.today()
