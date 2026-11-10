# Garment data scripts

Two scripts bring real product photos into Acloset Studio instead of the drawn
placeholders. Neither script runs at app startup, and neither touches the
database unless you pass `--write`.

## Where the data comes from

- Metadata and product ids: `ashraq/fashion-product-images-small` on Hugging Face,
  built from the Myntra catalogue. About 44k rows across two parquet shards,
  roughly 270 MB.
- Photos: `benitomartin/fashion-product-images-small-384x512`, the same rows at
  384x512. The original "small" dataset only stores 60x80 thumbnails, which look
  blurry in the wardrobe grid.

Both datasets derive from the Kaggle *Fashion Product Images (Small)* release.
They are used here for coursework demonstration only. Check the dataset card on
Hugging Face before any redistribution. Product photos belong to their original
retailers and brands.

## 1. Build the set

```
assets\garments\.venv\Scripts\python.exe assets\garments\scripts\fetch_garments.py
```

Needs `pyarrow` and `pillow`. The first run downloads the parquet shards into
`scripts/.cache/`; later runs reuse them and only fill in missing images.

Output, all under `assets/garments/`:

| File | Contents |
| --- | --- |
| `scraped_30.csv` | 30 records in the 19-column import format |
| `IT-30.jpg` … `IT-59.jpg` | 512x512 canvases, photo centred on a beige field |
| `scraped_30.sources.json` | app id → source dataset id, so reruns keep the same mapping |

The selection is fixed by quota in `BUCKETS` (11 tops, 8 bottoms, 5 outer,
6 shoes) and by `PREFERRED`, which avoids five white shirts in a row. Brand
names are de-duplicated per bucket. `OVERRIDES` corrects rows whose product
title does not match the photo; it is keyed by source dataset id, so it survives
a change in selection.

Why the square canvas: `ui/media.py` centre-crops every photo to a square. A
375x500 portrait pasted whole into a 512x512 canvas keeps the whole garment
visible after that crop.

## 2. Import into the database

Dry run first. It validates categories, colour families, hex values, the 1..10
ranges, seasons and occasions, then prints what the set contains:

```
.\.venv\Scripts\python.exe assets\garments\scripts\import_garments.py
```

Apply it. This adds the 30 items next to the built-in seed, so the wardrobe ends
up with 59 garments:

```
.\.venv\Scripts\python.exe assets\garments\scripts\import_garments.py --write
```

Replace the wardrobe entirely with the scraped set. This also clears saved
outfits and the wear log, so analytics start from empty:

```
.\.venv\Scripts\python.exe assets\garments\scripts\import_garments.py --write --reset --yes
```

Use `--db <path>` to target a copy of the database. Note that the numbers quoted
in Chapter 4 come from the 28-item seed and a clean wear log; resetting changes
them.

## CSV columns

`id`, `name`, `category`, `subtype`, `color_name`, `color_hex`, `color_family`,
`pattern`, `material`, `breathability`, `warmth`, `seasons`, `occasions`,
`image_path`, plus five provenance columns the importer ignores (`source`,
`product_name`, `gender`, `source_usage`, `source_season`).

`seasons` and `occasions` are comma-separated inside one quoted field. Leave
`image_path` empty: the UI falls back to `assets/garments/<id>.jpg` on its own.
See `../ATTRIBUTE_SCHEMA.md` for how each attribute is meant to be filled.

## Files

- `fetch_garments.py` — selection, attribute derivation, image fetch.
- `import_garments.py` — validation and CSV → SQLite import.
- `download_datasets.py` — empty placeholder from an earlier attempt; harmless,
  safe to delete.
