import base64
import json
import unittest
from doordash_promotions import extract

class PromotionTests(unittest.TestCase):
    def page(self, dashpass=False, store='123', review=False):
        item={'__typename':'Review' if review else 'StorePageCarouselItem','id':'dish1','name':'Test dish','nextCursor':base64.b64encode(json.dumps({'storeLiteData':{'storeId':store}}).encode()).decode(),'badges':[{'badge':{'type':'bogo_offer','isDashpass':dashpass}}]}
        return '<script>self.__next_f.push('+json.dumps([1,'50:'+json.dumps(item)])+')</script>'
    def test_exact_branch_badge(self):
        self.assertEqual(extract(self.page(),'123'),[{'id':'dish1','name':'Test dish'}])
    def test_wrong_branch_subscription_and_reviews_excluded(self):
        for page in [self.page(store='456'),self.page(dashpass=True),self.page(review=True)]:
            self.assertEqual(extract(page,'123'),[])
    def test_invalid_page_is_empty(self):
        self.assertEqual(extract('Access denied','123'),[])

if __name__=='__main__':unittest.main()
