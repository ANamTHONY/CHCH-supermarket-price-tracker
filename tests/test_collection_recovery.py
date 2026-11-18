import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import browser_driver
from woolworths_scraper import iter_products


class CollectionRecovery(unittest.TestCase):
    def test_driver_initialization_is_serialized(self):
        active = 0
        peak = 0
        lock = threading.Lock()

        def initialize(**kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return object()

        with patch.object(browser_driver, '_create_driver', side_effect=initialize):
            with ThreadPoolExecutor(max_workers=3) as pool:
                results = list(pool.map(lambda _: browser_driver.create_driver(), range(3)))
        self.assertEqual(len(results), 3)
        self.assertEqual(peak, 1)

    def test_incomplete_category_does_not_emit_partial_or_duplicate_rows(self):
        def partial():
            yield {'source_product_id': 'partial'}
            raise RuntimeError('Incomplete category: 1 products collected')

        with patch('woolworths_scraper._iter_products', side_effect=[partial(), iter([{'source_product_id': 'complete'}])]):
            self.assertEqual(list(iter_products(None, 'url', 'store')), [{'source_product_id': 'complete'}])

    def test_category_retry_is_bounded(self):
        with patch('woolworths_scraper._iter_products', side_effect=RuntimeError('Incomplete category: 1 products collected')) as collect:
            with self.assertRaisesRegex(RuntimeError, 'Incomplete category'):
                list(iter_products(None, 'url', 'store'))
            self.assertEqual(collect.call_count, 2)


if __name__ == '__main__':
    unittest.main()
