"""Build the single Fredericton baseline/provider seed bundle."""

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SEED_DATA = ROOT / "internal" / "seed" / "data"


def read_csv(name):
    with (SEED_DATA / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def slug(value):
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "unknown"


def raw_provider_stores(providers, provider_metadata):
    """Normalize raw provider listings without collapsing distinct branches."""
    records = []
    for provider_id, catalog in providers.items():
        for store in catalog.get("stores", []):
            store_name = store.get("name", "Unknown store")
            item_images = (provider_metadata.get(store.get("url", "")) or {}).get("itemImages", {})
            menu_items = []
            for item in store.get("menuItems", []):
                item_copy = dict(item)
                if item_copy.get("name") in item_images:
                    item_copy["imageUrl"] = item_images[item_copy["name"]]
                    item_copy["imageSourceUrl"] = store.get("url", "")
                menu_items.append(item_copy)
            records.append(
                {
                    "id": f"raw_{provider_id}_{slug(store_name)}_{len(records):04d}",
                    "name": store_name,
                    "address": store.get("address", ""),
                    "provider": provider_id,
                    "sourceUrl": store.get("url", ""),
                    "observedAt": store.get("observedAt") or store.get("retrievedAt") or catalog.get("retrievedAt", ""),
                    "coverage": store.get("coverage", ""),
                    "fulfillmentMode": store.get("fulfillmentMode", "unspecified"),
                    "rating": store.get("rating"),
                    "imageUrl": store.get("imageUrl", ""),
                    "menuItems": menu_items,
                }
            )
    return records


def main():
    providers = {
        "doordash": read_json(DATA / "doordash-fredericton.json"),
        "skip": read_json(DATA / "skip-fredericton.json"),
        "ubereats": read_json(DATA / "ubereats-fredericton.json"),
    }
    provider_metadata = read_json(DATA / "provider_metadata.json")
    enrichment = read_json(DATA / "enrichment.json")
    manual_direct = read_json(DATA / "manual_direct_menus.json")
    raw_stores = raw_provider_stores(providers, provider_metadata)
    baseline_items = read_csv("unbf_menu_items.csv")
    baseline_prices = read_csv("unbf_menu_prices.csv")
    for record in manual_direct.get("records", []):
        for item in record.get("items", []):
            baseline_items.append(
                {
                    "restaurant_id": record["restaurantId"],
                    "item_id": item["id"],
                    "name": item["name"],
                    "description": item.get("description", ""),
                    "section": item.get("section", ""),
                    "image_url": item.get("imageUrl", ""),
                    "image_source_url": record["sourceUrl"],
                    "image_status": "source_page_only" if not item.get("imageUrl") else "source_provided",
                    "source_url": record["sourceUrl"],
                    "observed_at": manual_direct["observedAt"],
                }
            )
            for mode in [record.get("fulfillmentMode", "pickup")]:
                baseline_prices.append(
                    {
                        "restaurant_id": record["restaurantId"],
                        "item_id": item["id"],
                        "channel": "merchant_web",
                        "fulfillment_mode": mode,
                        "price_cents": item.get("priceCents", ""),
                        "currency": "CAD",
                        "fees_cents": "0",
                        "observed_at": manual_direct["observedAt"],
                        "source_url": record["sourceUrl"],
                        "price_status": "observed_merchant_menu",
                    }
                )
    bundle = {
        "schemaVersion": "fredericton-seed-v1",
        "market": {"city": "Fredericton", "region": "NB", "country": "CA", "currency": "CAD"},
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "baseline": "Curated merchant directory and direct-menu observations.",
            "providers": "Committed provider catalogs from the acquisition collector.",
            "prices": "A price is only comparable when its provider/channel, fulfillment mode, and observation time are retained.",
        },
        "sourceFiles": [
            "internal/seed/data/unbf_businesses.csv",
            "internal/seed/data/unbf_menu_items.csv",
            "internal/seed/data/unbf_menu_prices.csv",
            "data/doordash-fredericton.json",
            "data/skip-fredericton.json",
            "data/ubereats-fredericton.json",
            "data/enrichment.json",
            "data/provider_metadata.json",
            "data/manual_direct_menus.json",
        ],
        "baseline": {
            "businesses": read_csv("unbf_businesses.csv"),
            "menuItems": baseline_items,
            "priceObservations": baseline_prices,
        },
        "rawCatalog": {
            "description": "Provider-backed public store/menu observations retained as raw seed material. These are not merchant-direct prices.",
            "stores": raw_stores,
            "directMenus": enrichment.get("directMenus", []),
            "manualDirectMenus": manual_direct.get("records", []),
            "priorityStores": {
                "Taco Boyz": [store for store in raw_stores if store["name"].casefold() == "taco boyz"],
                "McDonald's": [store for store in raw_stores if "mcdonald" in store["name"].casefold()],
            },
        },
        "providers": providers,
        "enrichment": enrichment,
        "providerMetadata": provider_metadata,
    }
    target = DATA / "fredericton-seed.json"
    target.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {target}: {len(bundle['baseline']['businesses'])} baseline businesses, "
        f"{len(bundle['baseline']['menuItems'])} baseline menu items, "
        f"{len(raw_stores)} raw provider stores"
    )


if __name__ == "__main__":
    main()
