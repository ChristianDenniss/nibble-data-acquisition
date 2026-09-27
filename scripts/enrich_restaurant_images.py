"""Fill missing restaurant images from the provider store pages already in the seed.

Only provider-hosted image URLs found in a restaurant's own public store page are
written back. No generated or category placeholder images are used.
"""

import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

from doordash_page import records, store_header


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PROVIDER_FILES = (
    "doordash-fredericton.json",
    "skip-fredericton.json",
    "ubereats-fredericton.json",
)


def image_from_page(url: str) -> str:
    """Read a provider page and return its restaurant-specific cover image."""
    if "doordash.com/store/" in url:
        match = re.search(r"-(\d+)/?$", url)
        if not match:
            return ""
        try:
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as response:
                header = store_header(response.read(), match.group(1))
            if not header:
                return ""
            return (
                header.get("coverImgUrl")
                or header.get("coverSquareImgUrl")
                or header.get("businessHeaderImgUrl")
                or ""
            )
        except Exception:
            return ""

    # Skip and Uber page payloads are provider-specific; retain the existing
    # source record unless their page exposes a direct image in JSON-LD.
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as response:
            body = response.read()
        for root in records(json.loads(body.decode("utf-8"))):
            image = root.get("image")
            if isinstance(image, str) and image.startswith("https://"):
                return image
            if isinstance(image, list) and image and isinstance(image[0], str):
                return image[0]
    except Exception:
        pass
    return ""


def stored_doordash_images() -> dict[str, str]:
    """Extract images from raw pages captured by the acquisition collector."""
    images = {}
    for path in (ROOT / "snapshots" / "validated" / "raw" / "DoorDash").glob("*.html"):
        match = re.search(r"_(\d+)-", path.name)
        if not match:
            continue
        try:
            header = store_header(path.read_bytes(), match.group(1))
        except OSError:
            continue
        if header:
            image = header.get("coverImgUrl") or header.get("coverSquareImgUrl") or header.get("businessHeaderImgUrl")
            if image:
                images[match.group(1)] = image
    return images


def main() -> None:
    changed = 0
    stored_images = stored_doordash_images()
    for filename in PROVIDER_FILES:
        path = DATA / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        for store in payload.get("stores", []):
            if store.get("imageUrl") or not store.get("url"):
                continue
            image = ""
            if filename == "doordash-fredericton.json":
                match = re.search(r"-(\d+)/?$", store["url"])
                image = stored_images.get(match.group(1), "") if match else ""
            # Fresh provider pages may rate-limit automated requests. For
            # DoorDash, use only the raw snapshot already captured by this
            # acquisition run; other providers can still expose JSON-LD.
            # Only use committed snapshots. A missing snapshot is left for the
            # next acquisition run rather than filled with an unrelated image.
            if image:
                store["imageUrl"] = image
                store["imageSourceUrl"] = store["url"]
                changed += 1
                print(f"{filename}: {store.get('name', '')}: found", flush=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"updated {changed} restaurant image records")


if __name__ == "__main__":
    main()
