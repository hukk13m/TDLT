"""Data access layer.

Every read/write the UI performs goes through :class:`Repository`. Keeping it
in one place means the three screens always agree on numbers such as "worn 8
times" - those are always derived from ``wear_log``, never cached on a row.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, timedelta

from libs.models import Context, Garment, Outfit, WearEntry, as_list, parse_date
from libs.seed_data import SEED_GARMENTS, SEED_WEAR_HISTORY


def _new_id(prefix: str = "OF") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ------------------------------------------------------------------ seed
    def ensure_seeded(self) -> bool:
        """Seed the demo wardrobe once. Returns True when seeding happened."""
        if self.conn.execute("SELECT COUNT(*) FROM garments").fetchone()[0]:
            return False
        for row in SEED_GARMENTS:
            self.upsert_garment(Garment(
                id=row["id"], name=row["name"], category=row["category"],
                subtype=row["subtype"], color_name=row["color_name"],
                color_hex=row["color_hex"], color_family=row["color_family"],
                pattern=row["pattern"], material=row["material"],
                breathability=row["breathability"], warmth=row["warmth"],
                seasons=list(row["seasons"]), occasions=list(row["occasions"]),
                created_at=date.today().isoformat(),
            ))
        today = date.today()
        by_id = {g.id: g for g in self.list_garments()}
        for days_ago, slots in SEED_WEAR_HISTORY:
            outfit = Outfit(
                id=_new_id(),
                name="",
                source="seed",
                created_at=(today - timedelta(days=days_ago)).isoformat(),
            )
            for slot, gid in slots:
                garment = by_id.get(gid)
                if garment:
                    outfit.items[slot] = garment
            outfit.name = _auto_name(outfit)
            self.conn.execute(
                "INSERT INTO outfits (id, name, score, source, is_favorite, created_at)"
                " VALUES (?,?,?,?,?,?)",
                (outfit.id, outfit.name, 0, "seed", 0, outfit.created_at),
            )
            for slot, garment in outfit.items.items():
                self.conn.execute(
                    "INSERT OR IGNORE INTO outfit_items (outfit_id, garment_id, slot)"
                    " VALUES (?,?,?)",
                    (outfit.id, garment.id, slot),
                )
            self.conn.execute(
                "INSERT INTO wear_log (outfit_id, worn_on, feedback, note) VALUES (?,?,?,?)",
                (outfit.id, (today - timedelta(days=days_ago)).isoformat(),
                 None if days_ago > 3 else 1, ""),
            )
        self.conn.commit()
        return True

    # -------------------------------------------------------------- garments
    def list_garments(
        self,
        search: str = "",
        category: str = "",
        sort: str = "recent",
        season: str = "",
    ) -> list[Garment]:
        rows = self.conn.execute("SELECT * FROM garments").fetchall()
        items = [self._garment_from_row(r) for r in rows]
        if search:
            needle = search.lower()
            items = [
                g for g in items
                if needle in " ".join(
                    [g.id, g.name, g.category, g.color_name, g.material, g.pattern]
                ).lower()
            ]
        if category:
            items = [g for g in items if g.category == category]
        if season:
            items = [g for g in items if season in g.seasons]
        stats = self.wear_stats()
        if sort == "least_worn":
            items.sort(key=lambda g: (stats.get(g.id, {}).get("count", 0), g.id))
        elif sort == "name":
            items.sort(key=lambda g: g.name)
        elif sort == "last_worn":
            items.sort(key=lambda g: stats.get(g.id, {}).get("last") or "", reverse=True)
        else:  # recent first
            items.sort(key=lambda g: g.id)
        return items

    def get_garment(self, garment_id: str) -> Garment | None:
        row = self.conn.execute(
            "SELECT * FROM garments WHERE id = ?", (garment_id,)
        ).fetchone()
        return self._garment_from_row(row) if row else None

    def next_garment_id(self) -> str:
        rows = self.conn.execute("SELECT id FROM garments").fetchall()
        numbers = []
        for row in rows:
            tail = str(row["id"]).split("-")[-1]
            if tail.isdigit():
                numbers.append(int(tail))
        return f"IT-{(max(numbers) + 1) if numbers else 1:02d}"

    def upsert_garment(self, garment: Garment) -> None:
        self.conn.execute(
            """INSERT INTO garments (id, name, category, subtype, color_name,
                    color_hex, color_family, pattern, material, breathability, warmth,
                    seasons, occasions, image_path, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, category=excluded.category,
                    subtype=excluded.subtype, color_name=excluded.color_name,
                    color_hex=excluded.color_hex, color_family=excluded.color_family,
                    pattern=excluded.pattern, material=excluded.material,
                    breathability=excluded.breathability, warmth=excluded.warmth,
                    seasons=excluded.seasons, occasions=excluded.occasions,
                    image_path=excluded.image_path""",
            (
                garment.id, garment.name, garment.category, garment.subtype,
                garment.color_name, garment.color_hex, garment.color_family,
                garment.pattern, garment.material, garment.breathability,
                garment.warmth, ",".join(garment.seasons), ",".join(garment.occasions),
                garment.image_path, garment.created_at or date.today().isoformat(),
            ),
        )
        self.conn.commit()

    def delete_garment(self, garment_id: str) -> None:
        self.conn.execute("DELETE FROM outfit_items WHERE garment_id = ?", (garment_id,))
        self.conn.execute("DELETE FROM garments WHERE id = ?", (garment_id,))
        self.conn.commit()

    # ------------------------------------------------------------------ wear
    def wear_stats(self) -> dict[str, dict]:
        """garment_id -> {"count": int, "last": iso-date-or-empty}"""
        rows = self.conn.execute(
            """SELECT oi.garment_id AS gid, COUNT(w.id) AS n, MAX(w.worn_on) AS last
               FROM outfit_items oi JOIN wear_log w ON w.outfit_id = oi.outfit_id
               GROUP BY oi.garment_id"""
        ).fetchall()
        return {r["gid"]: {"count": r["n"], "last": r["last"] or ""} for r in rows}

    def log_wear(self, outfit: Outfit, worn_on: date | None = None,
                 feedback: int | None = None, note: str = "") -> str:
        """Persist the outfit (if new) and append a wear entry."""
        stylish = outfit.id or _new_id()
        if not self.conn.execute("SELECT 1 FROM outfits WHERE id = ?", (stylish,)).fetchone():
            self.conn.execute(
                "INSERT INTO outfits (id, name, score, source, is_favorite, created_at)"
                " VALUES (?,?,?,?,?,?)",
                (stylish, outfit.name or _auto_name(outfit), outfit.score,
                 outfit.source, 1 if outfit.is_favorite else 0,
                 date.today().isoformat()),
            )
            for slot, garment in outfit.items.items():
                self.conn.execute(
                    "INSERT OR IGNORE INTO outfit_items (outfit_id, garment_id, slot)"
                    " VALUES (?,?,?)",
                    (stylish, garment.id, slot),
                )
        self.conn.execute(
            "INSERT INTO wear_log (outfit_id, worn_on, feedback, note) VALUES (?,?,?,?)",
            (stylish, (worn_on or date.today()).isoformat(), feedback, note),
        )
        self.conn.commit()
        outfit.id = stylish
        return stylish

    def wear_entries(self, limit: int = 100, month: str = "") -> list[WearEntry]:
        sql = "SELECT * FROM wear_log"
        params: list = []
        if month:
            sql += " WHERE substr(worn_on, 1, 7) = ?"
            params.append(month)
        sql += " ORDER BY worn_on DESC, id DESC LIMIT ?"
        params.append(limit)
        entries = []
        for row in self.conn.execute(sql, params).fetchall():
            entries.append(WearEntry(
                id=row["id"], outfit_id=row["outfit_id"], worn_on=row["worn_on"],
                feedback=row["feedback"], note=row["note"],
                outfit=self.get_outfit(row["outfit_id"]),
            ))
        return entries

    def set_feedback(self, entry_id: int, feedback: int | None) -> None:
        self.conn.execute("UPDATE wear_log SET feedback = ? WHERE id = ?", (feedback, entry_id))
        self.conn.commit()

    # --------------------------------------------------------------- outfits
    def save_outfit(self, outfit: Outfit) -> str:
        outfit.id = outfit.id or _new_id()
        outfit.name = outfit.name or _auto_name(outfit)
        self.conn.execute(
            "INSERT OR REPLACE INTO outfits (id, name, score, source, is_favorite, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (outfit.id, outfit.name, outfit.score, outfit.source,
             1 if outfit.is_favorite else 0, outfit.created_at or date.today().isoformat()),
        )
        self.conn.execute("DELETE FROM outfit_items WHERE outfit_id = ?", (outfit.id,))
        for slot, garment in outfit.items.items():
            self.conn.execute(
                "INSERT OR IGNORE INTO outfit_items (outfit_id, garment_id, slot)"
                " VALUES (?,?,?)", (outfit.id, garment.id, slot),
            )
        self.conn.commit()
        return outfit.id

    def get_outfit(self, outfit_id: str) -> Outfit | None:
        row = self.conn.execute("SELECT * FROM outfits WHERE id = ?", (outfit_id,)).fetchone()
        if not row:
            return None
        outfit = Outfit(
            id=row["id"], name=row["name"], score=row["score"], source=row["source"],
            is_favorite=bool(row["is_favorite"]), created_at=row["created_at"],
        )
        for item in self.conn.execute(
            "SELECT garment_id, slot FROM outfit_items WHERE outfit_id = ?", (outfit_id,)
        ).fetchall():
            garment = self.get_garment(item["garment_id"])
            if garment:
                outfit.items[item["slot"]] = garment
        return outfit

    def list_outfits(self, saved_only: bool = True, limit: int = 200) -> list[Outfit]:
        sql = "SELECT * FROM outfits"
        params: list = []
        if saved_only:
            sql += " WHERE source != 'seed'"
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        outfits = []
        for row in self.conn.execute(sql, params).fetchall():
            outfit = self.get_outfit(row["id"])
            if outfit:
                outfits.append(outfit)
        return outfits

    def delete_outfit(self, outfit_id: str) -> None:
        self.conn.execute("DELETE FROM outfit_items WHERE outfit_id = ?", (outfit_id,))
        self.conn.execute("DELETE FROM outfits WHERE id = ?", (outfit_id,))
        self.conn.commit()

    def outfits_on(self, day: date) -> list[Outfit]:
        rows = self.conn.execute(
            "SELECT outfit_id FROM wear_log WHERE worn_on = ?", (day.isoformat(),)
        ).fetchall()
        result = []
        for row in rows:
            outfit = self.get_outfit(row["outfit_id"])
            if outfit:
                result.append(outfit)
        return result

    # -------------------------------------------------------------- settings
    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?,?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def load_context(self) -> Context:
        city = self.get_setting("city", "Ho Chi Minh City")
        try:
            lat = float(self.get_setting("lat", "10.8231"))
            lon = float(self.get_setting("lon", "106.6297"))
        except ValueError:
            lat, lon = 10.8231, 106.6297
        outer_mode = self.get_setting("outer_mode", "auto")
        if outer_mode not in ("auto", "include", "exclude"):
            outer_mode = "auto"
        return Context(
            occasion=self.get_setting("occasion", "University"),
            style_goal=self.get_setting("style_goal", "Smart Casual"),
            city=city,
            anti_rep_days=int(self.get_setting("anti_rep_days", "3")),
            strict_anti_rep=self.get_setting("strict_anti_rep", "1") == "1",
            outer_mode=outer_mode,
        ), (lat, lon)

    def save_context(self, context: Context) -> None:
        self.set_setting("occasion", context.occasion)
        self.set_setting("style_goal", context.style_goal)
        self.set_setting("anti_rep_days", str(context.anti_rep_days))
        self.set_setting("strict_anti_rep", "1" if context.strict_anti_rep else "0")
        self.set_setting("outer_mode", getattr(context, "outer_mode", "auto"))

    # --------------------------------------------------------- weather cache
    def get_weather_cache(self) -> dict | None:
        row = self.conn.execute("SELECT * FROM weather_cache WHERE id = 1").fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            return None
        payload["fetched_at"] = row["fetched_at"]
        return payload

    def set_weather_cache(self, payload: dict) -> None:
        data = dict(payload)
        fetched = data.pop("fetched_at", "")
        self.conn.execute(
            "INSERT INTO weather_cache (id, fetched_at, payload) VALUES (1, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET fetched_at = excluded.fetched_at,"
            " payload = excluded.payload",
            (fetched, json.dumps(data)),
        )
        self.conn.commit()

    # ------------------------------------------------------------- analytics
    def analytics(self) -> dict:
        stats = self.wear_stats()
        garments = self.list_garments()
        total = len(garments)
        worn_items = [g for g in garments if stats.get(g.id, {}).get("count", 0) > 0]
        today = date.today()

        def days_since(garment: Garment) -> int | None:
            last = stats.get(garment.id, {}).get("last")
            if not last:
                return None
            return (today - parse_date(last)).days

        sleeping = [
            g for g in garments if (days_since(g) or 999) >= 14
        ]
        density: dict[str, int] = {}
        for garment in garments:
            density[garment.category] = density.get(garment.category, 0) + 1

        most_worn = sorted(
            garments, key=lambda g: stats.get(g.id, {}).get("count", 0), reverse=True
        )[:3]

        wear_days = sorted({
            row["worn_on"] for row in
            self.conn.execute("SELECT worn_on FROM wear_log").fetchall()
        })
        gaps = []
        for previous, current in zip(wear_days, wear_days[1:]):
            gaps.append((parse_date(current) - parse_date(previous)).days)
        avg_gap = round(sum(gaps) / len(gaps), 1) if gaps else 0.0

        collisions = 0
        if wear_days:
            recent = [d for d in wear_days if (today - parse_date(d)).days <= 14]
            collisions = max(0, len(recent) - len({d for d in recent}))
        repeat_rate = 0.0
        if wear_days:
            repeat_rate = round(100 * (1 - len(set(wear_days)) / max(1, len(wear_days))), 1)

        # Rest-window compliance: of every consecutive re-wear of the same
        # garment, how many respected the 3-day rest target. This is a real
        # rotation-health number, unlike counting distinct outfit ids.
        per_garment: dict[str, list[date]] = {}
        for row in self.conn.execute(
            "SELECT oi.garment_id AS gid, w.worn_on AS day"
            " FROM outfit_items oi JOIN wear_log w ON w.outfit_id = oi.outfit_id"
            " ORDER BY w.worn_on"
        ).fetchall():
            per_garment.setdefault(row["gid"], []).append(parse_date(row["day"]))
        pairs = 0
        compliant = 0
        for dates in per_garment.values():
            unique_days = sorted(set(dates))
            for previous, current in zip(unique_days, unique_days[1:]):
                pairs += 1
                if (current - previous).days >= 3:
                    compliant += 1
        rest_compliance = round(100 * compliant / pairs, 1) if pairs else 100.0

        return {
            "total": total,
            "utilization": round(100 * len(worn_items) / total, 1) if total else 0.0,
            "worn_count": len(worn_items),
            "sleeping": sleeping,
            "density": density,
            "most_worn": most_worn,
            "stats": stats,
            "avg_gap": avg_gap,
            "wear_days": wear_days,
            "collisions": collisions,
            "repeat_rate": repeat_rate,
            "rest_compliance": rest_compliance,
            "days_since": {g.id: days_since(g) for g in garments},
        }

    # ---------------------------------------------------------------- helper
    @staticmethod
    def _garment_from_row(row: sqlite3.Row) -> Garment:
        return Garment(
            id=row["id"], name=row["name"], category=row["category"],
            subtype=row["subtype"], color_name=row["color_name"],
            color_hex=row["color_hex"], color_family=row["color_family"],
            pattern=row["pattern"], material=row["material"],
            breathability=row["breathability"], warmth=row["warmth"],
            seasons=as_list(row["seasons"]), occasions=as_list(row["occasions"]),
            image_path=row["image_path"], created_at=row["created_at"],
        )


def _auto_name(outfit: Outfit) -> str:
    names = [g.name for g in outfit.ordered_items()[:2]]
    return " + ".join(names) if names else "Untitled outfit"
