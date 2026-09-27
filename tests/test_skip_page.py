import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from skip_page import directory, menu
from catalog_service import parse_menu

class SkipTests(unittest.TestCase):
    def setUp(self):
        self.url='https://www.skipthedishes.com/example-smythe'
        self.props={'partner':{'id':'branch-1','cleanUrl':'example-smythe','name':'Example','location':'520 Smythe St','locationDetails':'Fredericton, NB, E3B 1W8, CAN','partnerType':'FULL_SERVICE'},'menuV2':{'restaurantId':'branch-1','categories':[{'name':'Drinks','menuItems':[{'id':'water','name':'Water','subtotal':375,'available':True},{'id':'options','name':'Build your meal','subtotal':0,'available':True},{'id':'gone','name':'Unavailable','subtotal':100,'available':False}]}]}}
    def body(self, props):
        return ('<script id="__NEXT_DATA__" type="application/json">'+json.dumps({'props':{'pageProps':props}})+'</script>').encode()
    def test_prices_are_cents_and_zero_options_remain_unknown(self):
        result=parse_menu(self.body(self.props),{'url':self.url},'SkipTheDishes')
        self.assertEqual(len(result['menuItems']),2)
        self.assertEqual(result['menuItems'][0]['amountCents'],375)
        self.assertEqual(result['menuItems'][0]['currency'],'CAD')
        self.assertIsNone(result['menuItems'][1]['amountCents'])
        self.assertEqual(result['menuItems'][1]['priceKind'],'options')
    def test_quick_service_restaurants_are_supported(self):
        self.props['partner']['partnerType']='QUICK_SERVICE'
        self.assertEqual(len(menu(self.body(self.props),{'url':self.url})['menuItems']),2)

    def test_wrong_branch_city_and_retail_are_rejected(self):
        for key,value in [('id','wrong'),('cleanUrl','other-branch'),('locationDetails','Moncton, NB, E1C 1W1, CAN'),('partnerType','GROCERY')]:
            props=copy.deepcopy(self.props);props['partner'][key]=value
            with self.assertRaises(ValueError):menu(self.body(props),{'url':self.url})
    def test_directory_only_follows_city_scoped_links(self):
        props={'restaurants':[{'name':'Example','cleanUrl':'example-smythe'}],'cityBrandsLinks':[{'url':'/city-brands/fredericton/kfc'},{'url':'/city-brands/toronto/kfc'},{'url':'https://other.test/'}]}
        stores,pages=directory(self.body(props),'https://www.skipthedishes.com/cities/fredericton')
        self.assertEqual(len(stores),1)
        self.assertEqual(pages,['https://www.skipthedishes.com/city-brands/fredericton/kfc'])
        self.assertEqual(directory(self.body(props),'https://www.skipthedishes.com/cities/toronto'),([],[]))

if __name__=='__main__':unittest.main()
