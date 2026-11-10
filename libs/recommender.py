"""Candidate generation + ranking.

Only ~450-1800 combinations exist for a 28 item closet, so the recommender
scores every valid outfit instead of sampling. That keeps the "Rank #1 / #2"
ordering exact and lets the What-If panel be honest: when the context changes,
the entire ranking is genuinely recomputed.
"""

from __future__ import annotations

from dataclasses import replace
from itertools import product

from libs.models import Context, Garment, Outfit
from libs.xai.scoring import Evaluation, evaluate, item_days_since


def outfit_name(items: dict[str, Garment]) -> str:
    names = [items[slot].name for slot in ("top", "bottom") if slot in items]
    return " + ".join(names) if names else "Untitled outfit"


def add_outerwear(ctx: Context) -> bool:
    """Decide whether outerwear participates in candidate generation.

    auto    - include when it is cold or raining (default behaviour)
    include - always include outerwear when the pool is not empty
    exclude - never include outerwear
    """
    mode = getattr(ctx, "outer_mode", "auto")
    if mode == "include":
        return True
    if mode == "exclude":
        return False
    return ctx.is_rain or ctx.temperature < 22


def build_candidates(
    garments: list[Garment],
    ctx: Context,
    locks: dict[str, str] | None = None,
) -> list[Outfit]:
    locks = locks or {}
    pool: dict[str, list[Garment]] = {"top": [], "bottom": [], "shoes": [], "outer": []}
    for garment in garments:
        pool.get(garment.category, []).append(garment)

    for slot, garment_id in locks.items():
        chosen = next((g for g in garments if g.id == garment_id), None)
        if chosen:
            pool[slot] = [chosen]

    if not pool["top"] or not pool["bottom"] or not pool["shoes"]:
        return []

    want_outer = add_outerwear(ctx) and bool(pool["outer"])
    outer_sets = (
        product(pool["top"], pool["bottom"], pool["shoes"], pool["outer"])
        if want_outer
        else ((t, b, s, None) for t, b, s in product(pool["top"], pool["bottom"], pool["shoes"]))
    )

    candidates: list[Outfit] = []
    for top, bottom, shoes, outer in outer_sets:
        items = {"top": top, "bottom": bottom, "shoes": shoes}
        if outer is not None:
            items["outer"] = outer
        candidates.append(Outfit(id="", name=outfit_name(items), items=items))
    return candidates


def is_recent_repeat(outfit: Outfit, stats: dict, ctx: Context) -> bool:
    """True when any piece was worn inside the anti-repetition window."""
    window = max(1, ctx.anti_rep_days)
    for garment in outfit.ordered_items():
        days = item_days_since(garment, ctx, stats)
        if days is not None and days < window:
            return True
    return False


def recommend(
    garments: list[Garment],
    ctx: Context,
    stats: dict,
    config: dict | None = None,
    top_n: int = 5,
    locks: dict[str, str] | None = None,
) -> list[tuple[Outfit, Evaluation]]:
    """Return the best outfits, freshest first when strict mode is on."""
    candidates = build_candidates(garments, ctx, locks)
    if not candidates:
        return []

    if ctx.strict_anti_rep:
        fresh = [o for o in candidates if not is_recent_repeat(o, stats, ctx)]
        if fresh:
            candidates = fresh
        # If filtering empties the pool we keep the unfiltered list on purpose:
        # showing "worn recently" is better than showing nothing, and the
        # freshness bar already says why the score is low.

    scored: list[tuple[Outfit, Evaluation]] = []
    for outfit in candidates:
        evaluation = evaluate(outfit, ctx, stats, config)
        outfit.score = evaluation.score
        scored.append((outfit, evaluation))

    def _rank_key(pair: tuple[Outfit, Evaluation]):
        outfit, evaluation = pair
        by_key = evaluation.by_key()
        # Stable, meaningful tie-break so identical totals still sort sensibly.
        return (
            -evaluation.score,
            -by_key.get("freshness", None).subscore if by_key.get("freshness") else 0.0,
            -by_key.get("weather", None).subscore if by_key.get("weather") else 0.0,
            -by_key.get("occasion", None).subscore if by_key.get("occasion") else 0.0,
            -by_key.get("color", None).subscore if by_key.get("color") else 0.0,
            tuple(outfit.item_ids),
        )

    scored.sort(key=_rank_key)

    # Drop near-duplicates so alternates offer real variety.
    seen: set[tuple[str, ...]] = set()
    unique: list[tuple[Outfit, Evaluation]] = []
    for outfit, evaluation in scored:
        items = outfit.ordered_items()
        top_bottom = tuple(sorted(g.id for g in items[:2]))
        if top_bottom in seen:
            continue
        seen.add(top_bottom)
        unique.append((outfit, evaluation))
        if len(unique) >= top_n:
            break
    return unique


def what_if(
    base_outfit: Outfit,
    base_context: Context,
    stats: dict,
    config: dict | None = None,
    **changes,
) -> tuple[Evaluation, Context]:
    """Re-score the same outfit under a modified context."""
    context = replace(base_context, **changes)
    return evaluate(base_outfit, context, stats, config), context
