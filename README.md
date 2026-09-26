# nibble-data-acquisition

Collector process. It pulls (or will pull) prices from providers and sends them to `nibble-api-engine` over gRPC ingest.

**Why this repo exists:** provider quirks must not sit in the API or the domain. This process can crash, retry, and change adapters without taking down HTTP. It speaks `nibble-platform-contracts`, not SQL.

## Adapters (`ACQUISITION_ADAPTER`)

| Value | What it does |
|-------|----------------|
| `curated` | Global channels, memberships, markets, expected coverage, and the compare demo catalog (default in compose). |
| `demo` | Compare fixture only. |
| `stub` | No-op. |

Fredericton coverage is curated (`expected` from city knowledge). Live store lists and quotes wait on a source Nibble is allowed to call (official partner/merchant APIs), not another consumer food app.

Job type written today: `curated_seed`.
