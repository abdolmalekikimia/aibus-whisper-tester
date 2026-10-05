import unittest
from http.cookiejar import Cookie
from types import SimpleNamespace

from client import ApiBusClient, TRANSCRIPTIONS_PATH, extract_session_token


class CookieTokenTests(unittest.TestCase):
    def test_reads_token_from_response_cookie_jar(self):
        client = ApiBusClient("https://example.test")
        client.cookie_jar.set_cookie(
            Cookie(
                version=0,
                name="aibus_admin",
                value="session-value",
                port=None,
                port_specified=False,
                domain="example.test",
                domain_specified=False,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=True,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={"HttpOnly": None},
                rfc2109=False,
            )
        )
        self.assertEqual(client._cookie_token(), "session-value")

    def test_reads_token_from_set_cookie_header(self):
        response = SimpleNamespace(
            cookies={},
            headers={"Set-Cookie": "aibus_admin=session-value; Path=/; HttpOnly; SameSite=Lax"},
        )
        self.assertEqual(extract_session_token(response), "session-value")

    def test_returns_none_when_cookie_is_absent(self):
        response = SimpleNamespace(cookies={}, headers={})
        self.assertIsNone(extract_session_token(response))


class ClientUrlTests(unittest.TestCase):
    def test_builds_gateway_url_without_duplicate_slashes(self):
        client = ApiBusClient("https://example.test/base/", verify_tls=False)
        self.assertEqual(client.url("/api/auth/login"), "https://example.test/base/api/auth/login")


    def test_uses_requested_mock_whisper_endpoint(self):
        client = ApiBusClient("https://example.invalid")
        self.assertEqual(
            client.url(TRANSCRIPTIONS_PATH),
            "https://example.invalid/api/gateway/stt-custom-mock/v1/audio/transcriptions",
        )


if __name__ == "__main__":
    unittest.main()
