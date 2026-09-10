"""Offline authentication-likelihood detection tests."""
import unittest

from app.core.auth_detection import configured_auth_methods, detect_auth_requirement


class AuthDetectionTests(unittest.TestCase):
    def test_likely_private_and_account_patterns(self):
        cases = [
            "https://example.com/private/video",
            "https://example.com/members/video",
            "https://example.com/account/library",
            "https://www.instagram.com/stories/example/123/",
            "https://www.facebook.com/groups/privategroup/videos/123/",
            "https://vimeo.com/ondemand/example/123",
            "https://www.linkedin.com/learning/example",
            "https://www.patreon.com/posts/example-123",
        ]
        for url in cases:
            with self.subTest(url=url):
                result = detect_auth_requirement(url)
                self.assertEqual(result["likelihood"], "likely")
                self.assertGreaterEqual(result["score"], 65)
                self.assertTrue(result["reasons"])

    def test_public_and_extractor_capability_are_conservative(self):
        public = detect_auth_requirement("https://example.com/video")
        self.assertEqual(public["likelihood"], "unlikely")
        possible = detect_auth_requirement("https://vimeo.com/123", {"extractor": "vimeo", "supports_authentication": True})
        self.assertEqual(possible["likelihood"], "possible")
        self.assertTrue(possible["extractor_supports_auth"])

    def test_signed_url_never_exposes_values_or_claims_login(self):
        result = detect_auth_requirement("https://example.com/video?token=super-secret&expires=123")
        self.assertTrue(result["signed_access_url"])
        self.assertEqual(result["likelihood"], "unlikely")
        self.assertNotIn("super-secret", str(result))

    def test_configured_methods(self):
        preferences = {"site_login": True, "username": "me", "password": "secret",
                       "use_netrc": False, "cookies": "Cookies from Browser"}
        self.assertEqual(configured_auth_methods(preferences), ("username/password", "browser cookies"))
        result = detect_auth_requirement("https://example.com/private/video", preferences=preferences)
        self.assertTrue(result["auth_configured"])
        self.assertNotIn("secret", str(result))


if __name__ == "__main__":
    unittest.main()
