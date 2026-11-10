"""Build a 30-item garment set for Acloset Studio from an open dataset.

Source: ashraq/fashion-product-images-small on Hugging Face (Myntra catalogue).
The "small" parquet carries 60x80 thumbnails, so metadata comes from it while
the 384x512 image for the same row is fetched from the derived dataset
benitomartin/fashion-product-images-small-384x512 through the HF datasets
server. Both point at the same rows in the same order.

Output:
  assets/garments/IT-30.jpg ... IT-59.jpg
  assets/garments/scraped_30.csv

Usage:
  python assets/garments/scripts/fetch_garments.py

Requires: pyarrow, pillow. The first run downloads about 270 MB of parquet
into scripts/.cache/; later runs reuse it. Images are cached too, so a rerun
only fills gaps.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

SCRIPTS = Path(__file__).resolve().parent
GARMENTS = SCRIPTS.parent
CACHE = SCRIPTS / ".cache"
START_ID = 30
TOTAL = 30

SHARDS = [
    "https://huggingface.co/datasets/ashraq/fashion-product-images-small/resolve/main/data/train-00000-of-00002-6cff4c59f91661c3.parquet",
    "https://huggingface.co/datasets/ashraq/fashion-product-images-small/resolve/main/data/train-00001-of-00002-bb459e5ac5f01e71.parquet",
]
ROWS_API = ("https://datasets-server.huggingface.co/rows?dataset="
            "benitomartin%2Ffashion-product-images-small-384x512"
            "&config=default&split=train&offset={offset}&length=1")

# Quotas per category and subtype. Sums to 30.
BUCKETS = [
    ("shirts", lambda r: r["articleType"] == "Shirts", 5),
    ("tees", lambda r: r["articleType"] == "Tshirts", 3),
    ("tops", lambda r: r["articleType"] == "Tops", 1),
    ("knits", lambda r: r["articleType"] in ("Sweaters", "Sweatshirts"), 2),
    ("jeans", lambda r: r["articleType"] == "Jeans", 3),
    ("trousers", lambda r: r["articleType"] == "Trousers", 3),
    ("shorts", lambda r: r["articleType"] == "Shorts", 1),
    ("skirts", lambda r: r["articleType"] == "Skirts", 1),
    ("jackets", lambda r: r["articleType"] == "Jackets", 4),
    ("blazers", lambda r: r["articleType"] == "Blazers", 1),
    ("casual shoes", lambda r: r["articleType"] == "Casual Shoes", 2),
    ("sports shoes", lambda r: r["articleType"] == "Sports Shoes", 2),
    ("formal shoes", lambda r: r["articleType"] == "Formal Shoes", 2),
]

# Colour order used to keep the set varied instead of five white shirts.
PREFERRED = {
    "shirts": ["White", "Blue", "Olive", "Pink", "Brown", "Black", "Grey"],
    "tees": ["Black", "White", "Grey", "Navy Blue", "Red"],
    "tops": ["Beige", "White", "Black", "Pink"],
    "knits": ["Grey", "Black", "Navy Blue", "Brown"],
    "jeans": ["Blue", "Black", "Grey", "Brown"],
    "trousers": ["Khaki", "Cream", "Black", "Grey", "Brown"],
    "shorts": ["Brown", "Khaki", "Black", "Navy Blue"],
    "skirts": ["Tan", "Black", "Brown", "Grey"],
    "jackets": ["Black", "Charcoal", "Olive", "Navy Blue", "Brown"],
    "blazers": ["Charcoal", "Navy Blue", "Black"],
    "casual shoes": ["White", "Black", "Tan", "Brown"],
    "sports shoes": ["Grey", "Black", "Blue", "White"],
    "formal shoes": ["Black", "Brown"],
}

# Some product rows do not describe the photo. Keyed by source id so the
# corrections survive a change in selection.
OVERRIDES = {
    2170: {"name": "Multi Plaid Shirt", "color_name": "Multi", "color_hex": "#8A8F98",
           "color_family": "neutral", "pattern": "Check"},
    59390: {"name": "Brown Loafers", "subtype": "loafer", "material": "Calf Leather",
            "color_name": "Brown", "color_hex": "#6B4A32", "color_family": "earth",
            "breathability": 4, "warmth": 4, "occasions": "Smart Casual,Formal"},
    26788: {"name": "Taupe Shirt", "pattern": "Solid", "color_name": "Taupe",
            "color_hex": "#8A7461", "color_family": "earth"},
    27525: {"name": "Olive Gilet", "subtype": "gilet", "color_name": "Olive",
            "color_hex": "#4C5740", "color_family": "earth"},
    5408: {"name": "Blue Sandals", "subtype": "sandal", "material": "Synthetic",
           "color_name": "Blue", "color_hex": "#2F5D8A", "color_family": "cool",
           "seasons": "Spring,Summer", "occasions": "Casual,Sport"},
}

HEX = {
    "Black": "#141518", "White": "#FAFAF9", "Blue": "#2F5D8A", "Navy Blue": "#1F3A5F",
    "Grey": "#7C828A", "Brown": "#6B4A32", "Red": "#A62B2B", "Green": "#3F6B4A",
    "Pink": "#D98FA5", "Purple": "#6B4C8A", "Silver": "#B9BEC4", "Beige": "#D9C9A8",
    "Yellow": "#D9B23A", "Orange": "#C96A2B", "Maroon": "#6E2637", "Cream": "#F3EBDD",
    "Khaki": "#B6A176", "Olive": "#4C5740", "Tan": "#A98457", "Teal": "#2F6F6B",
    "Peach": "#E8B49A", "Gold": "#C9A24B", "Rust": "#A65A32", "Turquoise": "#3AA6A0",
    "Lavender": "#A99AC9", "Magenta": "#B33A7A", "Charcoal": "#3A3F47",
    "Off White": "#F2F1EE", "Rose": "#C97A87", "Nude": "#D8BBA6", "Copper": "#A8643C",
    "Lime Green": "#8FAE3A", "Sea Green": "#4E8A72", "Burgundy": "#5C2333",
    "Mushroom Brown": "#8A7461", "Coffee Brown": "#5A3E2B", "Metallic": "#A8ADB4",
    "Multi": "#8A8F98", "Skin": "#E3BE9E",
}


def download(url: str, target: Path) -> Path:
    if target.exists() and target.stat().st_size > 1_000_000:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {target.name} ...")
    request = urllib.request.Request(url, headers={"User-Agent": "AclosetStudio/1.0"})
    with urllib.request.urlopen(request, timeout=300) as response, target.open("wb") as fh:
        while chunk := response.read(1 << 20):
            fh.write(chunk)
    return target


def load_metadata() -> list[dict]:
    rows, cursor = [], 0
    for n, url in enumerate(SHARDS):
        path = download(url, CACHE / f"shard{n}.parquet")
        f = pq.ParquetFile(path)
        cols = ["id", "gender", "masterCategory", "articleType", "baseColour",
                "season", "usage", "productDisplayName"]
        for g in range(f.num_row_groups):
            data = f.read_row_group(g, columns=cols).to_pydict()
            for i in range(len(data["id"])):
                position = cursor
                cursor += 1
                name = data["productDisplayName"][i] or ""
                low = name.lower()
                if data["masterCategory"][i] not in ("Apparel", "Footwear"):
                    continue
                if any(w in low for w in ("kids", "boys", "girls", "baby", "innerwear",
                                          "inner wear", "waistcoat", "football", "cricket",
                                          "pack of", "combo", "set of")):
                    continue
                rows.append({
                    "offset": position,
                    "source_id": data["id"][i],
                    "gender": data["gender"][i],
                    "articleType": data["articleType"][i],
                    "baseColour": data["baseColour"][i] or "Grey",
                    "season": data["season"][i] or "Summer",
                    "usage": data["usage"][i] or "Casual",
                    "productDisplayName": name,
                })
    return rows


def brand_of(display: str) -> str:
    return re.split(r"\b(Men|Women|Man|Woman)\b", display, maxsplit=1)[0].strip().lower()


def pick(rows: list[dict]) -> list[dict]:
    chosen: list[dict] = []
    used_names: set[str] = set()
    used_colour: Counter = Counter()
    for label, pred, count in BUCKETS:
        pool = [r for r in rows if pred(r) and r["productDisplayName"] not in used_names]
        prefs = [c.lower() for c in PREFERRED.get(label, [])]
        local_brand: Counter = Counter()
        local_colour: Counter = Counter()
        while len([c for c in chosen if pred(c)]) < count:
            available = [r for r in pool if r["productDisplayName"] not in used_names
                         and local_brand[brand_of(r["productDisplayName"])] < 1]
            if not available:
                break

            def score(r: dict) -> tuple:
                colour = r["baseColour"].lower()
                rank = prefs.index(colour) if colour in prefs else len(prefs) + 5
                brand = brand_of(r["productDisplayName"])
                return (rank + local_colour[colour] * 10 + local_brand[brand] * 14
                        + used_colour[colour] * 2, len(r["productDisplayName"]))

            row = min(available, key=score)
            brand = brand_of(row["productDisplayName"])
            chosen.append(row)
            used_names.add(row["productDisplayName"])
            local_brand[brand] += 1
            local_colour[row["baseColour"].lower()] += 1
            used_colour[row["baseColour"].lower()] += 1
    return chosen


def colour_family(name: str) -> str:
    n = name.lower()
    if "olive" in n or "khaki" in n:
        return "earth"
    if "maroon" in n or "burgundy" in n:
        return "warm"
    if "navy" in n:
        return "cool"
    for key in ("black", "white", "grey", "gray", "silver", "beige", "cream",
                "charcoal", "off white", "ivory", "taupe", "nude"):
        if key in n:
            return "neutral"
    for key in ("blue", "green", "teal", "turquoise", "purple", "lavender",
                "aqua", "lime", "sea green"):
        if key in n:
            return "cool"
    for key in ("brown", "tan", "rust", "camel", "coffee", "mushroom", "bronze"):
        if key in n:
            return "earth"
    for key in ("red", "yellow", "orange", "pink", "peach", "gold", "rose",
                "magenta", "copper"):
        if key in n:
            return "warm"
    return "neutral"


def pattern_of(name: str) -> str:
    n = name.lower()
    if "strip" in n:
        return "Striped"
    if "check" in n or "plaid" in n:
        return "Check"
    if "print" in n or "graphic" in n or "motif" in n:
        return "Print"
    if "textur" in n or "self design" in n or "woven" in n:
        return "Textured"
    return "Solid"


def subtype_of(article: str, display: str) -> str:
    n = display.lower()
    if article == "Shirts":
        return "shirt"
    if article == "Tshirts":
        return "polo" if "polo" in n else "tee"
    if article == "Tops":
        return "blouse"
    if article == "Sweaters":
        return "knit"
    if article == "Sweatshirts":
        return "hoodie" if "hood" in n else "knit"
    if article == "Jackets":
        return "jacket"
    if article == "Blazers":
        return "blazer"
    if article == "Jeans":
        return "jeans"
    if article == "Trousers":
        return "trousers"
    if article == "Shorts":
        return "shorts"
    if article == "Skirts":
        return "skirt"
    if article == "Formal Shoes":
        return "oxford" if "oxford" in n else "derby"
    if article in ("Casual Shoes", "Sports Shoes"):
        if "loafer" in n:
            return "loafer"
        if "boot" in n:
            return "boot"
        return "sneaker"
    return "tee"


def category_of(subtype: str) -> str:
    if subtype in ("shirt", "tee", "polo", "blouse", "knit", "hoodie"):
        return "top"
    if subtype in ("jeans", "trousers", "shorts", "skirt", "track pants"):
        return "bottom"
    if subtype in ("jacket", "blazer", "gilet"):
        return "outer"
    return "shoes"


def material_of(name: str, subtype: str) -> str:
    n = name.lower()
    if "leather" in n:
        return "Leather"
    if "suede" in n:
        return "Suede"
    if "denim" in n or subtype == "jeans":
        return "Denim"
    if "linen" in n:
        return "Linen 100%"
    if "corduroy" in n:
        return "Cotton Corduroy"
    if "wool" in n or "tweed" in n:
        return "Wool Blend"
    if "silk" in n:
        return "Silk"
    if "mesh" in n:
        return "Engineered Mesh"
    if "canvas" in n:
        return "Cotton Canvas"
    if subtype in ("knit", "sweater", "cardigan"):
        return "Wool Blend"
    if subtype == "polo":
        return "Cotton Pique"
    if subtype in ("tee", "hoodie"):
        return "Cotton Jersey"
    if subtype == "shirt":
        return "Cotton Poplin"
    if subtype in ("trousers", "shorts", "skirt", "track pants"):
        return "Cotton Twill"
    if subtype in ("jacket", "gilet"):
        return "Polyester Shell"
    if subtype == "blazer":
        return "Wool"
    if subtype == "sneaker":
        return "Leather"
    if subtype in ("oxford", "derby", "loafer"):
        return "Calf Leather"
    return "Cotton Blend"


BASE_COMFORT = {
    "shirt": (7, 3), "tee": (8, 2), "polo": (7, 3), "blouse": (7, 3), "knit": (5, 7),
    "hoodie": (4, 7), "jacket": (3, 8), "gilet": (4, 6), "blazer": (4, 7),
    "jeans": (5, 5), "trousers": (6, 4), "shorts": (8, 2), "skirt": (7, 3),
    "track pants": (6, 4), "sneaker": (8, 2), "boot": (4, 6), "loafer": (5, 4),
    "oxford": (4, 5), "derby": (4, 5), "sandal": (9, 1),
}


def comfort_of(subtype: str, material: str) -> tuple[int, int]:
    breath, warm = BASE_COMFORT.get(subtype, (6, 4))
    m = material.lower()
    if "linen" in m:
        breath += 1; warm -= 1
    if "wool" in m:
        breath -= 2; warm += 2
    if "leather" in m or "suede" in m:
        breath -= 1; warm += 1
    if "mesh" in m:
        breath += 1
    if "corduroy" in m:
        breath -= 1; warm += 1
    return max(1, min(10, breath)), max(1, min(10, warm))


def seasons_of(dataset_season: str, subtype: str) -> str:
    if subtype in ("jeans", "trousers", "sneaker", "oxford", "derby", "loafer"):
        return "Spring,Summer,Autumn,Winter"
    if subtype in ("shorts", "skirt"):
        return "Spring,Summer"
    if subtype in ("jacket", "gilet", "blazer", "knit", "hoodie"):
        return "Autumn,Winter"
    return {"Summer": "Spring,Summer", "Spring": "Spring,Summer",
            "Autumn": "Autumn,Winter", "Fall": "Autumn,Winter",
            "Winter": "Autumn,Winter"}.get(dataset_season, "Spring,Summer")


def occasions_of(usage: str, subtype: str) -> str:
    if subtype in ("oxford", "derby"):
        return "Formal,Smart Casual"
    if subtype in ("loafer", "blazer"):
        return "Smart Casual,Formal"
    if subtype == "sneaker":
        return "Sport,Casual,University"
    if subtype in ("shorts", "skirt"):
        return "Casual,University"
    if subtype in ("jacket", "gilet"):
        return "Casual,Smart Casual"
    if usage == "Formal":
        return "Formal,Smart Casual"
    if usage == "Sports":
        return "Sport,Casual"
    if usage == "Smart Casual":
        return "Smart Casual,University"
    return "Casual,University"


TYPE_LABEL = {
    "shirt": "Shirt", "tee": "T-Shirt", "polo": "Polo", "blouse": "Blouse",
    "knit": "Knit", "hoodie": "Hoodie", "jacket": "Jacket", "gilet": "Gilet",
    "blazer": "Blazer", "jeans": "Jeans", "trousers": "Trousers", "shorts": "Shorts",
    "skirt": "Skirt", "track pants": "Track Pants", "sneaker": "Sneakers",
    "boot": "Boots", "loafer": "Loafers", "oxford": "Oxford Shoes",
    "derby": "Derby Shoes", "sandal": "Sandals",
}


def build_record(row: dict, app_id: str) -> dict:
    subtype = subtype_of(row["articleType"], row["productDisplayName"])
    colour = row["baseColour"]
    pattern = pattern_of(row["productDisplayName"])
    material = material_of(row["productDisplayName"], subtype)
    breath, warm = comfort_of(subtype, material)
    label = TYPE_LABEL.get(subtype, subtype.title())
    name = " ".join([colour] + ([pattern] if pattern != "Solid" else []) + [label])
    record = {
        "id": app_id,
        "name": name,
        "category": category_of(subtype),
        "subtype": subtype,
        "color_name": colour,
        "color_hex": HEX.get(colour, "#8A8F98"),
        "color_family": colour_family(colour),
        "pattern": pattern,
        "material": material,
        "breathability": breath,
        "warmth": warm,
        "seasons": seasons_of(row["season"], subtype),
        "occasions": occasions_of(row["usage"], subtype),
        "image_path": "",
        "source": f"fashion-product-images id={row['source_id']}",
        "product_name": row["productDisplayName"],
        "gender": row["gender"],
        "source_usage": row["usage"],
        "source_season": row["season"],
    }
    record.update(OVERRIDES.get(row["source_id"], {}))
    return record


def fetch_image(row: dict, target: Path, app_id: str, manifest: dict) -> None:
    if (target.exists() and target.stat().st_size > 6000
            and manifest.get(app_id) == row["source_id"]):
        return
    request = urllib.request.Request(ROWS_API.format(offset=row["offset"]),
                                     headers={"User-Agent": "AclosetStudio/1.0"})
    payload = None
    for attempt in range(8):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except Exception as exc:  # noqa: BLE001
            print(f"  retry {attempt + 1}: {exc}")
            time.sleep(10 + attempt * 8)
    if payload is None:
        raise RuntimeError(f"could not fetch image for {row['source_id']}")
    data = payload["rows"][0]["row"]
    if int(data["id"]) != int(row["source_id"]):
        raise RuntimeError(f"row mismatch {data['id']} != {row['source_id']}")
    with urllib.request.urlopen(data["image"]["src"], timeout=90) as response:
        raw = response.read()
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    image.thumbnail((500, 500), Image.LANCZOS)
    canvas = Image.new("RGB", (512, 512), (250, 249, 246))
    canvas.paste(image, ((512 - image.width) // 2, (512 - image.height) // 2))
    canvas.save(target, "JPEG", quality=90, optimize=True)


FIELDS = ["id", "name", "category", "subtype", "color_name", "color_hex",
          "color_family", "pattern", "material", "breathability", "warmth",
          "seasons", "occasions", "image_path", "source", "product_name",
          "gender", "source_usage", "source_season"]


def main() -> None:
    rows = load_metadata()
    chosen = pick(rows)
    if len(chosen) != TOTAL:
        print(f"warning: picked {len(chosen)} rows, expected {TOTAL}", file=sys.stderr)

    manifest_path = GARMENTS / "scraped_30.sources.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}

    records = []
    for n, row in enumerate(chosen):
        app_id = f"IT-{START_ID + n:02d}"
        record = build_record(row, app_id)
        target = GARMENTS / f"{app_id}.jpg"
        print(f"{app_id} {record['category']:6} {record['name']}")
        fetch_image(row, target, app_id, manifest)
        manifest[app_id] = row["source_id"]
        records.append(record)

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    out = GARMENTS / "scraped_30.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)
    print(f"\nwrote {out} and {len(records)} images")


if __name__ == "__main__":
    main()
