import unittest
from unittest.mock import patch
from selenium.common.exceptions import TimeoutException
from woolworths_scraper import public_price_ready, read_priced_cards


def raw(**changes):
    row=dict(name='Milk 1L',url='https://www.woolworths.co.nz/shop/product-details/123/milk',
             hero_price='',non_member_price='',member_offer=False,displayed_text='Milk 1L\nAdd to cart')
    row.update(changes)
    return row


class PriceLoadingTests(unittest.TestCase):
    def test_stable_names_without_prices_are_not_ready(self):
        class Driver:
            calls=0
            def execute_script(self,*args):
                self.calls+=1
                return [raw()] if self.calls<=2 else [raw(hero_price='$3.99')]
        driver=Driver()
        with patch('woolworths_scraper.check_access'):
            rows=read_priced_cards(driver,timeout=3)
        self.assertEqual(rows[0]['hero_price'],'$3.99')
        self.assertEqual(driver.calls,4)

    def test_member_only_price_is_not_a_public_price(self):
        self.assertFalse(public_price_ready(raw(member_offer=True,hero_price='$2.99')))
        self.assertTrue(public_price_ready(raw(member_offer=True,hero_price='$2.99',non_member_price='$3.99')))

    def test_savings_text_is_never_used_as_sale_price(self):
        self.assertFalse(public_price_ready(raw(displayed_text='SAVE $0.89\nMilk 1L\nAdd to cart')))

    def test_explicit_unavailable_item_is_not_infinite_loading(self):
        self.assertTrue(public_price_ready(raw(displayed_text='Milk 1L\nOut of stock')))

    def test_permanently_unpriced_active_cards_time_out(self):
        class Driver:
            def execute_script(self,*args):return [raw()]
        with patch('woolworths_scraper.check_access'):
            with self.assertRaises(TimeoutException):read_priced_cards(Driver(),timeout=0.01)
