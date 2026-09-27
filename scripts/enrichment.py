"""Public-page enrichment parsers. No account data, inferred discounts or fuzzy branch merges."""
import html
import json
import re
from decimal import Decimal, InvalidOperation


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def structured_restaurants(body):
    for script in re.findall(r'<script[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>', body, re.S | re.I):
        try:
            data = json.loads(script)
        except ValueError:
            continue
        for record in objects(data):
            if record.get('@type') == 'Restaurant':
                yield record


def rating_for(body, source_url):
    """Keep value/count from the SAME aggregate. Never mix header totals with review samples."""
    for restaurant in structured_restaurants(body):
        rating = restaurant.get('aggregateRating', {})
        try:
            value = float(rating['ratingValue'])
            count = int(rating.get('ratingCount', rating.get('reviewCount', 0)))
            scale = float(rating.get('bestRating', 5))
            if scale != 5 or not 0 < value <= scale or count <= 0:
                continue
        except (ValueError, TypeError, KeyError):
            continue
        return {'average': value, 'count': count, 'scale': 5, 'provider': 'DoorDash', 'sourceUrl': source_url, 'countScope': 'Published structured rating count'}
    return None


def text(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', ' ', value))).strip()


def wix_menu(body):
    """Wix public ordering HTML, scoped to each dish, preserving section/description/photo."""
    starts = list(re.finditer(r'<[^>]+data-hook="dish-item__root"[^>]*>', body))
    dishes = []
    for index, start in enumerate(starts):
        chunk = body[start.end():starts[index+1].start() if index+1 < len(starts) else len(body)]
        def field(hook):
            match = re.search(r'data-hook="'+hook+r'"[^>]*>(.*?)</(?:p|h\d|span)>', chunk, re.S)
            return text(match[1]) if match else ''
        name, price = field('dish-item__title'), field('dish-item__price')
        if not name:
            continue
        amount = re.fullmatch(r'CA\$([\d,]+\.\d{2})', price)
        try:
            cents = int(Decimal(amount[1].replace(',', '')) * 100) if amount else None
        except InvalidOperation:
            cents = None
        # $0 is an unconfigured item/option, not a free meal.
        if cents is not None and cents <= 0:
            cents = None
        img = re.search(r'<img\b[^>]*data-hook="dish-item__image"[^>]*>', chunk)
        src = re.search(r'src="([^"]+)"', img[0]) if img else None
        sections = re.findall(r'data-hook="menu-section__title"[^>]*>(.*?)</h\d>', body[:start.start()], re.S)
        dishes.append({'name': name, 'description': field('dish-item__description'), 'amountCents': cents,
                       'imageUrl': html.unescape(src[1]).split('/v1/')[0] if src else '',
                       'section': text(sections[-1]) if sections else 'Menu', 'fulfillmentMode': 'pickup'})
    return dishes
