import unittest
from unittest.mock import Mock, patch

import net_safety
import notion_sync as notion


def resolves_to(mapping):
    def getaddrinfo(host, port):
        if host not in mapping:
            raise OSError("no such host")
        return [(2, 1, 6, "", (ip, 0)) for ip in mapping[host]]
    return getaddrinfo


class HostTests(unittest.TestCase):
    def test_host_is_requires_a_dot_boundary(self):
        self.assertTrue(net_safety.host_is("boards.greenhouse.io", "greenhouse.io"))
        self.assertTrue(net_safety.host_is("GREENHOUSE.IO.", "greenhouse.io"))
        self.assertFalse(net_safety.host_is("evilgreenhouse.io", "greenhouse.io"))
        self.assertFalse(net_safety.host_is(None, "greenhouse.io"))

    def test_lookalike_host_is_not_treated_as_an_ats(self):
        with patch.object(notion, "_json") as api:
            self.assertIsNone(notion._ats_api("https://evilgreenhouse.io/acme/jobs/1"))
        api.assert_not_called()


class PublicUrlTests(unittest.TestCase):
    DNS = {"jobs.example": ["93.184.216.34"], "internal.example": ["10.0.0.5"],
           "mixed.example": ["93.184.216.34", "127.0.0.1"], "meta.example": ["169.254.169.254"],
           "cgnat.example": ["100.64.0.1"], "v6.example": ["::1"]}

    def check(self, url):
        with patch.object(net_safety.socket, "getaddrinfo", resolves_to(self.DNS)):
            return net_safety.is_public_url(url)

    def test_allows_only_public_http_urls(self):
        self.assertTrue(self.check("https://jobs.example/p/1"))
        for url in ("ftp://jobs.example/", "file:///etc/passwd", "javascript:alert(1)", "https:///x",
                    "http://127.0.0.1/", "http://localhost/", "http://internal.example/",
                    "http://mixed.example/", "http://meta.example/latest", "http://cgnat.example/",
                    "http://v6.example/", "http://unknown.example/"):
            with self.subTest(url=url):
                self.assertFalse(self.check(url), url)


class SafeGetTests(unittest.TestCase):
    def response(self, status=200, location=None, body=b"<title>Hi</title>"):
        r = Mock(status_code=status, headers={"Location": location} if location else {},
                 encoding="utf-8", is_redirect=bool(location))
        r.iter_content.return_value = [body]
        return r

    def run_get(self, *responses):
        with patch.object(net_safety.socket, "getaddrinfo", resolves_to(PublicUrlTests.DNS)), \
             patch.object(net_safety.requests, "get", side_effect=list(responses)) as get:
            return net_safety.safe_get_text("https://jobs.example/start"), get

    def test_returns_status_and_text(self):
        result, _ = self.run_get(self.response())
        self.assertEqual(result, (200, "<title>Hi</title>"))

    def test_follows_public_redirects_but_not_private_ones(self):
        result, get = self.run_get(self.response(302, "/next"), self.response())
        self.assertEqual(result[0], 200)
        self.assertEqual(get.call_args.args[0], "https://jobs.example/next")
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
        result, get = self.run_get(self.response(302, "http://internal.example/admin"))
        self.assertIsNone(result)
        self.assertEqual(get.call_count, 1)

    def test_redirect_loop_gives_up(self):
        result, get = self.run_get(*[self.response(302, "/again")] * 10)
        self.assertIsNone(result)
        self.assertEqual(get.call_count, net_safety.MAX_REDIRECTS + 1)

    def test_body_is_capped(self):
        big = Mock(status_code=200, headers={}, encoding="utf-8", is_redirect=False)
        big.iter_content.return_value = iter([b"a" * 600_000] * 100)
        result, _ = self.run_get(big)
        self.assertEqual(len(result[1]), net_safety.MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
