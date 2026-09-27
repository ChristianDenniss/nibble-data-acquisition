import sys
from pathlib import Path
import unittest
import socket
import json
import contextlib
import io
import tempfile
from unittest.mock import patch
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from enrichment import rating_for, wix_menu
from collect_enrichment import fetch, main

class EnrichmentTests(unittest.TestCase):
    def test_outage_does_not_refresh_promotions_sharing_a_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'config').mkdir()
            (root/'data').mkdir()
            source = 'https://example.com/terms'
            promos = [{'id': key, 'sourceUrl': source, 'reviewedAt': '2026-09-20T00:00:00+00:00'} for key in ['first', 'second']]
            (root/'config/enrichment_sources.json').write_text(json.dumps({'merchants': [], 'directMenus': [], 'promotions': promos}))
            output = root/'data/enrichment.json'
            output.write_text(json.dumps({'sources': {source: {'textHash': 'verified-hash'}}, 'promotions': [{**p, 'verifiedAt': p['reviewedAt'], 'needsReview': False} for p in promos]}))
            with patch('collect_enrichment.ROOT', root), patch('sys.argv', ['collector', '--output', str(output)]), patch('collect_enrichment.fetch', return_value=(None, 'http_403')), patch('collect_enrichment.time.sleep'), contextlib.redirect_stdout(io.StringIO()):
                main()
            result = json.loads(output.read_text())
            self.assertTrue(all(p['verifiedAt'] == p['reviewedAt'] for p in result['promotions']))
            self.assertEqual(result['sources'][source]['textHash'], 'verified-hash')

    def test_network_timeout_is_bounded_and_does_not_crash_collection(self):
        with tempfile.TemporaryDirectory() as directory, patch('collect_enrichment.urlopen', side_effect=socket.timeout()), patch('collect_enrichment.time.sleep') as sleep:
            self.assertEqual(fetch('https://example.com', Path(directory), 12), (None, 'network_error'))
            self.assertEqual(sleep.call_count, 1)

    def test_http_blocks_are_not_retried(self):
        with tempfile.TemporaryDirectory() as directory, patch('collect_enrichment.urlopen', side_effect=HTTPError('https://example.com', 403, 'Forbidden', {}, None)) as request:
            self.assertEqual(fetch('https://example.com', Path(directory), 12), (None, 'http_403'))
            self.assertEqual(request.call_count, 1)

    def test_rating_is_one_aggregate_not_header_total(self):
        body = '<script type="application/ld+json">{"@type":"Restaurant","aggregateRating":{"ratingValue":4.4,"ratingCount":50,"bestRating":5}}</script><script>{"numRatings":3383}</script>'
        rating = rating_for(body, 'https://www.doordash.com/store/23391251/')
        self.assertEqual((rating['average'], rating['count']), (4.4, 50))
        self.assertEqual(rating['provider'], 'DoorDash')
    def test_invalid_scales_and_missing_count_are_not_published(self):
        for aggregate in ['{"ratingValue":9,"ratingCount":5,"bestRating":10}', '{"ratingValue":4.4}', '{"ratingValue":6,"ratingCount":50}']:
            self.assertIsNone(rating_for('<script type="application/ld+json">{"@type":"Restaurant","aggregateRating":'+aggregate+'}</script>', 'https://example.com'))
    def test_wix_scope_currency_photo_and_unconfigured_price(self):
        body = '<h3 data-hook="menu-section__title">Starters</h3><div data-hook="dish-item__root"><p data-hook="dish-item__title">Garlic Bread</p><p data-hook="dish-item__description">Add cheese +$1</p><p data-hook="dish-item__price">CA$4.95</p><img src="https://static.wixstatic.com/media/a.jpg/v1/fill/w_300/a.jpg" data-hook="dish-item__image"></div><div data-hook="dish-item__root"><p data-hook="dish-item__title">Options</p><p data-hook="dish-item__price">CA$0.00</p></div>'
        menu = wix_menu(body)
        self.assertEqual(len(menu), 2)
        self.assertEqual(menu[0]['amountCents'], 495)
        self.assertEqual(menu[0]['section'], 'Starters')
        self.assertEqual(menu[0]['imageUrl'], 'https://static.wixstatic.com/media/a.jpg')
        self.assertEqual(menu[0]['fulfillmentMode'], 'pickup')
        self.assertIsNone(menu[1]['amountCents'])
        self.assertEqual(menu[1]['imageUrl'], '')

if __name__ == '__main__': unittest.main()
