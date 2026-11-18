import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from woolworths_scraper import _iter_products, LINKS


class DynamicListingTests(unittest.TestCase):
    def driver(self,duplicate=False):
        class Driver:
            current_url='page1'
            title='Eggs'
            collection_warnings=[]
            def find_elements(self,by,selector):
                if selector==LINKS:return [object()]
                return [NS(get_attribute=lambda key:'page2')] if self.current_url=='page1' else []
            def find_element(self,*args):
                return NS(text='1 to 1 of 3 products' if self.current_url=='page1' else '2 to 2 of 2 products')
            def execute_script(self,*args):
                sku='1' if self.current_url=='page1' or duplicate else '2'
                return [dict(name='Eggs 12 Pack',url=f'https://www.woolworths.co.nz/shop/product-details/{sku}/eggs',
                             hero_price='$5.00',non_member_price='',cup_price='$0.42 / 1ea',
                             non_member_cup_price='',member_offer=False,was_price='',displayed_text='Eggs $5.00')]
        return Driver()

    def test_total_change_and_final_discrepancy_are_nonblocking(self):
        driver=self.driver()
        # Change final total to three: the stable rendered two products still save.
        driver.find_element=lambda *args:NS(text='1 to 2 of 3 products')
        def navigate(browser,url):browser.current_url=url
        with patch('woolworths_scraper.open_page',side_effect=navigate), \
             patch('woolworths_scraper.require_store'),patch('woolworths_scraper.check_access'):
            records=list(_iter_products(driver,'page1','Store',timeout=2))
        self.assertEqual([r['source_product_id'] for r in records],['1','2'])
        self.assertTrue(driver.collection_warnings)

    def test_repeated_page_is_still_a_failure(self):
        driver=self.driver(duplicate=True)
        def navigate(browser,url):browser.current_url=url
        with patch('woolworths_scraper.open_page',side_effect=navigate), \
             patch('woolworths_scraper.require_store'),patch('woolworths_scraper.check_access'):
            with self.assertRaisesRegex(RuntimeError,'Repeated product page'):
                list(_iter_products(driver,'page1','Store',timeout=2))
