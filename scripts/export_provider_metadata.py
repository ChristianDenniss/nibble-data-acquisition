"""Retain public provider item artwork and native scores without changing item matching."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,default=ROOT/'snapshots/validated')
    args=parser.parse_args()
    target=ROOT/'data/provider_metadata.json'
    result=json.loads(target.read_text()) if target.exists() else {}
    for path in args.runtime.glob('*-fredericton.json'):
        for store in json.loads(path.read_text())['stores']:
            images={}
            for item in store.get('menuItems',[]):
                url=item.get('imageUrl','')
                if urlparse(url).scheme=='https' and urlparse(url).hostname in {'menu-images-static.skipthedishes.com','tb-static.uber.com','img.cdn4dd.com'}:
                    images[item['name']]=url
            if images or store.get('providerScore'):
                result[store['url']]={'itemImages':images,'score':store.get('providerScore')}
    target.write_text(json.dumps(result,indent=2)+'\n')
    print('Provider artwork:',sum(len(r['itemImages']) for r in result.values()),'item associations across',len(result),'menus')

if __name__=='__main__':main()
