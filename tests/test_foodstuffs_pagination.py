import unittest
from foodstuffs_scraper import ListingCounts, page_bounds, read_page


class FoodstuffsPaginationTests(unittest.TestCase):
    def test_listing_observer_accepts_different_daily_totals(self):
        pages=ListingCounts()
        pages.add((1,2,4),2)
        pages.add((3,4,4),2)
        self.assertFalse(pages.warnings)
        other=ListingCounts();other.add((1,3,3),3)
        self.assertFalse(other.warnings)

    def test_count_discrepancies_are_observed_without_blocking(self):
        for bounds,count in [((1,50,153),49),((51,100,153),50)]:
            with self.subTest(bounds=bounds):
                pages=ListingCounts();pages.add(bounds,count)
                self.assertTrue(pages.warnings)

    def test_total_can_change_during_pagination(self):
        pages=ListingCounts();pages.add((1,50,153),50)
        pages.add((51,100,152),50)
        self.assertIn('Displayed total changed during pagination',pages.warnings)

    def test_page_without_count_can_be_read(self):
        pages=ListingCounts();pages.add(None,50)
        self.assertIsNone(pages.total)
        self.assertEqual(page_bounds('Showing 1,001 - 1,050 of 1,053 products'),(1001,1050,1053))

    def test_waits_for_full_grid_before_reading(self):
        class Body:
            text='Showing 1 - 2 of 2 products'
        class Driver:
            title='Deli Meats'
            calls=0
            def find_element(self,*args):return Body()
            def execute_script(self,*args):
                self.calls+=1
                row={'source_product_id':'a','original_name':'A','product_url':'https://example.com/a'}
                return [row] if self.calls==1 else [row,dict(row,source_product_id='b')]
        driver=Driver()
        self.assertEqual(len(read_page(driver,timeout=2)),2)
        self.assertEqual(driver.calls,3)

    def test_stable_cards_do_not_need_to_equal_displayed_total(self):
        class Body:
            text='Showing 1 - 50 of 153 products'
        class Driver:
            title='Deli Meats'
            def find_element(self,*args):return Body()
            def execute_script(self,*args):
                return [{'source_product_id':str(i),'original_name':'Product','product_url':'https://example.com/'+str(i)} for i in range(49)]
        self.assertEqual(len(read_page(Driver(),timeout=2)),49)
