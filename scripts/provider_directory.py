"""Public directory discovery; retain branch addresses independently of menu freshness."""
import re
import json
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, parse_qs

class Directory(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cards, self.links, self.card = [], [], None
        self.depth = 0
        self.end_depth = None
        self.pending_card = None
        self.script = None
        self.structured = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag not in ('img', 'br', 'meta', 'link', 'input', 'hr', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track', 'col'):
            self.depth += 1
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.script = []
        if tag == 'a':
            href = attrs.get('href', '')
            self.links.append(href)
            if attrs.get('data-testid') == 'store-card':
                self.pending_card = {'url': href, 'text': []}
            if attrs.get('data-test') == 'store-link':
                self.card = {'url': href, 'text': []}
                self.end_depth = self.depth
        if tag == 'div' and attrs.get('data-test') == 'store-link' and self.pending_card is not None:
            self.card = self.pending_card
            self.pending_card = None
            self.end_depth = self.depth
        if self.card is not None and tag == 'img':
            self.card.update(name=attrs.get('alt', ''), imageUrl=attrs.get('src', ''))

    def handle_data(self, text):
        if self.script is not None:
            self.script.append(text)
        if self.card is not None and text.strip():
            self.card['text'].append(text.strip())

    def handle_endtag(self, tag):
        if tag in ('img', 'br', 'meta', 'link', 'input', 'hr', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track', 'col'):
            return
        if tag == 'script' and self.script is not None:
            try:
                self.structured.append(json.loads(''.join(self.script)))
            except ValueError:
                pass
            self.script = None
        if self.card is not None and self.depth == self.end_depth:
            self.cards.append(self.card)
            self.card = None
            self.end_depth = None
        self.depth = max(0, self.depth - 1)


def parse_directory(body, page_url, provider):
    if provider == 'SkipTheDishes':
        from skip_page import directory
        stores, pages = directory(body, page_url)
        if stores: return stores, pages
    doc = Directory()
    doc.feed(body.decode('utf-8'))
    stores = []
    for card in doc.cards:
        name = (card.get('name') or (card['text'][0] if card['text'] else '')).strip()
        parts = card['text']
        address = parts[-1] if parts and 'fredericton' in parts[-1].casefold() else ''
        # Only publish named, addressed restaurant cards, not retail listings.
        categories = next((p for p in parts if ' • ' in p), '')
        if not categories:
            categories = ' • '.join(p for p in parts[1:-1] if p not in ('•', 'New') and not re.fullmatch(r'[0-9.]+', p))
        if not name or not address or any(c in categories.casefold() for c in ('grocery', 'retail', 'pharmacy', 'pet supplies', 'convenience')):
            continue
        if provider != 'Uber Eats':
            continue
        stores.append({'name': name, 'url': urljoin(page_url, card['url']),
                       'address': address, 'imageUrl': card.get('imageUrl'),
                       'categories': [s.strip() for s in categories.split(' • ') if s.strip()],
                       'directorySourceUrl': page_url})
    if provider == 'SkipTheDishes':
        from doordash_page import records
        for root in doc.structured:
            for item in records(root):
                address = item.get('address', {})
                parsed = urlparse(item.get('url', ''))
                if item.get('@type') == 'Restaurant' and item.get('name') and isinstance(address, dict) and address.get('addressLocality', '').casefold() == 'fredericton' and parsed.scheme == 'https' and parsed.netloc == 'www.skipthedishes.com' and re.fullmatch(r'/(?:en/)?[a-z0-9]+(?:-[a-z0-9]+)*/?', parsed.path):
                    stores.append({'name': item['name'], 'url': parsed.geturl(), 'address': ', '.join(filter(None, [address.get('streetAddress'), 'Fredericton', address.get('addressRegion')])), 'directorySourceUrl': page_url})
    if provider == 'DoorDash':
        from doordash_page import records
        for root in doc.structured:
            for item in records(root):
                if item.get('@type') != 'Restaurant' or not item.get('name'):
                    continue
                url = item.get('url', '')
                if 'www.doordash.com/store/' not in url or '-fredericton-' not in url:
                    continue
                # City pages may expose converted USD prices; never import those as CAD.
                stores.append({'name': item['name'], 'url': url, 'directorySourceUrl': page_url})
    base = urlparse(page_url)
    pages = set()
    for href in doc.links:
        url = urljoin(page_url, href)
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.netloc != base.netloc or parsed.path != base.path:
            continue
        query = parse_qs(parsed.query)
        page = query.get('page', [''])[0]
        if re.fullmatch(r'\d+', page) and 1 <= int(page) <= 100 and set(query) == {'page'}:
            pages.add(parsed._replace(fragment='').geturl())
    return stores, sorted(pages)
