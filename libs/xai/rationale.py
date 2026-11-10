"""Turning numbers into sentences.

Two entry points:

* :func:`build_rationale` - the paragraph shown under the contribution bars.
* :func:`build_insights`  - the short observations on the Analytics screen.

Both are template driven on purpose: every sentence can be traced back to a
criterion, so nothing on screen is un-explainable hand-waving.
"""

from __future__ import annotations

from libs.models import Context, Outfit
from libs.xai.scoring import Evaluation


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def build_rationale(evaluation: Evaluation, context: Context, outfit: Outfit) -> str:
    ranked = sorted(evaluation.contributions, key=lambda c: c.points, reverse=True)
    top, second = ranked[0], ranked[1]
    weakest = min(ranked, key=lambda c: c.subscore)

    parts = [
        f"This look scores {evaluation.score:.0f}/100 for {context.occasion.lower()} "
        f"at {context.temperature:.0f}°C.",
        f"{top.label} contributes {top.points:.1f} pts ({top.percent:.0f}%) - "
        f"{_lower_first(top.evidence)}.",
        f"{second.label} adds {second.points:.1f} pts ({second.percent:.0f}%) - "
        f"{_lower_first(second.evidence)}.",
    ]

    if weakest.subscore < 0.5:
        parts.append(
            f"The weak point is {weakest.label.lower()} ({weakest.evidence}); "
            "swap that piece to gain the most."
        )
    else:
        parts.append("No criterion drops below 0.5, so this is a safe recommendation.")
    return " ".join(parts)


def build_repeat_warning(evaluation: Evaluation, context: Context) -> str:
    freshness = evaluation.by_key().get("freshness")
    if freshness and freshness.subscore < 0.2:
        return "Repeat detected - at least one piece was worn in the last day."
    return ""


def build_insights(analytics: dict) -> list[str]:
    """Small, defensible observations for the Analytics screen."""
    insights: list[str] = []
    density = analytics.get("density", {})
    total = max(1, analytics.get("total", 1))
    tops = density.get("top", 0)
    bottoms = density.get("bottom", 0)
    if bottoms:
        ratio = tops / bottoms
        if ratio >= 1.3:
            insights.append(
                f"Tops outnumber bottoms {ratio:.1f}:1 - you can build more outfits "
                "by adding bottoms instead of tops."
            )
        elif ratio <= 0.77:
            insights.append(
                f"Only {tops} tops for {bottoms} bottoms - a couple of new tops would "
                "unlock a lot of combinations."
            )

    sleeping = analytics.get("sleeping", [])
    if sleeping:
        names = ", ".join(g.name for g in sleeping[:2])
        insights.append(
            f"{len(sleeping)} items have been idle for 14+ days ({names}). "
            "Styling them once resets the anti-repetition clock."
        )

    avg_gap = analytics.get("avg_gap", 0)
    if avg_gap:
        if avg_gap < 3:
            insights.append(
                f"Average gap between wears is only {avg_gap:.1f} days, below the 3-day "
                "rest target - the rotation is repeating itself."
            )
        else:
            insights.append(
                f"Average gap between wears is {avg_gap:.1f} days, comfortably above the "
                "3-day rest target."
            )

    most_worn = analytics.get("most_worn", [])
    stats = analytics.get("stats", {})
    if most_worn:
        hero = most_worn[0]
        count = stats.get(hero.id, {}).get("count", 0)
        if count:
            insights.append(
                f"{hero.name} is the workhorse of the closet ({count} wears). "
                "Consider a second neutral shirt so it can rest."
            )
    return insights[:4]
