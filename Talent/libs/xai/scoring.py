"""Explainable outfit scoring.

The whole model is deliberately additive::

    score        = 100 * SUM(w_i * s_i)          w_i in [0, 1], SUM(w) == 1
    points_i     = 100 * w_i * s_i               SUM(points) == score
    share_i      = points_i / score              SUM(share) == 1

Because nothing is coupled, a counterfactual ("what if it rains?") changes
exactly one row and the delta decomposition is exact rather than approximate.
That is what makes the What-If panel trustworthy, and it is the honest
alternative to calling an ad-hoc weighted sum "SHAP".

Weights live in ``libs/xai/weights.json`` so the numbers from the written
report can be dropped in without touching code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from libs.models import Context, Contribution, Garment, Outfit, clamp, parse_date

WEIGHTS_PATH = Path(__file__).resolve().parent / "weights.json"

CRITERIA = {
    "color": "Colour Harmony",
    "occasion": "Occasion & Style Fit",
    "weather": "Weather Suitability",
    "freshness": "Freshness & Anti-Repetition",
}

CRITERIA_DETAIL = {
    "color": ("Neutral contrast", "Clashing palette", "Colour pairing"),
    "occasion": ("Tagged for occasion", "Partly off-brief", "Occasion tags"),
    "weather": ("Breathable for today", "Too warm / too light", "Fabric weight"),
    "freshness": ("Unworn recently", "Repeat risk", "Rest cycle"),
}

FALLBACK_WEIGHTS = {"color": 0.30, "occasion": 0.28, "weather": 0.24, "freshness": 0.18}


@dataclass
class Evaluation:
    score: float
    contributions: list[Contribution]

    @property
    def total_points(self) -> float:
        return sum(c.points for c in self.contributions)

    def by_key(self) -> dict[str, Contribution]:
        return {c.key: c for c in self.contributions}

    def delta_from(self, other: "Evaluation") -> dict[str, float]:
        before = other.by_key()
        return {
            c.key: c.points - before[c.key].points if c.key in before else c.points
            for c in self.contributions
        }


def load_config(path: Path | None = None) -> dict:
    target = path or WEIGHTS_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"weights": dict(FALLBACK_WEIGHTS), "params": {}}
    weights = data.get("weights") or {}
    if abs(sum(weights.values()) - 1.0) > 0.001:
        weights = dict(FALLBACK_WEIGHTS)
    return {"weights": weights, "params": data.get("params", {})}


# --------------------------------------------------------------------------
# Criteria
# --------------------------------------------------------------------------
def _color(garments: list[Garment], ctx: Context, params: dict,
           stats: dict | None = None) -> tuple[float, str, str]:
    families = {g.color_family for g in garments}
    non_neutral = families - {"neutral"}
    patterned = sum(1 for g in garments if g.pattern not in ("Solid", ""))

    if not non_neutral:
        value = params.get("neutral_only_score", 0.93)
        detail = "Neutral contrast"
        evidence = "Every piece stays inside the neutral family"
    elif len(non_neutral) == 1:
        accent = next(iter(non_neutral))
        if families == {accent}:
            value = params.get("same_family_score", 0.74)
            detail = "Tonal palette"
            evidence = f"Every piece stays in the {accent} family"
        else:
            value = params.get("single_accent_score", 0.86)
            detail = "One accent colour"
            evidence = f"Neutral base with a single {accent} accent"
    else:
        value = params.get("clash_score", 0.48)
        detail = "Clashing palette"
        mixed = ", ".join(sorted(non_neutral))
        evidence = f"Conflicting non-neutral families ({mixed})"

    if patterned >= 2:
        value = max(0.05, value - params.get("pattern_conflict_penalty", 0.15))
        evidence += f" · {patterned} competing patterns"
    return clamp(value), detail, evidence


def _occasion(garments: list[Garment], ctx: Context, params: dict,
              stats: dict | None = None) -> tuple[float, str, str]:
    if not garments:
        return 0.0, "No pieces", "No garments selected"
    matches = sum(1 for g in garments if ctx.occasion in g.occasions)
    ratio = matches / len(garments)
    value = 0.30 + 0.70 * ratio
    if ratio == 1:
        detail = "Fully on-brief"
    elif ratio >= 0.6:
        detail = "Mostly on-brief"
    else:
        detail = "Partly off-brief"
    evidence = f"{matches}/{len(garments)} pieces tagged for {ctx.occasion}"
    return clamp(value), detail, evidence


def _weather(garments: list[Garment], ctx: Context, params: dict,
             stats: dict | None = None) -> tuple[float, str, str]:
    if not garments:
        return 0.0, "No pieces", "No garments selected"
    avg_breath = sum(g.breathability for g in garments) / len(garments) / 10
    avg_warmth = sum(g.warmth for g in garments) / len(garments) / 10
    ideal = clamp((ctx.temperature - 6) / 30)

    comfort = 1 - abs(ideal - avg_breath)
    notes = [f"Avg breathability {avg_breath * 10:.1f}/10 at {ctx.temperature:.0f}°C"]

    if ctx.temperature < params.get("cold_temp_below", 18):
        comfort = comfort * 0.55 + clamp(avg_warmth) * 0.45
        notes.append("cold-weather warmth weighted in")

    has_outer = any(g.category == "outer" for g in garments)
    if ctx.is_rain:
        if not has_outer:
            comfort *= params.get("rain_without_outer_penalty", 0.62)
            notes.append("rain without a protective layer")
        else:
            notes.append("outer layer covers the rain")

    if comfort >= 0.8:
        detail = "Breathable for today"
    elif comfort >= 0.55:
        detail = "Acceptable for today"
    else:
        detail = "Poorly matched to weather"
    return clamp(comfort), detail, "; ".join(notes)


def _freshness(garments: list[Garment], ctx: Context, params: dict,
               stats: dict | None = None) -> tuple[float, str, str]:
    if not garments:
        return 0.0, "No pieces", "No garments selected"
    anti_days = max(1, ctx.anti_rep_days)
    gaps = [item_days_since(g, ctx, stats) for g in garments]
    gaps = [g for g in gaps if g is not None]
    if not gaps:
        return 1.0, "Never worn", "Every piece is fresh out of the closet"
    closest = min(gaps)
    if closest <= params.get("freshness_floor_days", 1):
        value = 0.06
        detail = "Repeat risk"
        evidence = f"Closest piece was worn {closest} day(s) ago"
    else:
        value = clamp(closest / anti_days)
        detail = "Fresh rotation" if value >= 0.9 else "Resting"
        evidence = f"Closest piece last worn {closest} days ago (target {anti_days}+)"
    return value, detail, evidence


_CRITERION_FNS = {
    "color": _color,
    "occasion": _occasion,
    "weather": _weather,
    "freshness": _freshness,
}


def item_days_since(garment: Garment, ctx: Context, stats: dict | None = None) -> int | None:
    """Days since this garment was last worn, or None when never worn."""
    last = (stats or {}).get(garment.id, {}).get("last") if stats else None
    if not last:
        return None
    return max(0, (ctx.today - parse_date(last)).days)


def evaluate(
    outfit: Outfit,
    ctx: Context,
    stats: dict | None = None,
    config: dict | None = None,
) -> Evaluation:
    """Score an outfit and decompose the score into additive contributions."""
    cfg = config or load_config()
    weights: dict[str, float] = cfg["weights"]
    params: dict = cfg.get("params", {})

    garments = outfit.ordered_items()
    subscores: dict[str, tuple[float, str, str]] = {}
    for key, fn in _CRITERION_FNS.items():
        subscores[key] = fn(garments, ctx, params, stats)

    raw = sum(weights.get(key, 0.0) * subscores[key][0] for key in CRITERIA)
    score = round(100 * raw, 1)

    contributions: list[Contribution] = []
    for key, label in CRITERIA.items():
        sub, detail, evidence = subscores[key]
        weight = weights.get(key, 0.0)
        points = round(100 * weight * sub, 2)
        contributions.append(Contribution(
            key=key,
            label=label,
            detail=detail,
            subscore=sub,
            weight=weight,
            points=points,
            share=(points / score) if score else 0.0,
            evidence=evidence,
        ))

    # Guard against float dust so the panel always adds up on screen.
    drift = round(score - sum(c.points for c in contributions), 2)
    if contributions and abs(drift) >= 0.01:
        contributions[0].points = round(contributions[0].points + drift, 2)

    return Evaluation(score=score, contributions=contributions)
