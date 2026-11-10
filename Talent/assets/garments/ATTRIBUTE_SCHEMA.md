# Garment attribute schema for scraping

This file lists every attribute the Acloset Studio recommender reads, the values it accepts, and the rules for filling the attribute from a product page. The database table is `garments` and the template file next to this document is `garments_template.csv`.

## Required columns

These 13 columns match the `garments` table and the seed data. Keep the order and the header names exactly as in the template.

| Column | Type | Allowed values | Used by |
|---|---|---|---|
| `id` | text | `IT-01`, `IT-02`, ... unique | Primary key and photo filename |
| `name` | text | English product name, title case | Ranking labels, outfit names, analytics |
| `category` | enum | `top`, `bottom`, `outer`, `shoes` | Candidate generation (one item per slot) |
| `subtype` | text | see list below | Display and search |
| `color_name` | text | Normalised colour name, e.g. `Off White` | Wardrobe card, search |
| `color_hex` | text | `#RRGGBB` | Flat-lay illustration, swatch |
| `color_family` | enum | `neutral`, `cool`, `earth`, `warm` | Colour Harmony sub-score |
| `pattern` | text | `Solid`, `Striped`, `Textured`, `Check`, `Print` | Pattern conflict penalty |
| `material` | text | Fibre plus weave, e.g. `Cotton Poplin` | Display, manual breathability checks |
| `breathability` | integer | `1` to `10` | Weather Suitability sub-score |
| `warmth` | integer | `1` to `10` | Weather Suitability sub-score below 18°C |
| `seasons` | text | comma list from `Spring,Summer,Autumn,Winter` | Wardrobe filters |
| `occasions` | text | comma list from `University,Smart Casual,Casual,Formal,Sport` | Occasion sub-score, filters |

`image_path` is a fourteenth database column, but leave it empty when you follow the photo naming rule below. The media layer looks for `assets/garments/<id>.jpg` first, then `.jpeg`, `.png` and `.webp`.

## Category and subtype

The recommender builds outfits from four slots, so `category` is the one field that must be correct. A missing top, bottom or shoes pool produces an empty recommendation list.

| `category` | Suggested `subtype` values |
|---|---|
| `top` | `shirt`, `tee`, `polo`, `blouse`, `knit`, `hoodie`, `sweater`, `overshirt` |
| `bottom` | `jeans`, `trousers`, `chinos`, `shorts`, `skirt` |
| `outer` | `jacket`, `coat`, `blazer`, `trench`, `parka`, `cardigan` |
| `shoes` | `sneaker`, `boot`, `loafer`, `oxford`, `sandal`, `derby` |

Dresses and jumpsuits have no slot in the current model. Either skip them during scraping or split a dress listing into a top record and a bottom record only when the product is genuinely sold as two pieces. A one-piece dress stored as `top` will be combined with trousers, which is wrong.

## Colour family mapping

The colour score uses colour families, not individual hex values. Two accent families that do not share a tonal direction receive a clash penalty, so this column changes the ranking more than the hex value does.

| Family | Typical colours |
|---|---|
| `neutral` | black, white, off white, cream, ivory, grey, charcoal, navy, beige, taupe, stone |
| `earth` | olive, khaki, sand, camel, tan, brown, rust, terracotta, ochre |
| `cool` | blue, teal, green, mint, sage, lavender, purple, silver |
| `warm` | red, burgundy, orange, yellow, mustard, pink, coral, gold |

Rules:

- Choose one family per garment. When two apply, prefer the family that dominates the surface area.
- Denim goes to `cool` unless it is a washed grey or ecru, which go to `neutral`.
- Brown leather shoes are `earth`; black leather shoes are `neutral`.
- A print with two strong colours still needs one family. Pick the background.

## Breathability and warmth

Both values run from 1 to 10 and should describe the fabric and the construction, not the season tag. The weather score compares average breathability against the current temperature and adds warmth only below 18°C, so inconsistent values produce odd rankings.

| Garment type | Breathability | Warmth |
|---|---|---|
| Linen shirt, linen shorts | 9 | 2 |
| Cotton poplin or voile shirt | 8 | 3 |
| Cotton jersey tee | 7 | 3 |
| Polo, pique cotton | 7 | 3 |
| Silk blouse | 7 | 3 |
| Cotton twill or gabardine trousers | 6 | 4 |
| Denim jeans | 5 | 5 |
| Merino knit, mid weight | 5 | 7 |
| Cotton fleece hoodie | 4 | 7 |
| Wool coat or trench | 3 | 9 |
| Padded or lined jacket | 2 | 9 |
| Leather jacket | 3 | 7 |
| Mesh runner | 9 | 1 |
| Leather boot or loafer | 4 | 5 |

Adjust by one point for obvious deviations: a lined shirt is less breathable, a chunky knit is warmer, an unlined linen blazer is airier. Keep values as integers.

## Season and occasion tags

`seasons` and `occasions` are comma-separated. In the CSV, wrap these two fields in double quotes so the comma stays inside the cell: `"Spring,Summer"` and `"University,Smart Casual"`. The display splits on commas, so `Spring,Summer` is correct and `Spring, Summer` also works but is harder to review in a CSV.

Season rules:

- Short sleeves and lightweight fabrics: `Spring,Summer`.
- Knits, wool and corduroy: `Autumn,Winter`.
- Jeans, chinos, sneakers and classic shirts: all four seasons.
- Outerwear: at least `Autumn,Winter`; a trench may include `Spring`.

Occasion rules:

- Office, interview, ceremony, church: `Formal` and/or `Smart Casual`.
- Campus, lecture, study: `University`.
- Everyday, weekend, errand: `Casual`.
- Gym, running, training: `Sport`.
- A garment can carry several tags. A white oxford shirt is `University,Smart Casual,Formal`.

The score uses the share of pieces that carry the selected occasion tag, so tagging too broadly removes the difference between garments. Tag what the product is plausibly worn for, not every occasion it could be forced into.

## Name and photo conventions

`name` should be the product name without marketing words. Remove "Men's", "Premium", "New Season", "Essential" and similar prefixes. Keep the colour and the garment type because the wardrobe grid shows the name as its main label.

Photos go in `assets/garments/` with the record id as the filename:

```
assets/garments/IT-29.jpg
assets/garments/IT-30.png
```

Recommended image spec: square crop, 800 × 800 px, garment centred on a plain light background, JPEG at quality 85. The crop and background matter more than the resolution because the card and the collage both display the image inside a rounded container.

## Optional columns for the scraper

Keep these in a separate working file, not in `garments_template.csv`, because the database insert reads the fixed column list:

| Column | Why keep it |
|---|---|
| `product_url` | Trace the record back to the source page |
| `brand` | Duplicate detection and provenance |
| `price` | Wardrobe value analytics later |
| `source` | Site name, for licence checks |
| `image_url` | Re-download the photo if the local copy is lost |
| `scraped_at` | Date of capture |
| `notes` | Fit, sizing, care, or a reason for a manual attribute override |

## Importing the result

There is no bulk importer in the application today. The current paths are the Add Clothing dialog, direct SQLite inserts into `assets/data/wardrobe.db`, or a small script that maps each row to `Garment` and calls `Repository.upsert_garment`. A CSV importer can be added if the scraped set is large, and the template above is already shaped for that.
