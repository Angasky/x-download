from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import backend.cookies as cookie_module
import scripts.bootstrap as bootstrap


class CookiePromptTests(unittest.TestCase):
    def test_multiline_x_json_is_saved_for_ytdlp(self) -> None:
        with TemporaryDirectory() as directory:
            config_dir = Path(directory) / "config"
            cookies_yaml = config_dir / "cookies.yaml"
            cookies_example = config_dir / "missing-example.yaml"
            ytdlp_file = config_dir / "ytdlp_cookies.txt"
            answers = iter(
                [
                    "douyin-cookie",
                    "",
                    "",
                    "[",
                    '{"domain":".x.com","httpOnly":true,"name":"auth_token",',
                    ' "secure":true,"value":"x-token"}',
                    "]",
                ]
            )
            patches = (
                patch.object(bootstrap, "CONFIG_DIR", config_dir),
                patch.object(bootstrap, "COOKIES_FILE", cookies_yaml),
                patch.object(bootstrap, "COOKIES_EXAMPLE", cookies_example),
                patch.object(bootstrap, "YTDLP_COOKIES", ytdlp_file),
                patch.object(cookie_module, "CONFIG_DIR", config_dir),
                patch.object(cookie_module, "COOKIES_FILE", cookies_yaml),
                patch.object(cookie_module, "COOKIES_EXAMPLE", cookies_example),
                patch.object(cookie_module, "YTDLP_COOKIES", ytdlp_file),
                patch("builtins.input", side_effect=lambda *_: next(answers)),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
                bootstrap.prompt_cookies(reconfigure=True)

            self.assertTrue(cookies_yaml.exists())
            content = ytdlp_file.read_text(encoding="utf-8")
            self.assertIn("# Netscape HTTP Cookie File", content)
            self.assertIn("\tauth_token\tx-token", content)


if __name__ == "__main__":
    unittest.main()
