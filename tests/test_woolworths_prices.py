import unittest
from woolworths_scraper import parse_product,cup

class WoolworthsPrices(unittest.TestCase):
    def raw(self,**changes):
        row=dict(name='Woolworths Eggs Barn Mixed Grade 20 Pack',url='https://www.woolworths.co.nz/shop/product-details/422870/woolworths-eggs',hero_price='$13.90',non_member_price='Non-member price $15.69',cup_price='$0.70 / 1ea',non_member_cup_price='$0.78 / 1ea',member_offer=True,was_price='',displayed_text='Member price $13.90; Non-member price $15.69')
        row.update(changes);return row
    def test_member_offer_preserves_public_price_and_corresponding_unit(self):
        row=parse_product(self.raw())
        self.assertEqual(row['total_price'],'15.69')
        self.assertEqual(row['member_price'],'13.90')
        self.assertEqual(row['unit_price'],'0.78')
        self.assertEqual(row['member_unit_price'],'0.70')
        self.assertEqual(row['total_quant'],'20pk')
        self.assertEqual(row['source_product_id'],'422870')
    def test_missing_public_price_never_falls_back_to_member_price(self):
        row=parse_product(self.raw(non_member_price='',non_member_cup_price=''))
        self.assertIsNone(row['total_price'])
        self.assertIsNone(row['unit_price'])
        self.assertEqual(row['price_status'],'public_price_missing')
    def test_standard_discount_and_was_price(self):
        row=parse_product(self.raw(member_offer=False,hero_price='$7.40',non_member_price='',cup_price='$0.62 / 1ea',was_price='Was $9.99'))
        self.assertEqual(row['total_price'],'7.40')
        self.assertIsNone(row['member_price'])
        self.assertEqual(row['was_price'],'9.99')
        self.assertEqual(row['is_promo'],1)
    def test_cup_denominator_keeps_hundred_grams(self):
        self.assertEqual(cup('$1.53 / 100g'),('1.53','100g'))
    def test_pack_size_does_not_capture_egg_grade(self):
        row=parse_product(self.raw(name='Henergy Eggs Cage Free Size 7 18 Pack'))
        self.assertEqual(row['total_quant'],'18pk')
    def test_missing_product_identity_stops_parsing(self):
        with self.assertRaises(ValueError):parse_product(self.raw(url='https://www.woolworths.co.nz/'))

if __name__=='__main__':unittest.main()
