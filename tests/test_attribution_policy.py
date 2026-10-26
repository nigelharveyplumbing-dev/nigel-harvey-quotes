"""Attribution policy: only explicit evidence establishes Google organic search."""
import unittest

from business.growth_tracking import inferred_source


class AttributionPolicyTests(unittest.TestCase):
    def test_unknown_google_referrer_is_not_assumed_organic(self):
        self.assertEqual(inferred_source("website", {
            "referrer": "https://www.google.co.uk"
        }), "Other")
        self.assertEqual(inferred_source("website", {
            "referrer": "https://www.google.com"
        }), "Other")

    def test_explicit_google_organic_is_recognised(self):
        self.assertEqual(inferred_source("website", {
            "utm_source": "google", "utm_medium": "organic"
        }), "Google organic search")

    def test_whatsapp_is_a_contact_channel_not_a_confirmed_lead(self):
        # A WhatsApp click has no independent proof that a message was sent.
        self.assertEqual(inferred_source("website", {}), "Website/direct")


if __name__ == "__main__":
    unittest.main()
