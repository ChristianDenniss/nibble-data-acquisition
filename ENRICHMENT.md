# Public menu enrichment

Collection and export belong to this repository. The web repository receives a generated read model and downloaded images, never scraper code or raw pages.

```sh
python3 scripts/collect_enrichment.py --catalog /path/to/catalog.json
python3 scripts/refresh_storefront_images.py --catalog /path/to/catalog.json
python3 scripts/export_storefront_catalog.py --catalog /path/to/catalog.json
python3 -m unittest discover -s tests
```

The catalog input is the validated `/v1/catalog` API response. The enrichment collector has a 12-hour page cache, 20-second request timeouts, an 8 MB page limit, and one retry for transient errors. Failed sources are also cached for 12 hours to avoid repeated requests to blocked hosts. It reports HTTP blocks and bot challenges without bypassing them. A second pass reuses successful cached pages. Raw pages stay in ignored `snapshots/`; normalized records and source reports are in `data/enrichment.json`. The image refresh uses macOS `sips` to verify dimensions, keeps existing photos on failures or smaller replacements, and uses up to four downloads concurrently.

Run collection and export twice daily from the existing acquisition scheduler, with a persisted cache and a catalog input from that run. No new scheduler is installed by these scripts. Publishing the generated bundle is a separate web build/deployment step; updating acquisition files alone does not update a deployed website.

## Reviewed sources and boundaries

`config/enrichment_sources.json` contains official merchant ordering links, one verified Wix menu source, and reviewed public promotion terms. Promotion discovery candidates and outgoing menu/order/app links are retained for review, not automatically treated as coupons. Terms came from the linked official pages; when a source blocks the collector, the last reviewed terms remain available only within the freshness window.

Ratings preserve the value and count from one DoorDash Restaurant JSON-LD aggregate. They do not combine the JSON-LD sample count with a larger store-header count, nor mix Uber scores with DoorDash counts. Unavailable aggregates remain absent. The source URL and count scope accompany each rating.

Luna's website lists 379 King Street while the provider catalog lists a different address. Its 61 menu entries are a separate branch, with 60 positive base prices marked pickup and starting-price. The zero-price options entry is not a free item. Prices are not transferred to the other Luna branch or compared as delivered quotes. Merchant app links for other brands require location selection; they are not verified branch-specific quotes.

All retained catalog restaurants with menu entries are exported, including partial menus. A missing item price remains missing. Source-specific option groups, checkout fees, personalized promotions, and authenticated app menus are not available through this collector. The current bundle is not a claim of complete provider coverage.

## Promotion review

Promotions are conditional suggestions, never deductions from cart totals. The storefront hides expired offers, records requiring review, and records without verification within 72 hours. Date-only expiries use Atlantic Canada time. Unknown-expiry offers require provider confirmation. When public page text changes, existing promotions enter `needsReview`; after checking the official terms, update the definition and `reviewedAt` to clear that quarantine on the next run. New offer definitions require review; discovered snippets never enter the storefront automatically.

Source hashes deliberately include public page text, so navigation/content changes can also trigger review. This is conservative. A failed request preserves the last successful fingerprint and menu, without claiming a successful refresh. This is public-page enrichment, not an integration with checkout or a guarantee of account eligibility.

## Images

The image refresh requests larger source renditions (typically 1,200–1,600 pixels), not artificial pixel upscaling. Fifteen distinct Luna dish photos come from its own ordering page; other menu photography is illustrative and may be reused. Some original sources are smaller and cannot gain genuine detail. Image source URLs and verified dimensions are recorded in the web image manifests.
