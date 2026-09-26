# Skip browser collector

The browser collector runs as a backend worker beside the product. It uses the locally saved, approved Skip browser session, reads the fixed target list, and sends only unambiguous item prices to the existing gRPC ingest service. The product user does not open or control the collection browser.

## One-time browser setup

From PowerShell, open a browser session and sign in normally. Set the delivery address used for this prototype, then press Enter in the terminal to save the local profile:

```powershell
cd C:\Users\Kyled\Downloads\nibble\nibble-data-acquisition\tools\skip-browser
& 'C:\Users\Kyled\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' .\src\create-session.mjs
```

The profile is stored in `.profile/`, which is git-ignored. Never copy it into the repository or share it. The worker uses this profile headlessly, so it can run without displaying a browser window.

## Start backend collection

Start the local development services first. Then, in a separate PowerShell window, run the Go collector from `nibble-data-acquisition`:

```powershell
cd C:\Users\Kyled\Downloads\nibble\nibble-data-acquisition
$env:ACQUISITION_ADAPTER = 'skip'
$env:API_ENGINE_GRPC_ADDR = 'localhost:9091'
$env:NODE_BIN = 'C:\Users\Kyled\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
$env:SKIP_BROWSER_DIR = 'C:\Users\Kyled\Downloads\nibble\nibble-data-acquisition\tools\skip-browser'
go run .\cmd\data-acquisition
```

It collects once at startup and refreshes every 15 minutes. Set `SKIP_COLLECTION_INTERVAL` to another positive Go duration such as `30m` to change the refresh interval. Keep this process running. The `demo` adapter remains the default, and Docker Compose continues to use it because the saved browser profile belongs on the host.

Collected observations are recorded through ingest v2 with source item, restaurant, fulfillment, currency, and observation time. A source snapshot also retains the Skip page URL and captured menu item metadata. The API comparison path can then read the latest stored observation. Items that are missing or ambiguous are skipped rather than assigned a guessed price. Generic “Wings” targets are likely to be ambiguous because menus often list multiple sizes; choose a specific size in the CSV if the sample distinguishes one.

The restaurant URLs and visible menu layout can change. Confirm the output statuses and prices before presenting prototype results. The current worker does not place orders or collect checkout fees, so its price is the menu item price, not a final delivery total.
