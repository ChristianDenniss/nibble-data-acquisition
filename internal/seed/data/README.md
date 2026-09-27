# Curated UNBF seed data

`../../../data/fredericton-seed.json` is the canonical merged bundle. Rebuild it with:

```sh
python scripts/build_fredericton_seed.py
```

It combines the merchant baseline below with the committed DoorDash, Skip, Uber Eats, enrichment, and provider-metadata catalogs. Work from that bundle rather than maintaining a second provider or merchant seed.

`unbf_businesses.csv` contains the place-level directory used for the Fredericton/UNBF demo.

`unbf_menu_items.csv` contains canonical menu items. `image_url` stays empty until an image asset has been captured and cleared for demo use; `image_source_url` records where the item/image was found.

`unbf_menu_prices.csv` contains observations, not permanent restaurant prices. A price belongs to a channel and fulfillment mode. `fees_cents` is the explicitly observed fee at capture time; quote-level delivery, service, small-order, tax, and tip amounts should be added when a provider quote is captured.

Allowed channel values:

- `in_person`
- `drive_thru`
- `phone`
- `merchant_web`
- `merchant_app`
- `skip`
- `doordash`
- `ubereats`

Allowed fulfillment values include `dine_in`, `drive_thru`, `pickup`, `phone`, and `delivery`.
