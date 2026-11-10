
from datasets import load_dataset
from pathlib import Path
import pandas as pd
from tqdm import tqdm

# 1. Tạo thư mục
BASE_DIR = Path("dataset/raw")
IMAGE_DIR = BASE_DIR / "images"

IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# 2. Tải dataset
print("Loading Fashion Product Images...")

dataset = load_dataset(
    "ashraq/fashion-product-images-small",
    split="train"
)

print("Total records:", len(dataset))

# 3. Chỉ lấy Apparel
clothes = dataset.filter(
    lambda x: x["masterCategory"] == "Apparel"
)

print("Clothing records:", len(clothes))

# 4. Lưu metadata và hình ảnh
metadata = []

for item in tqdm(clothes, desc="Saving images"):

    product_id = item["id"]
    image = item["image"]

    if image is None:
        continue

    image_path = IMAGE_DIR / f"{product_id}.jpg"

    try:
        image.convert("RGB").save(
            image_path,
            format="JPEG",
            quality=95
        )

        metadata.append({
            "id": product_id,
            "name": item["productDisplayName"],
            "category": item["subCategory"],
            "subtype": item["articleType"],
            "color_name": item["baseColour"],
            "season": item["season"],
            "usage": item["usage"],
            "gender": item["gender"],
            "year": item["year"],
            "image_path": str(image_path)
        })

    except Exception as e:
        print(f"Error {product_id}: {e}")

# 5. Xuất CSV
df = pd.DataFrame(metadata)

df.to_csv(
    BASE_DIR / "metadata.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\nDownload completed!")
print("Total saved:", len(df))
print(df.head())
