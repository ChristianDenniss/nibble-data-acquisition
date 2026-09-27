"""Use the downloaded source artwork manifest for catalog restaurants."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
catalog_path = ROOT / "nibble-web-platform" / "src" / "catalog" / "catalog.json"
manifest_path = ROOT / "nibble-web-platform" / "src" / "catalog" / "restaurantImages.json"

catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
placeholder_files = {
    "/images/menu/burger.jpg",
    "/images/menu/chicken.jpg",
    "/images/menu/pizza.jpg",
    "/images/menu/wrap.jpg",
    "/images/menu/taco-cutout.jpg",
    "/images/menu/salad.jpg",
}
changed = 0
for restaurant in catalog["restaurants"]:
    if restaurant.get("imageURL") not in placeholder_files:
        continue
    artwork = manifest.get(restaurant["id"])
    if artwork and artwork.get("file"):
        restaurant["imageURL"] = artwork["file"]
        changed += 1

catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"updated {changed} restaurant images from the source artwork manifest")
