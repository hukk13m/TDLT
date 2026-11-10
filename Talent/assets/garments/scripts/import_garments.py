"""Import a garment CSV into the Acloset Studio SQLite database.

Dry run by default: it validates the file and prints what would change.
Add --write to insert or update rows. Add --reset --yes to clear the
wardrobe, saved outfits and wear log first, so the imported set is the only
content in the app.

Examples:
  python assets/garments/scripts/import_garments.py
  python assets/garments/scripts/import_garments.py --write
  python assets/garments/scripts/import_garments.py --write --reset --yes
"""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from libs import db  # noqa: E402
from libs.models import Garment  # noqa: E402
from libs.repo import Repository  # noqa: E402

CATEGORIES = {"top", "bottom", "outer", "shoes"}
FAMILIES = {"neutral", "cool", "earth", "warm"}
SEASONS = {"Spring", "Summer", "Autumn", "Winter"}


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def to_list(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def validate(rows: list[dict]) -> list[str]:
    problems = []
    seen = set()
    for n, row in enumerate(rows, start=2):
        rid = row.get("id", "").strip()
        if not rid:
            problems.append(f"line {n}: missing id")
            continue
        if rid in seen:
            problems.append(f"line {n}: duplicate id {rid}")
        seen.add(rid)
        if row.get("category") not in CATEGORIES:
            problems.append(f"line {n}: bad category {row.get('category')!r}")
        if row.get("color_family") not in FAMILIES:
            problems.append(f"line {n}: bad color_family {row.get('color_family')!r}")
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", row.get("color_hex", "")):
            problems.append(f"line {n}: bad color_hex {row.get('color_hex')!r}")
        for field in ("breathability", "warmth"):
            try:
                value = int(row[field])
                if not 1 <= value <= 10:
                    raise ValueError
            except (KeyError, ValueError):
                problems.append(f"line {n}: {field} must be 1..10")
        bad_seasons = set(to_list(row.get("seasons", ""))) - SEASONS
        if bad_seasons:
            problems.append(f"line {n}: unknown seasons {sorted(bad_seasons)}")
        if not to_list(row.get("occasions", "")):
            problems.append(f"line {n}: no occasions")
    return problems


def to_garment(row: dict) -> Garment:
    return Garment(
        id=row["id"].strip(),
        name=row["name"].strip(),
        category=row["category"].strip(),
        subtype=row.get("subtype", "").strip(),
        color_name=row.get("color_name", "").strip(),
        color_hex=row.get("color_hex", "#CCCCCC").strip(),
        color_family=row.get("color_family", "neutral").strip(),
        pattern=row.get("pattern", "Solid").strip() or "Solid",
        material=row.get("material", "").strip(),
        breathability=int(row["breathability"]),
        warmth=int(row["warmth"]),
        seasons=to_list(row.get("seasons", "")),
        occasions=to_list(row.get("occasions", "")),
        image_path=row.get("image_path", "").strip(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="?", default=str(ROOT / "assets" / "garments" / "scraped_30.csv"))
    parser.add_argument("--db", default=str(ROOT / "assets" / "data" / "wardrobe.db"))
    parser.add_argument("--write", action="store_true", help="commit changes")
    parser.add_argument("--reset", action="store_true", help="clear wardrobe, outfits and wear log")
    parser.add_argument("--yes", action="store_true", help="required with --reset")
    args = parser.parse_args()

    path = Path(args.csv)
    rows = read_rows(path)
    problems = validate(rows)
    if problems:
        print("validation failed:")
        for problem in problems:
            print(" ", problem)
        raise SystemExit(1)

    from collections import Counter
    counts = Counter(row["category"] for row in rows)
    print(f"{path.name}: {len(rows)} rows")
    print("  " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))

    images_dir = ROOT / "assets" / "garments"
    missing_images = [r["id"] for r in rows
                      if not (images_dir / f"{r['id']}.jpg").exists()]
    if missing_images:
        print(f"  warning: no image for {', '.join(missing_images)}")

    db_path = Path(args.db)
    known: set[str] = set()
    if db_path.exists() and not args.reset:
        existing = sqlite3.connect(str(db_path))
        known = {row[0] for row in existing.execute("SELECT id FROM garments")}
        existing.close()

    print()
    print(f"  {'id':6} {'status':7} {'category':7} {'name':22} colour")
    print(f"  {'-' * 6} {'-' * 7} {'-' * 7} {'-' * 22} {'-' * 14}")
    for row in rows:
        status = "update" if row["id"] in known else "new"
        colour = f"{row.get('color_name', '')} {row.get('color_hex', '')}".strip()
        print(f"  {row['id']:6} {status:7} {row['category']:7} "
              f"{row['name'][:22]:22} {colour}")
    print()
    print(f"  {len(rows) - len([r for r in rows if r['id'] in known])} new, "
          f"{len([r for r in rows if r['id'] in known])} already in the database")

    if not args.write:
        print()
        print("dry run, nothing written.")
        print("to apply, put the flag after the script name:")
        print(f"  python {Path(__file__).name} --write")
        return

    if args.reset:
        if not args.yes:
            raise SystemExit("--reset needs --yes")
        conn = db.connect(args.db)
        conn.executescript(
            "DELETE FROM wear_log; DELETE FROM outfit_items; DELETE FROM outfits;"
            " DELETE FROM garments;"
        )
        conn.commit()
        conn.close()
        print("cleared wardrobe, outfits and wear log")

    conn = db.connect(args.db)
    repo = Repository(conn)
    for row in rows:
        repo.upsert_garment(to_garment(row))
    total = conn.execute("SELECT COUNT(*) FROM garments").fetchone()[0]
    conn.close()
    print(f"imported {len(rows)} rows, wardrobe now has {total} garments")


if __name__ == "__main__":
    main()
