import unittest
from access_guard import AccessDeniedError, check_access, is_denied
from recover_run import recovery_scope


class RunRecoveryTests(unittest.TestCase):
    def test_saved_denial_response(self):
        self.assertTrue(is_denied('', 'Access Denied\nYou don\'t have permission to access this server.'))
        self.assertTrue(is_denied('Access Denied', ''))
        self.assertFalse(is_denied('Milk', '0 products'))
        self.assertFalse(is_denied('Shop', 'Product description mentions access denied'))

    def test_denial_raises_instead_of_retrying(self):
        class Driver:
            title='Access Denied'
            def execute_script(self, script):return 'Access Denied'
        with self.assertRaises(AccessDeniedError):check_access(Driver())

    def test_legacy_partial_run_keeps_full_expected_scope(self):
        locations=[{'source':'woolworths','store_id':str(i),'is_christchurch_urban':True} for i in range(3)]
        state={'mode':'production','expected_stores':3,'results':[{'status':'uploaded'}]}
        self.assertEqual(recovery_scope(state,locations),locations)

    def test_ambiguous_legacy_scope_rejected(self):
        with self.assertRaises(ValueError):
            recovery_scope({'mode':'production','expected_stores':2,'results':[{'status':'uploaded'}]},[])

    def test_unuploaded_partial_files_not_recovered(self):
        with self.assertRaises(ValueError):
            recovery_scope({'mode':'production','results':[{'status':'failed','rows':159}]},[])


if __name__=='__main__':unittest.main()
