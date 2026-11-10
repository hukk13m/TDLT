"""SQLite schema and connection handling.

The database lives in ``assets/data/wardrobe.db`` and is created (and seeded)
on first run, so the app is usable straight after cloning.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "assets" / "data" / "wardrobe.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS garments (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT NOT NULL,
    subtype      TEXT NOT NULL DEFAULT '',
    color_name   TEXT NOT NULL DEFAULT '',
    color_hex    TEXT NOT NULL DEFAULT '#CCCCCC',
    color_family TEXT NOT NULL DEFAULT 'neutral',
    pattern      TEXT NOT NULL DEFAULT 'Solid',
    material     TEXT NOT NULL DEFAULT '',
    breathability INTEGER NOT NULL DEFAULT 5,
    warmth       INTEGER NOT NULL DEFAULT 5,
    seasons      TEXT NOT NULL DEFAULT '',
    occasions    TEXT NOT NULL DEFAULT '',
    image_path   TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS outfits (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    score       REAL NOT NULL DEFAULT 0,
    source      TEXT NOT NULL DEFAULT 'ai',
    is_favorite INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS outfit_items (
    outfit_id  TEXT NOT NULL,
    garment_id TEXT NOT NULL,
    slot       TEXT NOT NULL,
    PRIMARY KEY (outfit_id, garment_id)
);

CREATE TABLE IF NOT EXISTS wear_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    outfit_id TEXT NOT NULL,
    worn_on   TEXT NOT NULL,
    feedback  INTEGER,
    note      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weather_cache (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    fetched_at TEXT NOT NULL,
    payload    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_wear_on ON wear_log (worn_on);
CREATE INDEX IF NOT EXISTS idx_items_outfit ON outfit_items (outfit_id);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    target = Path(path) if path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def table_row_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
