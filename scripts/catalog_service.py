"""Provider acquisition: collect, retain history, and publish over private gRPC.

No authentication, challenge solving, user cookies, or checkout endpoints.
"""
import argparse
import copy
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import subprocess
from urllib.error import HTTPError
from provider_directory import parse_directory
from doordash_page import store_header
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler

MAX_BYTES = 12 * 1024 * 1024
HOSTS = {'Uber Eats': 'www.ubereats.com', 'DoorDash': 'www.doordash.com', 'SkipTheDishes': 'www.skipthedishes.com'}
FILES = {'Uber Eats': 'ubereats-fredericton.json', 'DoorDash': 'doordash-fredericton.json', 'SkipTheDishes': 'skip-fredericton.json'}


def now():
    return datetime.now(timezone.utc).isoformat()


def store_id(provider, url):
    p = urlparse(url)
    if p.scheme != 'https' or p.netloc != HOSTS.get(provider):
        raise ValueError('Unexpected provider URL')
    if provider == 'SkipTheDishes':
        match = re.fullmatch(r'/(?:en/)?([a-z0-9]+(?:-[a-z0-9]+)*)/?', p.path)
        if not match or match[1] in ('cities', 'restaurants', 'terms-of-service', 'privacy-policy'):
            raise ValueError('Invalid Skip restaurant URL')
        return 'ss_skip_' + hashlib.sha256(match[1].encode()).hexdigest()[:24]
    if provider == 'Uber Eats':
        match = re.fullmatch(r'/ca/store/[^/]+/([^/]+)/?', p.path)
        if not match:
            raise ValueError('Invalid Uber Eats store URL')
        return 'ss_ubereats_' + hashlib.sha256(match[1].encode()).hexdigest()[:24]
    match = re.fullmatch(r'/(?:en(?:-CA)?/)?store/(?:[^/]*-)?(\d+)/?', p.path)
    if not match:
        raise ValueError('Invalid DoorDash store URL')
    return 'ss_doordash_' + match[1]


def clean_text(value):
    # Provider HTML occasionally contains NULs, which PostgreSQL text cannot store.
    if isinstance(value, str):
        return value.replace('\x00', '')
    if isinstance(value, dict):
        return {k: clean_text(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_text(v) for v in value]
    return value


def validate(snapshot, provider):
    cleaned = clean_text(snapshot)
    snapshot.clear()
    snapshot.update(cleaned)
    if snapshot.get('city') != 'Fredericton' or snapshot.get('region') != 'NB':
        raise ValueError('Snapshot must be for Fredericton, NB')
    datetime.fromisoformat(snapshot['retrievedAt'].replace('Z', '+00:00'))
    if not snapshot.get('stores'):
        raise ValueError('Empty snapshot')
    seen = set()
    for store in snapshot['stores']:
        sid = store_id(provider, store['url'])
        if sid in seen or not store.get('name'):
            raise ValueError('Duplicate or unnamed store')
        seen.add(sid)
        store['id'] = sid
        if not store.get('observedAt') and not store.get('sourceCrawlAgeAtRetrieval') and not store.get('directoryObservedAt'):
            raise ValueError('Missing source age')
        names = set()
        for item in store.get('menuItems', []):
            name = item.get('name', '').strip()
            if not name or name in names or item.get('currency') != 'CAD':
                raise ValueError('Invalid or duplicate menu item')
            names.add(name)
            cents = item.get('amountCents')
            if cents is not None and (type(cents) is not int or cents < 0):
                raise ValueError('Invalid price')
            if cents is None and not item.get('priceNote'):
                raise ValueError('Missing price explanation')
            if item.get('priceKind', 'base') not in ('base', 'from', 'options'):
                raise ValueError('Invalid price kind')
    return snapshot


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts, self.links = [], []
        self.current = None
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.current = []
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)
    def handle_endtag(self, tag):
        if tag == 'script' and self.current is not None:
            try:
                self.scripts.append(json.loads(''.join(self.current)))
            except json.JSONDecodeError:
                pass
            self.current = None


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def parse_menu(body, previous, provider):
    """Read explicit JSON-LD menu offers; never pair unrelated text and prices.

    Current accessible saved pages can be imported. Provider HTML adapters must
    fail if the site exposes no supported structured menu, rather than fabricate
    a successful refresh from a title or a delivery promotion.
    """
    if len(body) > MAX_BYTES:
        raise ValueError('Page exceeds size limit')
    if provider == 'SkipTheDishes':
        from skip_page import menu, page_props
        if page_props(body).get('menuV2'):
            result = menu(body, previous)
            result['id'] = store_id(provider, result['url'])
            result['observedAt'] = now()
            result['retrievedAt'] = result['observedAt']
            result.pop('sourceCrawlAgeAtRetrieval', None)
            result.pop('promotions', None)
            result['coverage'] = 'partial: public Skip menu; configured options excluded'
            return result
    doc = Document()
    doc.feed(body.decode('utf-8'))
    header = store_header(body, store_id(provider, previous['url']).removeprefix('ss_doordash_')) if provider == 'DoorDash' else None
    menu_roots = doc.scripts
    if provider == 'DoorDash' and header:
        menu_roots = [r for r in doc.scripts if isinstance(r, dict) and r.get('@type') == 'Restaurant' and r.get('name') == header.get('name')]
        if not menu_roots:
            standalone = [r for r in doc.scripts if isinstance(r, dict) and r.get('@type') == 'Menu']
            if len(standalone) == 1:
                menu_roots = standalone
    if provider == 'SkipTheDishes':
        menu_roots = [r for root in doc.scripts for r in objects(root)
                      if r.get('@type') == 'Restaurant'
                      and r.get('name', '').casefold() == previous['name'].casefold()
                      and isinstance(r.get('address'), dict)
                      and r['address'].get('addressLocality', '').casefold() == 'fredericton'
                      and r['address'].get('streetAddress', '').casefold() == previous['address'].split(',')[0].casefold()]
        if not menu_roots:
            raise ValueError('Skip menu branch identity unavailable')
    sections = {}
    for root in menu_roots:
        for section in objects(root):
            if isinstance(section.get('hasMenuItem'), list) and section.get('name'):
                for entry in section['hasMenuItem']:
                    if isinstance(entry, dict) and entry.get('name'):
                        sections[entry['name']] = section['name']
    items = {}
    for root in menu_roots:
        for obj in objects(root):
            if obj.get('@type') != 'MenuItem' or not obj.get('name'):
                continue
            offers = obj.get('offers')
            if isinstance(offers, list):
                if len(offers) != 1:
                    continue  # variant prices need explicit variant identity
                offers = offers[0]
            if not isinstance(offers, dict):
                continue
            currency = offers.get('priceCurrency')
            raw_price = str(offers.get('price', ''))
            price_kind = 'base'
            # CAD inherited only from the matching restaurant's explicit server record.
            if provider == 'DoorDash' and header and currency is None:
                currency = header.get('currency')
                match = re.fullmatch(r'(?:CA)?\$(\d+(?:\.\d{1,2})?)(\+)?', raw_price)
                if not match:
                    continue
                raw_price = match[1]
                price_kind = 'from' if match[2] else 'base'
            if currency != 'CAD':
                continue
            try:
                amount = Decimal(raw_price) * 100
                if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
                    continue
            except (KeyError, InvalidOperation):
                continue
            name = obj['name'].strip()
            item = {'name': name, 'amountCents': int(amount), 'currency': 'CAD', 'priceKind': price_kind}
            item['section'] = sections.get(name, 'Menu')
            if name in items:
                old = items[name]
                if old.get('priceKind') == 'options':
                    continue
                if old['amountCents'] != item['amountCents'] or old['priceKind'] != item['priceKind']:
                    items[name] = {'name': name, 'amountCents': None, 'currency': 'CAD', 'priceKind': 'options', 'section': item['section'], 'priceNote': 'Multiple same-name variants; confirm the chosen option price in the provider app'}
                    continue
            items[name] = item
    if not items:
        raise ValueError('No supported structured menu prices; blocked or changed page layout')
    result = copy.deepcopy(previous)
    result['id'] = store_id(provider, result['url'])
    if header:
        address = header.get('address', {})
        if address.get('city', '').casefold() != 'fredericton' or address.get('countryShortname') != 'CA':
            raise ValueError('Restaurant branch is outside Fredericton')
        result['address'] = address.get('displayAddress') or ', '.join(filter(None, [address.get('street'), address.get('city'), address.get('state')]))
        result['addressSourceUrl'] = result['url']
        result['imageUrl'] = header.get('coverImgUrl')
        result['categories'] = [tag['name'] for tag in header.get('businessTags', []) if tag.get('name')]

    result['menuItems'] = list(items.values())
    result['observedAt'] = now()
    result['retrievedAt'] = result['observedAt']
    result.pop('sourceCrawlAgeAtRetrieval', None)
    result.pop('promotions', None)  # never renew an old promo with a new menu timestamp
    result['coverage'] = 'partial: structured public menu only'
    return result


class ProviderBlocked(ValueError):
    pass


class PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if urlparse(newurl).netloc == 'def.uber.com':
            raise ProviderBlocked('Provider challenge; retry next scheduled cycle')
        if urlparse(newurl).scheme != 'https' or urlparse(newurl).netloc != urlparse(request.full_url).netloc:
            raise ValueError('Unexpected provider redirect')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def fetch(url):
    p = urlparse(url)
    if p.scheme != 'https' or p.netloc not in HOSTS.values():
        raise ValueError('Only public provider hosts are allowed')
    request = Request(url, headers={'User-Agent': 'NibbleCatalog/1.0', 'Accept': 'text/html'})
    with build_opener(PublicRedirect()).open(request, timeout=25) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError('Page exceeds size limit')
        return body


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    os.replace(temporary, path)


class Catalog:
    def __init__(self, seeds, runtime, interval_hours=12):
        if interval_hours not in (12, 24):
            raise ValueError('Snapshot interval must be 12 or 24 hours')
        self.seeds, self.runtime = Path(seeds), Path(runtime)
        self.interval_hours = interval_hours
        self.lock = threading.Lock()
        self.run_lock = threading.Lock()
        self.snapshots = {}
        for provider, filename in FILES.items():
            path = self.runtime / filename
            if not path.exists():
                path = self.seeds / filename
            self.snapshots[provider] = validate(json.loads(path.read_text()), provider)
        status_path = self.runtime / 'status.json'
        self.status = json.loads(status_path.read_text()) if status_path.exists() else {'providers': {}}

    def bundle(self):
        with self.lock:
            return {'version': 1, 'providers': copy.deepcopy(self.snapshots)}

    def collect_once(self, providers=None, store_urls=None):
        if not self.run_lock.acquire(blocking=False):
            return
        try:
            for provider, snapshot in copy.deepcopy(self.snapshots).items():
                if providers and provider not in providers:
                    continue
                attempts, updates = [], {}
                # Discovery runs once per provider per cycle. If blocked, stop
                # requests to that provider until the next scheduled cycle.
                try:
                    candidates = {s['id']: s for s in snapshot['stores']}
                    pending, visited = ([] if store_urls is not None else [snapshot['sourceUrl']]), set()
                    while pending and len(visited) < 100:
                        page = pending.pop(0)
                        if page in visited:
                            continue
                        visited.add(page)
                        try:
                            logging.info('%s: directory %d: %s', provider, len(visited), page)
                            city_body = fetch(page)
                            directory_path = self.runtime / 'directories' / provider.replace(' ', '-') / (hashlib.sha256(page.encode()).hexdigest() + '.html')
                            directory_path.parent.mkdir(parents=True, exist_ok=True)
                            directory_path.write_bytes(city_body)
                            found, pages = parse_directory(city_body, page, provider)
                            for listing in found:
                                sid = store_id(provider, listing['url'])
                                old = candidates.get(sid)
                                # Directory refresh never updates price timestamps.
                                if old is None:
                                    old = {'id': sid, 'menuItems': [], 'retrievedAt': now(),
                                           'coverage': 'directory only; menu unavailable'}
                                if old.get('url'):
                                    listing['url'] = old['url']
                                old.update(listing)
                                old['directoryObservedAt'] = now()
                                candidates[sid] = old
                            if found:
                                pending.extend(p for p in pages if p not in visited and p not in pending)
                            attempts.append({'url': page, 'status': 'directory', 'restaurants': len(found)})
                        except (HTTPError, ProviderBlocked) as error:
                            attempts.append({'url': page, 'status': 'blocked', 'reason': str(error)})
                            break
                        if pending:
                            time.sleep(2)
                    # Save directory identities even when menu requests are blocked.
                    snapshot['stores'] = list(candidates.values())
                    consecutive_blocks = 0
                    for previous in ([] if attempts and attempts[-1]['status'] == 'blocked' else candidates.values()):
                        if store_urls is not None and previous['url'] not in store_urls:
                            continue
                        observed = previous.get('observedAt')
                        if observed and time.time() - datetime.fromisoformat(observed.replace('Z', '+00:00')).timestamp() < self.interval_hours * 3600:
                            continue
                        try:
                            logging.info('%s: collecting %s', provider, previous['url'])
                            body = fetch(previous['url'])
                            consecutive_blocks = 0
                            if provider == 'DoorDash':
                                header = store_header(body, previous['id'].removeprefix('ss_doordash_'))
                                address = header.get('address', {}) if header else {}
                                if address.get('city', '').casefold() == 'fredericton' and address.get('countryShortname') == 'CA' and address.get('displayAddress'):
                                    previous['address'] = address['displayAddress']
                                    previous['addressSourceUrl'] = previous['url']
                                    previous['directoryObservedAt'] = now()
                                    previous['imageUrl'] = header.get('coverImgUrl')
                            store = parse_menu(body, previous, provider)
                            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                            raw_path = self.runtime / 'raw' / provider.replace(' ', '-') / f"{store['id']}-{stamp}.html"
                            raw_path.parent.mkdir(parents=True, exist_ok=True)
                            raw_path.write_bytes(body)
                            updates[store['id']] = store
                            logging.info('%s: retained %s (%d items)', provider, store['name'], len(store['menuItems']))
                            atomic_json(self.runtime / 'history' / f"{store['id']}-{stamp}.json", store)
                            attempts.append({'url': previous['url'], 'status': 'success', 'items': len(store['menuItems'])})
                        except ProviderBlocked as error:
                            attempts.append({'url': previous['url'], 'status': 'blocked', 'reason': str(error)})
                            consecutive_blocks += 1
                            if consecutive_blocks >= 3:
                                break
                        except HTTPError as error:
                            attempts.append({'url': previous['url'], 'status': 'blocked' if error.code in (403, 429) else 'failed', 'reason': f'HTTP {error.code}'})
                            if error.code == 429:
                                break
                            consecutive_blocks = consecutive_blocks + 1 if error.code == 403 else 0
                            if consecutive_blocks >= 3:
                                break
                        except Exception as error:
                            attempts.append({'url': previous['url'], 'status': 'failed', 'reason': str(error)})
                        time.sleep(2)
                except Exception as error:
                    attempts.append({'url': snapshot['sourceUrl'], 'status': 'blocked' if isinstance(error, HTTPError) and error.code in (403, 429) else 'failed', 'reason': str(error)})
                if updates or snapshot != self.snapshots[provider]:
                    snapshot['stores'] = [updates.get(s['id'], s) for s in snapshot['stores']]
                    # Keep original top-level retrieval time: unchanged stores
                    # must never inherit a successful neighbour's newer timestamp.
                    filename = FILES[provider]
                    validate(snapshot, provider)
                    atomic_json(self.runtime / filename, snapshot)
                result = {'lastAttemptAt': now(), 'updatedStores': len(updates), 'attempts': attempts}
                with self.lock:
                    self.snapshots[provider] = snapshot
                    self.status['providers'][provider] = result
                    atomic_json(self.runtime / 'status.json', self.status)
                logging.info('%s: %d updated stores; %s', provider, len(updates), attempts)
        finally:
            self.run_lock.release()

    def run(self):
        while True:
            due = {p for p in HOSTS if not self.status['providers'].get(p, {}).get('lastAttemptAt') or
                   time.time() - datetime.fromisoformat(self.status['providers'][p]['lastAttemptAt']).timestamp() >= self.interval_hours * 3600}
            if not due:
                time.sleep(60)
                continue
            try:
                self.collect_once(due)
            except Exception:
                logging.exception("Collection failed; retrying in one hour")
                for _ in range(60):
                    time.sleep(60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', default='data')
    parser.add_argument('--runtime', default='snapshots')
    parser.add_argument('--interval-hours', type=int, choices=[12, 24], default=12)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--provider', choices=list(HOSTS), help='Limit a one-off collection to one provider')
    parser.add_argument('--retry-parse-failures', action='store_true', help='Retry only prior parser failures; never blocked requests')
    parser.add_argument('--publish-once', action='store_true', help='Publish retained data without fetching')
    parser.add_argument('--publisher', default=os.getenv('CATALOG_PUBLISHER', '/usr/local/bin/catalog-publish'))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    catalog = Catalog(args.seeds, args.runtime, args.interval_hours)
    if args.provider and not args.once:
        parser.error('--provider requires --once')
    if args.retry_parse_failures and not args.once:
        parser.error('--retry-parse-failures requires --once')
    if args.once:
        urls = None
        if args.retry_parse_failures:
            urls = {attempt['url'] for provider, status in catalog.status['providers'].items() if not args.provider or provider == args.provider for attempt in status.get('attempts', []) if attempt['status'] == 'failed' and any(reason in attempt.get('reason','') for reason in ['Conflicting prices', 'ambiguous same-name', 'No supported structured menu'])}
        catalog.collect_once({args.provider} if args.provider else None, urls)
    if not args.once and not args.publish_once:
        threading.Thread(target=catalog.run, daemon=True).start()
    published = None
    while True:
        payload = json.dumps(catalog.bundle(), sort_keys=True, separators=(',', ':')).encode()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != published:
            try:
                subprocess.run([args.publisher], input=payload, check=True, timeout=150)
                published = digest
            except (subprocess.SubprocessError, OSError):
                logging.exception('Publish failed; retained data will be retried')
                if args.once or args.publish_once:
                    raise
        if args.once or args.publish_once:
            return
        time.sleep(60)


if __name__ == '__main__':
    main()
