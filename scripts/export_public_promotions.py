"""Export public branch offers from validated snapshots; never refresh their observation date."""
import json
import re
from doordash_promotions import export as doordash_offers
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

def export(catalog):
    output = []
    snapshot = json.loads((ROOT/'nibble-data-acquisition/snapshots/validated/skip-fredericton.json').read_text())
    branches = {links.get('prov_skip'): rid for rid, links in catalog['links'].items()}
    names = {r['id']: r['name'] for r in catalog['restaurants']}
    for store in snapshot['stores']:
        rid = branches.get(store.get('url'))
        if not rid: continue
        # Some providers sell the promotion as its own menu SKU, not an offer badge.
        for item in store.get('menuItems', []):
            if item.get('section') != 'Buy One Get One Free' or not item.get('name', '').startswith('Buy One, Get One Free '):
                continue
            item_name = re.sub(r'\s*\[[^]]*\]', '', item['name']).strip()
            output.append(dict(id='skip-bundle-'+rid+'-'+str(item.get('sourceItemId',item_name)),providerId='prov_skip',restaurantId=rid,
                restaurantNameContains=names[rid],title=item_name,sourceUrl=store['url'],
                terms=(item.get('description') or 'Select the promotional item in Skip.')+' The displayed price is the promotional menu listing; no additional discount is subtracted.',
                expiresOn=None,code='',minimumCents=0,country='CA',eligibility='public_restaurant',
                reviewedAt=store.get('observedAt') or store.get('retrievedAt') or snapshot['retrievedAt'],
                automatic=False,rule={'kind':'bogo','amountCents':0,'itemName':item_name}))
        offers = store.get('observedOffers', {})
        for field, kind in [('partnerFlatDiscountOffers','fixed'),('partnerBogoOffers','bogo'),('partnerFreeItemOffers','free_item')]:
            for raw in offers.get(field, []):
                item = raw.get('menuItem', {})
                minimum = raw.get('minimumSubtotal', raw.get('orderMinimum', 0))
                if not isinstance(minimum, int) or minimum < 0: continue
                title = raw.get('title') or ('Buy one, get one: ' if kind == 'bogo' else 'Free item: ') + item.get('name', 'Eligible item')
                output.append(dict(id='skip-public-'+raw['id'], providerId='prov_skip', restaurantId=rid,
                    restaurantNameContains=names[rid], title=title, sourceUrl=store['url'],
                    terms=f"Minimum food subtotal ${minimum/100:.2f}. " + ("Selected item and options must qualify; confirm the offer in Skip." if kind != 'fixed' else "Restaurant-funded offer; confirm final eligibility at checkout."),
                    expiresOn=None, code='', minimumCents=minimum, country='CA', eligibility='public_restaurant',
                    reviewedAt=store.get('observedAt') or store.get('retrievedAt') or snapshot['retrievedAt'],
                    rule={'kind':kind, 'amountCents':raw.get('discountAmount',0), 'itemName':item.get('name','')},
                    automatic=kind=='fixed' and raw.get('origin')=='PARTNER_SELF_SERVE' and type(raw.get('discountAmount')) is int and raw['discountAmount']>0))
    output.extend(doordash_offers(catalog, ROOT/'nibble-data-acquisition'))
    return output

if __name__ == '__main__':
    catalog=json.loads((ROOT/'nibble-web-platform/src/catalog/catalog.json').read_text())
    output=export(catalog)
    (ROOT/'nibble-web-platform/src/catalog/publicPromotions.json').write_text(json.dumps(output,indent=2)+'\n')
    (ROOT/'nibble-data-acquisition/data/public_promotions.json').write_text(json.dumps(output,indent=2)+'\n')
    print('Public restaurant offers:',len(output),'; automatically calculable:',sum(p['automatic'] for p in output))
