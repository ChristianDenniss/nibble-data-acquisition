"""Adapt the validated public catalog to existing storefront entities; never invent prices.
Usage: python scripts/export_storefront_catalog.py --catalog /path/to/api-catalog.json
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from doordash_page import store_header
ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'nibble-web-platform'
PROVIDERS = {'DoorDash':'prov_doordash','Uber Eats':'prov_ubereats','SkipTheDishes':'prov_skip'}

def clean(name):
    return re.sub(r'\s+', ' ', re.sub(r'\s*\[[^]]*\]', '', name).replace('™','').replace('®','')).strip()

def photo_for(name, restaurant):
    n = name.lower()
    if ('water' in n or 'dasani' in n) and 'vitamin' not in n: return 'water'
    if any(k in n for k in ['coffee','latte','cappuccino','espresso']): return 'coffee'
    if any(k in n for k in ['churro','chimi cheesecake']): return 'churros-stuffed'
    if any(k in n for k in ['flurry','cookie','pie','sundae','shake','brownie','cake']): return 'dessert'
    if any(k in n for k in ['water','jarritos','pop','coca','sprite','tea','juice','milk','powerade','vitamin','monster energy','pepsi','lemonade','soda']): return 'drink'
    if 'fries' in n or 'poutine' in n or 'onion rings' in n: return 'fries'
    if 'taco boyz' in restaurant.lower():
        if 'bowl' in n: return 'burrito-bowl'
        if 'quesadilla' in n: return 'quesadilla'
        if 'pocket' in n: return 'taco-pocket'
        if 'burrito' in n or 'chimichanga' in n: return 'burrito-cutout'
        if 'taco' in n: return 'taco-cutout'
        return 'nachos'
    if 'mcdonald' in restaurant.lower():
        if 'nugget' in n: return 'nuggets'
        if 'wrap' in n: return 'wrap'
        if any(k in n for k in ['chicken','crispy','fish','veggie']): return 'mcchicken'
        return 'bigmac'
    if 'pizza' in n or 'pizza' in restaurant.lower(): return 'pizza'
    if 'wing' in n: return 'wings'
    if 'salad' in n or 'bowl' in n or 'rocks' in n or 'half & half' in n: return 'salad'
    if 'soup' in n: return 'soup'
    if 'fish' in n: return 'fish'
    if 'wrap' in n or 'shawarma' in n: return 'wrap'
    if any(k in n for k in ['burger','baconator','whopper']): return 'burger'
    if any(k in n for k in ['chicken','tender','strip','bucket']): return 'chicken'
    if any(k in n for k in ['sandwich','sub','panini']): return 'sandwich'
    return 'burger' if any(k in restaurant.lower() for k in ['wendy','harvey','a&w']) else 'chicken'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--catalog',type=Path,required=True);args=parser.parse_args()
    catalog=json.loads(args.catalog.read_text())
    imagefile=WEB/'public/images/menu/sources.json';images=json.loads(imagefile.read_text())
    for entry in images.values():entry['file']=entry['file'].replace('/images/demo/','/images/menu/')
    imagefile.write_text(json.dumps(images,indent=2)+'\n')
    restaurant_images=json.loads((WEB/'public/images/menu/restaurants.json').read_text())
    chosen=[r for r in catalog['restaurants'] if len(r['items'])>=20][:12]
    chosen.sort(key=lambda r: (0 if 'Taco Boyz' in r['name'] else 1 if 'McDonald' in r['name'] else 2, r['name']))
    result={'restaurants':[],'items':[],'offers':[],'provenance':{},'links':{},'providerIds':{},'menuCounts':{}}
    for r in chosen:
        rid=r['id'];name=r['name'];lower=name.lower()
        cuisine='mexican' if 'taco' in lower else 'pizza' if any(k in lower for k in ['pizza','pizzeria','wingstreet']) else 'shawarma' if 'osmow' in lower else 'chicken' if any(k in lower for k in ['kfc','swiss']) else 'burgers'
        hero={'mexican':'taco-cutout','pizza':'pizza','shawarma':'wrap','chicken':'chicken','burgers':'burger'}[cuisine]
        if 'mcdonald' in lower:hero='bigmac'
        lat,lng=0,0
        for source in r['sources']:
            if source['provider'] != 'DoorDash': continue
            match=re.search(r'-(\d+)/?$',source['url'])
            if not match: continue
            pages=sorted((ROOT/'nibble-data-acquisition/snapshots/validated/raw/DoorDash').glob(f'ss_doordash_{match[1]}-*.html'))
            for page in reversed(pages):
                header=store_header(page.read_bytes(),match[1])
                address=header.get('address',{}) if header else {}
                if address.get('city','').casefold()=='fredericton' and address.get('countryShortname')=='CA':
                    try:lat,lng=float(address['lat']),float(address['lng'])
                    except (ValueError,KeyError):continue
                    break
        result['restaurants'].append({'id':rid,'name':name,'imageURL':(restaurant_images.get(rid) or images[hero])['file'],'location':{'latitude':lat,'longitude':lng,'address':next((source['address'] for source in r['sources'] if source['provider']=='DoorDash' and source.get('address')),r['address']),'city':'Fredericton','region':'NB','postalCode':''},'cuisineIds':['cui_'+cuisine],'categoryIds':['cat_food'],'rating':{'average':0,'count':0},'phone':'','appURL':'','hours':[]})
        result['links'][rid]={PROVIDERS[s['provider']]:s['url'] for s in r['sources'] if s['provider'] in PROVIDERS}
        result['providerIds'][rid]=list(result['links'][rid])
        result['menuCounts'][rid]=len(r['items'])
        for raw in r['items']:
            itemname=clean(raw['name']);iid=rid+'_'+hashlib.sha256(raw['id'].encode()).hexdigest()[:12]
            photo=photo_for(itemname,name)
            section=raw.get('section') or ('Drinks' if photo in ['drink','coffee','water'] else 'Sides & sweets' if photo in ['dessert','churros-stuffed','fries','nachos'] else 'Mains')
            result['items'].append({'id':iid,'restaurantId':rid,'name':itemname,'description':'','section':section,'imageURL':images[photo]['file']})
            for offer in raw['offers']:
                if offer.get('amountCents') is None:continue
                provider=PROVIDERS.get(offer['provider'])
                if not provider:continue
                oid=iid+'_'+provider
                result['offers'].append({'id':oid,'restaurantId':rid,'menuItemId':iid,'providerId':provider,'price':{'amountCents':offer['amountCents'],'currency':'CAD'},'estimatedMinutes':0})
                result['provenance'][oid]={'sourceUrl':offer['sourceUrl'],'startingPrice':offer.get('priceKind')=='from'}
    target=WEB/'src/catalog/catalog.json';target.write_text(json.dumps(result,indent=2)+'\n')
    print('Exported',len(result['restaurants']),'restaurants,',len(result['items']),'pictured items,',len(result['offers']),'collected provider prices; no synthetic offers')
if __name__=='__main__':main()
