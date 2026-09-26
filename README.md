# data-acquisition

Collector process. It pulls (or will pull) prices from providers and sends them to `api-engine` over gRPC ingest.

**Why this repo exists:** scraping and provider quirks must not sit in the API or the domain. This process can crash, retry, and change adapters without taking down HTTP. It speaks `platform-contracts`, not SQL.

The current adapter is a stub so the stack can start and prove the gRPC path.
