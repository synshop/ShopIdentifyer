import os
import unittest
import requests
import json

SWIPE_URL = "https://localhost/swipe/"
MEMBER_URL = "https://localhost/member/"

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

    def test_missing_liability_wavier(self):
        # The user's liability waiver is missing
        r = requests.get(MEMBER_URL + "/3BE0092/files/liability-waiver.pdf", verify=False)
        assert "No Waiver on file, please fix this!" == r.text

    def test_missing_vetted_membership_form(self):
        # The user's vetted membership form is missing
        r = requests.get(MEMBER_URL + "/3BE0092/files/vetted-membership-form.pdf", verify=False)
        assert "No signed vetted membership form on file, please fix this!" == r.text

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(IdentityTests)
    unittest.TextTestRunner(verbosity=2).run(suite)
    #unittest.main()
