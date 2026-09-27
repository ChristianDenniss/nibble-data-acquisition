"""Download source restaurant artwork, retain attribution, and reject undersized images."""
import json,re,hashlib,urllib.request,subprocess,concurrent.futures
from pathlib import Path
root=Path(__file__).resolve().parents[2]; web=root/'nibble-web-platform'; catalog=json.loads((web/'src/catalog/catalog.json').read_text()); out=web/'public/images/restaurants';out.mkdir(exist_ok=True)
skip={s['url']:s.get('imageUrl') for s in json.loads((root/'nibble-data-acquisition/snapshots/validated/skip-fredericton.json').read_text())['stores']}
def work(r):
 urls=[]; links=catalog['links'].get(r['id'],{})
 if r['name'].startswith('Taco Boyz'):urls.append('https://www.tacoboyz.com/wp-content/uploads/thegem-logos/logo_086fcc33a23c499bd2cca95ffa803eda_3x.png')
 if r['id']=='catalog-direct-luna-king':urls.append('https://static.wixstatic.com/media/f21ad0_01182c430077451abeccc81563425685~mv2.png')
 image=skip.get(links.get('prov_skip'))
 if image:urls.append(image)
 if r['imageURL'].startswith('https://'):urls.append(r['imageURL'])
 for url in urls:
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=10) as res:
    mime=res.headers.get_content_type();raw=res.read(8_000_001)
   if len(raw)>8_000_000:continue
   if raw.startswith(b'\xff\xd8\xff'):mime='image/jpeg'
   elif raw.startswith(b'\x89PNG'):mime='image/png'
   ext={'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp'}.get(mime)
   if not ext:continue
   p=out/(hashlib.sha256(url.encode()).hexdigest()[:16]+ext);p.write_bytes(raw)
   info=subprocess.run(['sips','-g','pixelWidth','-g','pixelHeight',str(p)],capture_output=True,text=True).stdout
   dims=re.findall(r'pixel(?:Width|Height): (\d+)',info)
   if len(dims)!=2 or min(map(int,dims))<180:p.unlink(missing_ok=True);continue
   return r['id'],{'name':r['name'],'file':'/images/restaurants/'+p.name,'sourceUrl':url,'width':int(dims[0]),'height':int(dims[1])}
  except Exception:continue
 return r['id'],None
manifest_path=web/'src/catalog/restaurantImages.json'
manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for rid,entry in pool.map(work,[r for r in catalog['restaurants'] if r['id'] not in manifest]):
  if entry:manifest[rid]=entry
(web/'src/catalog/restaurantImages.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Downloaded original restaurant artwork for',len(manifest),'restaurants',flush=True)
