"""Skip public Next.js page data, scoped to the requested Canadian restaurant branch."""
import copy
import json
import re
from urllib.parse import urlparse


def page_props(body):
    source = body.decode('utf-8') if isinstance(body, bytes) else body
    match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', source, re.S)
    if not match:
        return {}
    try:
        return json.loads(match[1]).get('props', {}).get('pageProps', {})
    except (ValueError, AttributeError):
        return {}


def directory(body, page_url):
    props = page_props(body)
    if not re.fullmatch(r'/(?:cities/fredericton|city-(?:area|brands|cuisines)/fredericton/[a-z0-9%&-]+)/?', urlparse(page_url).path):
        return [], []
    stores = []
    for record in props.get('restaurants', []):
        slug = record.get('cleanUrl', '')
        if not record.get('name') or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
            continue
        stores.append({'name': record['name'], 'url': 'https://www.skipthedishes.com/'+slug,
                       'directorySourceUrl': page_url, 'imageUrl': record.get('imageUrls', {}).get('listImageWebUrl')})
    pages = []
    for key in ['cityNeighbourhoodLinks', 'cityBrandsLinks', 'cityCuisinesLinks']:
        for record in props.get(key, []):
            path = record.get('url', '')
            if re.fullmatch(r'/city-(?:area|brands|cuisines)/fredericton/[a-z0-9%&-]+', path):
                pages.append('https://www.skipthedishes.com'+path)
    return stores, sorted(set(pages))


def menu(body, previous):
    props = page_props(body)
    partner, menu = props.get('partner', {}), props.get('menuV2', {})
    slug = urlparse(previous['url']).path.rstrip('/').split('/')[-1]
    location = partner.get('locationDetails', '')
    if partner.get('cleanUrl') != slug or not partner.get('id') or partner.get('id') != menu.get('restaurantId'):
        raise ValueError('Skip page/menu branch identity mismatch')
    if not re.match(r'Fredericton,\s*NB,', location, re.I) or not location.endswith('CAN') or not partner.get('location'):
        raise ValueError('Skip menu branch is not verified in Fredericton, NB, Canada')
    if partner.get('partnerType') not in {'FULL_SERVICE', 'QUICK_SERVICE'}:
        raise ValueError('Skip listing is not a restaurant')
    items = {}
    for category in menu.get('categories', []):
        if category.get('id') == 'POPULAR_GROUP':
            continue
        for raw in category.get('menuItems', []):
            if not raw.get('name') or raw.get('available') is False:
                continue
            amount = raw.get('subtotal')
            # Zero frequently means required configuration, not a free item.
            amount = amount if type(amount) is int and amount > 0 else None
            item = {'name': raw['name'].strip(), 'sourceItemId': raw.get('id'), 'section': category.get('name', 'Menu'),
                    'amountCents': amount, 'currency': 'CAD', 'priceKind': 'base' if amount is not None else 'options',
                    'description': raw.get('description', ''), 'imageUrl': raw.get('imageUrl', '')}
            if amount is None:
                item['priceNote'] = 'Select options in Skip to confirm the item price'
            old = items.get(item['name'])
            if old and old.get('ambiguousVariants'):
                continue
            if old and old['amountCents'] != amount:
                item.update(amountCents=None, priceKind='options', priceNote='Multiple same-name variants; select an option in Skip', ambiguousVariants=True)
            items[item['name']] = item
    if not items:
        raise ValueError('Skip structured menu is empty')
    result = copy.deepcopy(previous)
    result.update(name=partner['name'], address=partner['location']+', '+location,
                  imageUrl=partner.get('imageUrl'), addressSourceUrl=previous['url'],
                  menuItems=list(items.values()), providerScore={'value':partner.get('score',{}).get('formatted'), 'scale':10},
                  observedOffers=partner.get('offers', {}), fulfillmentMode='unspecified')
    return result
