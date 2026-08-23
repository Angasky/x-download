from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.cookies import save_x_cookies


class BrowserCookieInputTests(unittest.TestCase):
    def test_merges_x_json_into_netscape_file(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cookies.txt"
            path.write_text(
                "# Netscape HTTP Cookie File\n"
                ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tyoutube-secret\n"
                ".x.com\tTRUE\t/\tTRUE\t0\told\told-value\n",
                encoding="utf-8",
            )
            exported = """[
              {"domain":".x.com","expirationDate":1900000000,"httpOnly":true,
               "name":"auth_token","path":"/","secure":true,"value":"new-token"},
              {"domain":".example.com","name":"ignored","value":"private"}
            ]"""
            self.assertEqual(save_x_cookies(exported, path), 1)
            content = path.read_text(encoding="utf-8")
            self.assertIn(".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tyoutube-secret", content)
            self.assertIn("#HttpOnly_.x.com\tTRUE\t/\tTRUE\t1900000000\tauth_token\tnew-token", content)
            self.assertNotIn("old-value", content)
            self.assertNotIn("private", content)

    def test_accepts_plain_x_cookie_header(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cookies.txt"
            self.assertEqual(save_x_cookies("auth_token=token; ct0=csrf", path), 2)
            content = path.read_text(encoding="utf-8")
            self.assertIn("\tauth_token\ttoken", content)
            self.assertIn("\tct0\tcsrf", content)


if __name__ == "__main__":
    unittest.main()
