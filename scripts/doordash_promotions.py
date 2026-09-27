"""Read item BOGO badges from branch-scoped public DoorDash carousel records."""
import base64
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from doordash_page import records

def extract(body, store_id):
    found = {}
    for match in re.finditer(r'self\.__next_f\.push\((\[.*?\])\)', body, re.S):
        try:
            chunk = json.loads(match[1])[1]
            root, _ = json.JSONDecoder().raw_decode(chunk.partition(':')[2])
        except (ValueError, IndexError, TypeError, AttributeError):
            continue
        for record in records(root):
            if record.get('__typename') != 'StorePageCarouselItem': continue
            try:
                cursor = record['nextCursor']
                identity = json.loads(base64.b64decode(cursor + '=' * (-len(cursor) % 4)))
                if str(identity['storeLiteData']['storeId']) != store_id: continue
            except (KeyError, ValueError, TypeError): continue
            badges = [entry.get('badge', {}) for entry in record.get('badges', [])]
            if any(b.get('type') == 'bogo_offer' and b.get('isDashpass') is False for b in badges):
                found[record['id']] = {'id':record['id'], 'name':record['name']}
    return list(found.values())

def export(catalog, root):
    output=[]
    names={r['id']:r['name'] for r in catalog['restaurants']}
    for rid, links in catalog['links'].items():
        url=links.get('prov_doordash','')
        match=re.search(r'-(\d+)/?$',url)
        if not match:continue
        sid=match[1]
        pages=sorted((root/'snapshots/validated/raw/DoorDash').glob(f'ss_doordash_{sid}-*.html'))
        if not pages:continue
        page=pages[-1]
        observed=datetime.strptime(page.stem.split('-')[-1],'%Y%m%dT%H%M%S%fZ').replace(tzinfo=timezone.utc).isoformat()
        for item in extract(page.read_text(),sid):
            output.append(dict(id=f'dd-public-{sid}-{item["id"]}',providerId='prov_doordash',restaurantId=rid,restaurantNameContains=names[rid],title='Buy one, get one: '+item['name'],sourceUrl=url,terms='Eligible item: '+item['name']+'. Check eligible sizes, options and redemption limits in DoorDash. Not deducted until those conditions are verified.',expiresOn=None,code='',minimumCents=0,country='CA',eligibility='public_restaurant',reviewedAt=observed,automatic=False,rule={'kind':'bogo','amountCents':0,'itemName':item['name']}))
    return output
