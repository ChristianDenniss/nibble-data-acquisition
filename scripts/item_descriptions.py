"""Preserve branch-specific descriptions from validated provider snapshots.

Run directly to enrich the current storefront without changing prices or IDs.
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def key(name):
    return re.sub(r'\s+', ' ', re.sub(r'\s*\[[^]]*\]', '', name).replace('™', '').replace('®', '')).strip().casefold()


def enrich(catalog):
    sources = {}
    for path in sorted((ROOT / 'nibble-data-acquisition/snapshots/validated').glob('*-fredericton.json')):
        snapshot = json.loads(path.read_text())
        for store in snapshot.get('stores', []):
            for item in store.get('menuItems', []):
                description = html.unescape(re.sub(r'<[^>]+>', '', item.get('description') or '')).strip()
                if description:
                    sources.setdefault((store['url'].rstrip('/'), key(item['name'])), []).append({
                        'description': description, 'sourceUrl': store['url'],
                        'sourceItemName': item['name'], 'retrievedAt': snapshot.get('retrievedAt'),
                    })
    provenance = catalog.setdefault('itemDetailsSources', {})
    official_path = ROOT / 'nibble-data-acquisition/data/mcdonalds-item-details.json'
    official = {key(entry['name']): entry for entry in json.loads(official_path.read_text())} if official_path.exists() else {}
    restaurants = {entry['id']: entry for entry in catalog['restaurants']}
    count = 0
    for item in catalog['items']:
        candidates = []
        for url in catalog['links'].get(item['restaurantId'], {}).values():
            candidates.extend(sources.get((url.rstrip('/'), key(item['name'])), []))
        if candidates:
            # Choose the most complete supplied description, only for the exact branch and item.
            source = max(candidates, key=lambda candidate: len(candidate['description']))
            item['description'] = source['description']
            provenance[item['id']] = source
            count += 1
        elif 'mcdonald' in restaurants[item['restaurantId']]['name'].lower() and key(item['name']) in official:
            source = official[key(item['name'])]
            item['description'] = source['description']
            provenance[item['id']] = {**source, 'scope': 'Canadian standard menu'}
            count += 1
    return count


if __name__ == '__main__':
    path = ROOT / 'nibble-web-platform/src/catalog/catalog.json'
    catalog = json.loads(path.read_text())
    print('Restored descriptions:', enrich(catalog))
    path.write_text(json.dumps(catalog, indent=2) + '\n')
    for restaurant in catalog['restaurants']:
        if any(name in restaurant['name'].lower() for name in ['mcdonald', 'taco boy']):
            items = [item for item in catalog['items'] if item['restaurantId'] == restaurant['id']]
            print(restaurant['name'], sum(bool(item['description']) for item in items), '/', len(items))
