"""Download larger source renditions; retain attribution and reject resolution regressions.
Requires macOS sips for image verification. No pixel upscaling or invented product photos.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT/'nibble-web-platform'


def dimensions(path):
    proc = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', str(path)], capture_output=True, text=True)
    values = re.findall(r'pixel(?:Width|Height): (\d+)', proc.stdout)
    return tuple(map(int, values)) if len(values) == 2 else (0, 0)


def download(entry):
    entry = dict(entry)
    target = WEB/'public'/entry['file'].lstrip('/')
    old = dimensions(target) if target.exists() else (0, 0)
    try:
        with urlopen(Request(entry['url'], headers={'User-Agent': 'Mozilla/5.0'}), timeout=25) as response:
            body = response.read(15_000_001)
            if not response.headers.get('Content-Type', '').startswith('image/') or len(body) > 15_000_000:
                raise ValueError('not a bounded image')
        with tempfile.NamedTemporaryFile(suffix=target.suffix) as temporary:
            temporary.write(body); temporary.flush()
            size = dimensions(temporary.name)
        if min(size) == 0 or size[0]*size[1] < old[0]*old[1]:
            raise ValueError('invalid image or resolution regression')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        entry.update(width=size[0], height=size[1])
        return entry, 'saved'
    except Exception as error:
        return None, type(error).__name__


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    args = parser.parse_args()
    manifest_path = WEB/'public/images/menu/sources.json'
    original = json.loads(manifest_path.read_text())
    jobs = {}
    for key, entry in original.items():
        entry = dict(entry); url = entry['url']
        url = url.replace('w=600&q=85', 'w=1600&q=90').replace('hei=480&wid=424', 'hei=1400&wid=1400')
        url = url.replace('height=400&width=600', 'height=1000&width=1500')
        url = re.sub(r'-\d+x\d+(?=\.(?:png|jpg)$)', '', url)
        entry['url'] = url
        jobs[key] = entry
    enrichment = json.loads((ROOT/'nibble-data-acquisition/data/enrichment.json').read_text())
    for menu in enrichment['directMenus']:
        for item in menu['items']:
            url = item['imageUrl']
            if not url: continue
            key = 'dish-'+hashlib.sha256(url.encode()).hexdigest()[:16]
            jobs[key] = {'file':'/images/menu/'+key+'.jpg', 'url':url+'/v1/fit/w_1200,h_1200,q_90/'+url.rsplit('/',1)[-1], 'sourceUrl':menu['sourceUrl'], 'illustrative':False}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for key, (entry, status) in zip(jobs, pool.map(download, jobs.values())):
            if entry: original[key] = entry
            print(key, status, flush=True)
    manifest_path.write_text(json.dumps(original, indent=2)+'\n')
    path = WEB/'public/images/menu/restaurants.json'
    images = json.loads(path.read_text())
    restaurants = json.loads(args.catalog.read_text())['restaurants']
    jobs = {}
    for restaurant in restaurants:
        if not restaurant['items'] or not restaurant.get('image'): continue
        rid = restaurant['id']; url = restaurant['image']
        jobs[rid] = {'file':images.get(rid,{}).get('file', '/images/menu/restaurant-'+hashlib.sha256(rid.encode()).hexdigest()[:12]+'.jpg'), 'url':url}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for rid, (entry, status) in zip(jobs, pool.map(download, jobs.values())):
            if entry: images[rid] = entry
            print('restaurant', rid, status, flush=True)
    path.write_text(json.dumps(images, indent=2)+'\n')


if __name__ == '__main__': main()
