import unittest
from tools.boot_daily import shutdown_allowed


class BootPowerTests(unittest.TestCase):
    def test_shutdown_requires_confirmed_bios_and_no_signed_in_user(self):
        state={'status':'complete','dry_run':False}
        self.assertTrue(shutdown_allowed(state,True,False))
        self.assertFalse(shutdown_allowed(state,False,False))
        self.assertFalse(shutdown_allowed(state,True,True))

    def test_failures_pending_data_and_dry_runs_never_shutdown(self):
        for status in ['failed','before_schedule','starting']:
            self.assertFalse(shutdown_allowed({'status':status},True,False))
        self.assertFalse(shutdown_allowed({'status':'complete','dry_run':True},True,False))
