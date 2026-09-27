# Public restaurant promotions

Run `python3 scripts/export_public_promotions.py` after refreshing validated provider snapshots to update the storefront offer feed and `data/public_promotions.json`. The storefront catalog exporter also rebuilds the feed. A deployed static frontend still needs rebuilding to receive new data.

Only restaurant-funded structured fields are imported, linked by exact branch URL. Generic coupons, loyalty bonuses, subscription benefits, new-user and payment-card offers are excluded. Original observation timestamps are preserved; the frontend hides offers after 72 hours and respects known expiry dates. Collection time is not invented when re-exporting.

Fixed basket discounts with explicit amounts and minimums are automatically evaluated for that branch in whole-cart estimates. Only the single greatest saving applies; discounts do not stack. BOGO and free-item listings are displayed with source links but are not deducted until exact option eligibility and redemption rules can be verified.

Web search leads are recorded separately in `data/promotion_discovery.json`. Search snippets and expired campaigns do not enter the public offer feed. Current extraction covers Skip partner offers and DoorDash item BOGO badges. DoorDash records must identify the same store in their decoded item cursor; DashPass badges and reviews are excluded. Only the newest retained page per branch is read. Uber Eats leads remain in the discovery file until fresh branch evidence is available.
