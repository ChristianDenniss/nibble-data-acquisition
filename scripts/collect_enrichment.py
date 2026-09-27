"""Collect public merchant pages and reviewed promotion sources, with a 12-hour cache.
Run before export_storefront_catalog.py. HTTP blocks are reported, not bypassed.
Promotion text changes require a human review before refreshing eligibility metadata.
"""
import argparse
from datetime import datetime, timezone
from http.client import HTTPException
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from enrichment import text, wix_menu

ROOT = Path(__file__).resolve().parents[1]


def fetch(url, cache, cache_hours):
    key = hashlib.sha256(url.encode()).hexdigest()
    path = cache / (key + '.html')
    failure = cache / (key + '.failure.json')
    if failure.exists() and time.time() - failure.stat().st_mtime < cache_hours * 3600:
        return None, json.loads(failure.read_text())['status']
    def fail(status):
        failure.write_text(json.dumps({'status': status}))
        return None, status
    if path.exists() and time.time() - path.stat().st_mtime < cache_hours * 3600:
        body = path.read_text()
        if 'Bot Verification' in body or 'Verifying that you are not a robot' in body:
            return fail('challenge')
        return body, 'cached'
    # Retry transient failures only, with a bounded backoff. Never retry a 403/429.
    for attempt in range(2):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'NibbleCatalog/1.0 (public menu collection)'}), timeout=20) as response:
                body = response.read(8_000_001)
                if len(body) > 8_000_000:
                    return fail('too_large')
                body = body.decode('utf-8', errors='replace')
            if any(marker in body.lower() for marker in ['verify you are human', 'just a moment...', 'cf-chl-', 'bot verification', 'verifying that you are not a robot']):
                return fail('challenge')
            path.write_text(body)
            failure.unlink(missing_ok=True)
            return body, 'fetched'
        except HTTPError as error:
            if error.code < 500 or attempt:
                return fail(f'http_{error.code}')
        except (URLError, OSError, HTTPException):
            if attempt:
                return fail('network_error')
        time.sleep(2)
    return fail('network_error')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, help='Validated catalog for retained provider rating extraction')
    parser.add_argument('--cache-hours', type=float, default=12)
    parser.add_argument('--output', type=Path, default=ROOT/'data/enrichment.json')
    args = parser.parse_args()
    sources = json.loads((ROOT/'config/enrichment_sources.json').read_text())
    previous = json.loads(args.output.read_text()) if args.output.exists() else {}
    cache = ROOT/'snapshots/enrichment'
    cache.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    result = {'collectedAt': now, 'merchants': sources['merchants'], 'promotions': [], 'directMenus': [], 'sources': {}}
    urls = sorted({entry['sourceUrl'] for kind in sources.values() for entry in kind})
    pages = {}
    for url in urls:
        body, status = fetch(url, cache, args.cache_hours)
        pages[url] = body
        result['sources'][url] = {'status': status}
        if body:
            # Strip scripts/styles before detecting changes to public terms.
            import re
            visible = text(re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', body, flags=re.S | re.I))
            result['sources'][url]['textHash'] = hashlib.sha256(visible.encode()).hexdigest()
            from html import unescape
            from urllib.parse import urljoin, urlparse
            links = {urljoin(url, unescape(link)) for link in re.findall(r'href=[\"\']([^\"\']+)', body)}
            result['sources'][url]['discoveredLinks'] = sorted(link for link in links if urlparse(link).scheme == 'https' and any(word in link.lower() for word in ['order', 'menu', 'offer', 'promo', 'apps.apple', 'play.google']))[:50]
            # Discovery candidates are internal review inputs, not published discounts.
            result['sources'][url]['promotionCandidates'] = list(dict.fromkeys(re.findall(r'.{0,70}(?:% off|\$\d+ off|promo code|buy one|get one free).{0,160}', visible, re.I)))[:20]
        print(status, url, flush=True)
        if status != 'cached':
            time.sleep(1)
    for promo in sources['promotions']:
        entry = dict(promo)
        url = entry['sourceUrl']
        old = next((p for p in previous.get('promotions', []) if p['id'] == entry['id']), None)
        if old and entry['reviewedAt'] > old.get('reviewedAt', ''):
            old = None  # Explicitly re-reviewed terms reset a change quarantine.
        old_hash = previous.get('sources', {}).get(url, {}).get('textHash')
        new_hash = result['sources'][url].get('textHash') if pages[url] else None
        if old and old_hash and new_hash == old_hash and not old.get('needsReview'):
            entry['verifiedAt'] = now
        else:
            entry['verifiedAt'] = old.get('verifiedAt', entry['reviewedAt']) if old else entry['reviewedAt']
        entry['needsReview'] = bool(old and (old.get('needsReview') or (new_hash and old_hash and new_hash != old_hash)))
        # Preserve the last successful fingerprint through outages.
        if not new_hash and old_hash:
            result['sources'][url]['textHash'] = old_hash
        result['promotions'].append(entry)
    for source in sources['directMenus']:
        body = pages[source['sourceUrl']]
        old = next((m for m in previous.get('directMenus', []) if m['id'] == source['id']), None)
        if body and source['requiredAddress'] in text(body):
            dishes = wix_menu(body)
            if dishes:
                result['directMenus'].append({**source, 'items': dishes, 'collectedAt': now})
                continue
        if old:
            result['directMenus'].append(old)
    result['ratings'] = previous.get('ratings', {})
    if args.catalog:
        from enrichment import rating_for
        import re
        catalog = json.loads(args.catalog.read_text())
        for restaurant in catalog['restaurants']:
            for source in restaurant['sources']:
                if source['provider'] != 'DoorDash': continue
                match = re.search(r'-(\d+)/?$', source['url'])
                if not match: continue
                pages = sorted((ROOT/'snapshots/validated/raw/DoorDash').glob(f'ss_doordash_{match[1]}-*.html'))
                for path in reversed(pages):
                    rating = rating_for(path.read_text(), source['url'])
                    if rating:
                        result['ratings'][restaurant['id']] = rating
                        break
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, indent=2)+'\n')
    temporary.replace(args.output)
    print('Direct menu items:', sum(len(m['items']) for m in result['directMenus']))


if __name__ == '__main__':
    main()
