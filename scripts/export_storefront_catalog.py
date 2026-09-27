"""Adapt the validated public catalog to existing storefront entities; never invent prices.
Usage: python scripts/export_storefront_catalog.py --catalog /path/to/api-catalog.json
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse
from doordash_page import store_header
from enrichment import rating_for
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
    chosen=[r for r in catalog['restaurants'] if r['items']]
    chosen.sort(key=lambda r: (0 if r['id']=='catalog-ss_ubereats_0a5ba1d349096949787465cf' else 1 if r['id']=='catalog-ss_ubereats_b516b917b6ed6c6e5c3ba08c' else 2, r['name']))
    enrichment_path=ROOT/'nibble-data-acquisition/data/enrichment.json'
    enrichment=json.loads(enrichment_path.read_text()) if enrichment_path.exists() else {}
    media_path=ROOT/'nibble-data-acquisition/data/provider_metadata.json'
    media=json.loads(media_path.read_text()) if media_path.exists() else {}
    result={'restaurants':[],'items':[],'offers':[],'provenance':{},'links':{},'providerIds':{},'menuCounts':{},'ratings':{},'merchantOrdering':{},'promotions':enrichment.get('promotions',[]),'providerScores':{}}
    for r in chosen:
        rid=r['id'];name=r['name'];lower=name.lower()
        cuisine='mexican' if 'taco' in lower else 'pizza' if any(k in lower for k in ['pizza','pizzeria','wingstreet']) else 'shawarma' if 'osmow' in lower else 'chicken' if any(k in lower for k in ['kfc','swiss']) else 'burgers'
        hero={'mexican':'taco-cutout','pizza':'pizza','shawarma':'wrap','chicken':'chicken','burgers':'burger'}[cuisine]
        if 'mcdonald' in lower:hero='bigmac'
        lat,lng=0,0
        rating=enrichment.get('ratings',{}).get(rid)
        merchant=next((m for m in enrichment.get('merchants',[]) if m['match'].casefold() in lower),None)
        if merchant:result['merchantOrdering'][rid]=merchant
        for source in r['sources']:
            if source['provider'] != 'DoorDash': continue
            match=re.search(r'-(\d+)/?$',source['url'])
            if not match: continue
            pages=sorted((ROOT/'nibble-data-acquisition/snapshots/validated/raw/DoorDash').glob(f'ss_doordash_{match[1]}-*.html'))
            for page in reversed(pages):
                body=page.read_text()
                if rating is None:rating=rating_for(body,source['url'])
                header=store_header(body.encode(),match[1])
                address=header.get('address',{}) if header else {}
                if address.get('city','').casefold()=='fredericton' and address.get('countryShortname')=='CA':
                    try:lat,lng=float(address['lat']),float(address['lng'])
                    except (ValueError,KeyError):continue
                    break
        if rating:result['ratings'][rid]=rating
        result['restaurants'].append({'id':rid,'name':name,'imageURL':restaurant_images.get(rid,{}).get('file') or (r.get('image') if urlparse(r.get('image','')).hostname in {'menu-images-static.skipthedishes.com','tb-static.uber.com','img.cdn4dd.com'} else None) or images[hero]['file'],'location':{'latitude':lat,'longitude':lng,'address':next((source['address'] for source in r['sources'] if source['provider']=='DoorDash' and source.get('address')),r['address']),'city':'Fredericton','region':'NB','postalCode':''},'cuisineIds':['cui_'+cuisine],'categoryIds':['cat_food'],'rating':{'average':rating['average'],'count':rating['count']} if rating else {'average':0,'count':0},'phone':'','appURL':merchant['orderUrl'] if merchant else '','hours':[]})
        result['links'][rid]={PROVIDERS[s['provider']]:s['url'] for s in r['sources'] if s['provider'] in PROVIDERS}
        result['providerIds'][rid]=list(result['links'][rid])
        result['providerScores'][rid]=[{'provider':source['provider'],'sourceUrl':source['url'],**media[source['url']]['score']} for source in r['sources'] if media.get(source['url'],{}).get('score',{} ) and media[source['url']]['score'].get('value') is not None]
        result['menuCounts'][rid]=len(r['items'])
        for raw in r['items']:
            itemname=clean(raw['name']);iid=rid+'_'+hashlib.sha256(raw['id'].encode()).hexdigest()[:12]
            photo=photo_for(itemname,name)
            section=raw.get('section') or ('Drinks' if photo in ['drink','coffee','water'] else 'Sides & sweets' if photo in ['dessert','churros-stuffed','fries','nachos'] else 'Mains')
            provider_photo=next((media.get(offer['sourceUrl'],{}).get('itemImages',{}).get(raw['name']) for offer in raw['offers'] if media.get(offer['sourceUrl'],{}).get('itemImages',{}).get(raw['name'])),None)
            result['items'].append({'id':iid,'restaurantId':rid,'name':itemname,'description':'','section':section,'imageURL':provider_photo or images[photo]['file']})
            for offer in raw['offers']:
                if offer.get('amountCents') is None:continue
                provider=PROVIDERS.get(offer['provider'])
                if not provider:continue
                oid=iid+'_'+provider
                result['offers'].append({'id':oid,'restaurantId':rid,'menuItemId':iid,'providerId':provider,'price':{'amountCents':offer['amountCents'],'currency':'CAD'},'estimatedMinutes':0})
                result['provenance'][oid]={'sourceUrl':offer['sourceUrl'],'startingPrice':offer.get('priceKind')=='from'}
    for menu in enrichment.get('directMenus',[]):
        rid=menu['id']
        result['restaurants'].append({'id':rid,'name':menu['name'],'imageURL':images['pizza']['file'],'location':{'latitude':0,'longitude':0,'address':menu['address'],'city':'Fredericton','region':'NB','postalCode':''},'cuisineIds':['cui_pizza'],'categoryIds':['cat_food'],'rating':{'average':0,'count':0},'phone':'','appURL':menu['sourceUrl'],'hours':[]})
        result['merchantOrdering'][rid]={'orderUrl':menu['sourceUrl'],'sourceUrl':menu['sourceUrl'],'note':'Menu from the restaurant website. Listed prices are for pickup; check delivery and options with the restaurant.'}
        result['links'][rid]={'prov_direct':menu['sourceUrl']}
        result['providerIds'][rid]=['prov_direct']
        result['menuCounts'][rid]=len(menu['items'])
        for raw in menu['items']:
            iid=rid+'_'+hashlib.sha256((raw['section']+'|'+raw['name']).encode()).hexdigest()[:12]
            imagekey='dish-'+hashlib.sha256(raw['imageUrl'].encode()).hexdigest()[:16]
            image=images.get(imagekey,images[photo_for(raw['name'],menu['name'])])['file']
            result['items'].append({'id':iid,'restaurantId':rid,'name':raw['name'],'description':raw['description'],'section':raw['section'],'imageURL':image})
            if raw['amountCents'] is None:continue
            oid=iid+'_prov_direct'
            result['offers'].append({'id':oid,'restaurantId':rid,'menuItemId':iid,'providerId':'prov_direct','price':{'amountCents':raw['amountCents'],'currency':'CAD'},'estimatedMinutes':0})
            result['provenance'][oid]={'sourceUrl':menu['sourceUrl'],'startingPrice':True,'fulfillmentMode':'pickup'}
    target=WEB/'src/catalog/catalog.json';target.write_text(json.dumps(result,indent=2)+'\n')
    print('Exported',len(result['restaurants']),'restaurants,',len(result['items']),'pictured items,',len(result['offers']),'collected provider prices; no synthetic offers')
if __name__=='__main__':main()
