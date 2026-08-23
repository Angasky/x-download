from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOUK_VENDOR = ROOT / "vendor" / "TikTokDownloader"
WEB = ROOT / "web"
CONFIG_DIR = ROOT / "config"
COOKIES_FILE = CONFIG_DIR / "cookies.yaml"
COOKIES_EXAMPLE = CONFIG_DIR / "cookies.example.yaml"
APP_CONFIG = CONFIG_DIR / "app.yaml"
VENV_DIR = ROOT / ".venv"
YTDLP_COOKIES = CONFIG_DIR / "ytdlp_cookies.txt"
