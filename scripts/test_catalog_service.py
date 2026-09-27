import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from catalog_service import Catalog, parse_menu, store_id, validate, ProviderBlocked, PublicRedirect
from provider_directory import parse_directory
from urllib.request import Request

SEEDS = Path(__file__).resolve().parent.parent / 'data'
if not SEEDS.exists():
    SEEDS = Path('/app/data')


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.catalog = Catalog(SEEDS, self.tmp.name)

    def test_publish_retains_provider_identity_and_provenance(self):
        bundle = self.catalog.bundle()
        self.assertEqual(bundle['version'], 1)
        self.assertEqual(set(bundle['providers']), {'Uber Eats', 'DoorDash', 'SkipTheDishes'})
        self.assertIn('sourceCrawlAgeAtRetrieval', bundle['providers']['Uber Eats']['stores'][0])
        bundle['providers']['Uber Eats']['stores'].clear()
        self.assertTrue(self.catalog.snapshots['Uber Eats']['stores'])

    def test_blocked_refresh_preserves_prices_and_timestamp(self):
        before = copy.deepcopy(self.catalog.snapshots)
        with patch('catalog_service.fetch', side_effect=HTTPError('https://www.doordash.com',403,'Forbidden',{},None)) as request:
            self.catalog.collect_once()
            self.assertEqual(request.call_count, 3)  # one attempt per provider, no retry storm
        self.assertEqual(before, self.catalog.snapshots)
        self.assertEqual(self.catalog.status['providers']['DoorDash']['updatedStores'],0)
        self.assertEqual(self.catalog.status['providers']['DoorDash']['attempts'][0]['status'],'blocked')
        self.assertFalse((Path(self.tmp.name)/'doordash-fredericton.json').exists())
        self.assertTrue((Path(self.tmp.name)/'status.json').exists())

    def test_parse_explicit_prices_only(self):
        source = self.catalog.snapshots['DoorDash']['stores'][0]
        body = b'<script type="application/ld+json">{"@type":"MenuItem","name":"Bowl","offers":{"price":"14.30","priceCurrency":"CAD"}}</script>'
        got = parse_menu(body, source, 'DoorDash')
        self.assertEqual(got['menuItems'][0]['amountCents'],1430)
        self.assertIn('observedAt',got)
        self.assertNotIn('sourceCrawlAgeAtRetrieval',got)
        for bad in [b'<h1>Just a moment...</h1>',b'<p>Free delivery $0</p>',body.replace(b'14.30',b'NaN'),body.replace(b'CAD',b'USD')]:
            with self.assertRaises(ValueError):
                parse_menu(bad,source,'DoorDash')

    def test_ambiguous_variant_does_not_discard_the_whole_menu(self):
        records=[{'@type':'MenuItem','name':name,'offers':{'price':price,'priceCurrency':'CAD'}} for name,price in [('Burger','10.00'),('Burger','12.00'),('Water','3.00'),('Burger','10.00')]]
        body=('<script type="application/ld+json">'+json.dumps(records)+'</script>').encode()
        result=parse_menu(body,self.catalog.snapshots['DoorDash']['stores'][0],'DoorDash')
        items={i['name']:i for i in result['menuItems']}
        self.assertIsNone(items['Burger']['amountCents'])
        self.assertEqual(items['Burger']['priceKind'],'options')
        self.assertEqual(items['Water']['amountCents'],300)

    def test_success_retains_history_and_unchanged_store_dates(self):
        self.catalog.snapshots['DoorDash']['stores'][0]['observedAt'] = '2000-01-01T00:00:00+00:00'
        before = copy.deepcopy(self.catalog.snapshots['DoorDash'])
        count = 0
        def fetch(url):
            nonlocal count
            if 'restaurants' in url or '/city/' in url:
                return b'<html></html>'
            count += 1
            if '23391251' in url:
                return b'<script type="application/ld+json">{"@type":"MenuItem","name":"Large Nachos","offers":{"price":"15.75","priceCurrency":"CAD"}}</script>'
            raise HTTPError(url,403,'Forbidden',{},None)
        with patch('catalog_service.fetch',side_effect=fetch),patch('catalog_service.time.sleep'):
            self.catalog.collect_once()
        after = self.catalog.snapshots['DoorDash']
        self.assertEqual(after['retrievedAt'],before['retrievedAt'])
        self.assertEqual(after['stores'][1],before['stores'][1])
        self.assertEqual(after['stores'][0]['menuItems'][0]['amountCents'],1575)
        self.assertTrue(list(Path(self.tmp.name).glob('history/*.json')))
        restarted = Catalog(SEEDS,self.tmp.name)
        self.assertEqual(restarted.snapshots['DoorDash'], after)

    def test_directory_layouts_and_pagination(self):
        body = b'<a data-testid="store-card" href="/ca/store/subway/test"><h3>Subway</h3></a><div data-test="store-link"><div>Subway</div><span>Sandwich</span><span>349 King St, Fredericton, NB</span></div><a href="?page=2#main-content">Next</a><a href="https://other.example/?page=3">Bad</a>'
        body = body.replace(b'<div>Subway</div>', b'<img src="photo.jpg" alt="Subway"/><div>Subway</div>')
        stores, pages = parse_directory(body, 'https://www.ubereats.com/ca/city/fredericton-nb', 'Uber Eats')
        self.assertEqual(stores[0]['address'], '349 King St, Fredericton, NB')
        self.assertEqual(pages, ['https://www.ubereats.com/ca/city/fredericton-nb?page=2'])

    def test_doordash_currency_and_branch_identity(self):
        source = self.catalog.snapshots['DoorDash']['stores'][0]
        header = {'id': '23391251', 'name': 'Taco Boyz', 'currency': 'CAD', 'address': {'city': 'Fredericton', 'countryShortname': 'CA', 'displayAddress': '520 Smythe St #2A'}}
        menu = {'@type': 'MenuItem', 'name': 'Tacos', 'offers': {'price': '$16.85+'}}
        def page(header):
            record = '1:' + json.dumps({'storeHeaderLite': header}) + '\n'
            return ('<script>self.__next_f.push(' + json.dumps([1, record]) + ')</script><script type="application/ld+json">' + json.dumps({'@type': 'Restaurant', 'name': 'Taco Boyz', 'hasMenu': menu}) + '</script>').encode()
        parsed = parse_menu(page(header), source, 'DoorDash')
        self.assertEqual(parsed['menuItems'][0]['amountCents'], 1685)
        self.assertEqual(parsed['menuItems'][0]['priceKind'], 'from')
        self.assertEqual(parsed['address'], '520 Smythe St #2A')
        menu['offers']['price'] = 'CA$10.99'
        self.assertEqual(parse_menu(page(header), source, 'DoorDash')['menuItems'][0]['amountCents'], 1099)
        for overrides in [{'id':'wrong-branch'}, {'currency':'USD'}]:
            with self.assertRaises(ValueError): parse_menu(page({**header, **overrides}), source, 'DoorDash')

    def test_provider_challenge_stops_collection(self):
        with self.assertRaises(ProviderBlocked):
            PublicRedirect().redirect_request(Request('https://www.ubereats.com/ca/store/a/b'), None, 307, '', {}, 'https://def.uber.com/en/challenge')

    def test_removes_provider_nul_text(self):
        source = copy.deepcopy(self.catalog.snapshots['Uber Eats'])
        source['stores'][0]['categories'] = ['Pizza\x00']
        self.assertEqual(validate(source, 'Uber Eats')['stores'][0]['categories'], ['Pizza'])

    def test_skip_branch_and_currency_validation(self):
        source = self.catalog.snapshots['SkipTheDishes']['stores'][0]
        self.assertTrue(store_id('SkipTheDishes', source['url']).startswith('ss_skip_'))
        menu = {'@type': 'Restaurant', 'name': 'Taco Boyz', 'address': {'streetAddress': '520 Smythe St', 'addressLocality': 'Fredericton'}, 'hasMenu': {'@type': 'MenuItem', 'name': 'Water', 'offers': {'price': '3.75', 'priceCurrency': 'CAD'}}}
        def body(value):
            return ('<script type="application/ld+json">' + json.dumps(value) + '</script>').encode()
        self.assertEqual(parse_menu(body(menu), source, 'SkipTheDishes')['menuItems'][0]['amountCents'], 375)
        menu['address']['streetAddress'] = 'Other branch'
        with self.assertRaises(ValueError): parse_menu(body(menu), source, 'SkipTheDishes')
        menu['address']['streetAddress'] = '520 Smythe St'
        menu['hasMenu']['offers']['priceCurrency'] = 'USD'
        with self.assertRaises(ValueError): parse_menu(body(menu), source, 'SkipTheDishes')
        with self.assertRaises(ValueError): store_id('SkipTheDishes', 'https://www.skipthedishes.com/cities/fredericton')

    def test_reject_invalid_snapshot(self):
        source=copy.deepcopy(self.catalog.snapshots['DoorDash'])
        source['stores'][0]['menuItems'][0]['amountCents']=-1
        with self.assertRaises(ValueError):validate(source,'DoorDash')
        with self.assertRaises(ValueError):Catalog(SEEDS,self.tmp.name,1)

if __name__=='__main__':unittest.main()
