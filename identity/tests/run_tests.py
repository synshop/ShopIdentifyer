import os
import unittest
import requests
import json

SWIPE_URL = "https://localhost/swipe/"

class IdentityTests(unittest.TestCase):

    def setUp(self):
		pass

    def tearDown(self):
		pass

    def test_good_swipe(self):
        # Normal swipe functionality
        payload = {'tag': '2A9F699', 'reader': '1'}
        r = requests.post(SWIPE_URL,data=payload,verify=False)
        response = json.loads(r.text)
        swipe_message = "SWIPE_OK"
        assert swipe_message == response["message"]

    def test_good_swipe_no_reader(self):
        # Normal swipe functionality
        payload = {'tag': '2A9F699'}
        r = requests.post(SWIPE_URL,data=payload,verify=False)
        response = json.loads(r.text)
        swipe_message = "SWIPE_OK"
        assert swipe_message == response["message"]

    def test_missing_badge_swipe(self):
        # The user's badge is not in the system
        payload = {'tag': 'XXXXXX', 'reader': '1'}
        r = requests.post(SWIPE_URL,data=payload,verify=False)
        response = json.loads(r.text)
        swipe_message = "MISSING_BADGE"
        assert swipe_message == response["message"]

    def test_missing_stripe_swipe(self):
        # The user's defined stripe email does not match with the stripe cache
        payload = {'tag': '1234', 'reader': '1'}
        r = requests.post(SWIPE_URL,data=payload,verify=False)
        response = json.loads(r.text)
        swipe_message = "MISSING_STRIPE"
        assert swipe_message == response["message"]

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(IdentityTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    #unittest.main()
