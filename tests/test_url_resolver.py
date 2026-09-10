"""Short URL recognition and bounded redirect resolution tests."""
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

from app.core.url_resolver import _BoundedRedirectHandler, URLResolution, expand_short_url, is_short_url


class URLResolverTests(unittest.TestCase):
    def test_known_hosts_and_lookalikes(self):
        for url in ("https://youtu.be/abc", "https://bit.ly/a", "https://t.co/a", "https://ow.ly/a", "https://goo.gl/a"):
            self.assertTrue(is_short_url(url), url)
        for url in ("https://bit.ly.example.com/a", "https://evilbit.ly/a", "https://example.com/a"):
            self.assertFalse(is_short_url(url), url)

    def test_non_short_url_needs_no_network(self):
        factory = Mock()
        result = expand_short_url("https://example.com/video", opener_factory=factory)
        self.assertEqual(result, URLResolution("https://example.com/video", "https://example.com/video", ()))
        factory.assert_not_called()

    def test_redirect_result_and_head_request(self):
        response = Mock()
        response.geturl.return_value = "https://www.youtube.com/watch?v=abc"
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        result = expand_short_url("https://youtu.be/abc", opener_factory=lambda handler: opener)
        self.assertEqual(result.final_url, "https://www.youtube.com/watch?v=abc")
        self.assertTrue(result.expanded)
        self.assertEqual(opener.open.call_args.args[0].method, "HEAD")

    def test_head_falls_back_to_bounded_get(self):
        response = Mock()
        response.geturl.return_value = "https://example.com/video"
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.side_effect = [HTTPError("https://bit.ly/a", 405, "", {}, None), response]
        result = expand_short_url("https://bit.ly/a", opener_factory=lambda handler: opener)
        self.assertEqual(result.final_url, "https://example.com/video")
        request = opener.open.call_args_list[1].args[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.get_header("Range"), "bytes=0-0")

    def test_credentials_and_limits_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "credentials"):
            expand_short_url("https://user:secret@bit.ly/a")
        with self.assertRaisesRegex(ValueError, "between 1 and 20"):
            expand_short_url("https://bit.ly/a", max_redirects=0)

    def test_redirect_loop_limit_and_private_targets(self):
        request = Mock(full_url="https://bit.ly/a", headers={})
        request.get_method.return_value = "HEAD"
        handler = _BoundedRedirectHandler("https://bit.ly/a", 1)
        handler.redirect_request(request, None, 302, "Found", {}, "https://example.com/b")
        with self.assertRaisesRegex(ValueError, "redirect loop"):
            handler.redirect_request(request, None, 302, "Found", {}, "https://bit.ly/a")
        with self.assertRaisesRegex(ValueError, "redirect limit"):
            handler.redirect_request(request, None, 302, "Found", {}, "https://example.org/c")
        for target in ("http://localhost/private", "http://127.0.0.1/private", "http://[::1]/private"):
            fresh = _BoundedRedirectHandler("https://bit.ly/a", 8)
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "local"):
                fresh.redirect_request(request, None, 302, "Found", {}, target)


if __name__ == "__main__":
    unittest.main()
