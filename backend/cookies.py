from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.paths import CONFIG_DIR, COOKIES_EXAMPLE, COOKIES_FILE, YTDLP_COOKIES

try:
    import yaml
except ImportError:  # bootstrap 早期可能尚未安装
    yaml = None


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if yaml:
        data = yaml.safe_load(text) or {}
        return data if isinstance(data, dict) else {}
    # 极简回退：只读顶层 key: value
    out: dict[str, Any] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_cookies() -> dict[str, str]:
    data = _load_yaml(COOKIES_FILE) if COOKIES_FILE.exists() else {}
    if not data and COOKIES_EXAMPLE.exists():
        data = _load_yaml(COOKIES_EXAMPLE)
    douyin = str(data.get("douyin_cookie") or "").strip()
    tiktok = str(data.get("tiktok_cookie") or "").strip()
    ytdlp = str(data.get("ytdlp_cookies_file") or "").strip()
    if not ytdlp and YTDLP_COOKIES.exists():
        ytdlp = str(YTDLP_COOKIES)
    return {
        "douyin_cookie": douyin,
        "tiktok_cookie": tiktok,
        "ytdlp_cookies_file": ytdlp,
    }


def save_cookies(values: dict[str, str]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    douyin = (values.get("douyin_cookie") or "").replace("\r", " ").replace("\n", " ").strip()
    tiktok = (values.get("tiktok_cookie") or "").replace("\r", " ").replace("\n", " ").strip()
    ytdlp = (values.get("ytdlp_cookies_file") or "").strip()
    COOKIES_FILE.write_text(
        (
            "# 由一键启动脚本生成，请勿提交到 git\n"
            f'douyin_cookie: "{_escape_yaml(douyin)}"\n'
            f'tiktok_cookie: "{_escape_yaml(tiktok)}"\n'
            f'ytdlp_cookies_file: "{_escape_yaml(ytdlp)}"\n'
        ),
        encoding="utf-8",
    )


def _escape_yaml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def ytdlp_cookiefile() -> str | None:
    path = load_cookies().get("ytdlp_cookies_file") or ""
    if path and Path(path).exists():
        return path
    return None
