from __future__ import annotations

import json
import time
import urllib.parse
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


def _browser_cookie_entries(value: str, default_domain: str = ".x.com") -> list[dict[str, Any]]:
    value = (value or "").strip()
    if not value:
        return []
    if value[0] not in "[{":
        if value.lower().startswith("cookie:"):
            value = value.split(":", 1)[1].strip()
        entries: list[dict[str, Any]] = []
        for part in value.replace("\r", "").replace("\n", "").split(";"):
            name, separator, cookie_value = part.strip().partition("=")
            if separator and name:
                entries.append({"domain": default_domain, "name": name, "value": cookie_value})
        return entries

    try:
        exported = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cookie JSON 格式错误：第 {exc.lineno} 行第 {exc.colno} 列") from exc
    if isinstance(exported, dict):
        exported = exported.get("cookies")
    if not isinstance(exported, list):
        raise ValueError("Cookie JSON 必须是数组，或包含 cookies 数组的对象")
    return [item for item in exported if isinstance(item, dict)]


def _is_x_cookie_domain(domain: str) -> bool:
    host = domain.removeprefix("#HttpOnly_").lstrip(".").lower()
    return host == "x.com" or host.endswith(".x.com") or host == "twitter.com" or host.endswith(".twitter.com")


def _is_youtube_cookie_domain(domain: str) -> bool:
    host = domain.removeprefix("#HttpOnly_").lstrip(".").lower()
    return host == "youtube.com" or host.endswith(".youtube.com")


def _is_bilibili_cookie_domain(domain: str) -> bool:
    host = domain.removeprefix("#HttpOnly_").lstrip(".").lower()
    return host == "bilibili.com" or host.endswith(".bilibili.com")


def save_x_cookies(value: str, path: Path = YTDLP_COOKIES) -> int:
    """Merge an X browser JSON/header export into a Netscape yt-dlp cookie jar."""
    entries = _browser_cookie_entries(value)
    output: list[str] = []
    for item in entries:
        domain = str(item.get("domain") or ".x.com").strip()
        name = str(item.get("name") or "").strip()
        cookie_value = str(item.get("value") or "")
        if not _is_x_cookie_domain(domain):
            continue
        if not name or any(char in name for char in "=;\t\r\n"):
            continue
        if any(char in cookie_value for char in "\t\r\n"):
            continue
        host_only = bool(item.get("hostOnly", False))
        domain = domain.lstrip(".") if host_only else f".{domain.lstrip('.')}"
        include_subdomains = "FALSE" if host_only else "TRUE"
        secure = "TRUE" if bool(item.get("secure", True)) else "FALSE"
        try:
            expires = max(0, int(float(item.get("expirationDate") or 0)))
        except (TypeError, ValueError):
            expires = 0
        netscape_domain = f"#HttpOnly_{domain}" if bool(item.get("httpOnly")) else domain
        output.append(
            "\t".join(
                (netscape_domain, include_subdomains, str(item.get("path") or "/"), secure, str(expires), name, cookie_value)
            )
        )
    if not output:
        raise ValueError("没有找到有效的 x.com / twitter.com Cookie")

    preserved: list[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) >= 7 and _is_x_cookie_domain(fields[0]):
                continue
            if line.strip() not in {"# Netscape HTTP Cookie File", "# HTTP Cookie File"}:
                preserved.append(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "# Netscape HTTP Cookie File\n"
    if preserved:
        text += "\n".join(preserved).strip("\n") + "\n"
    text += "\n".join(output) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return len(output)


def save_youtube_cookies(value: str, path: Path = YTDLP_COOKIES) -> int:
    """Merge a Cookie-Editor YouTube JSON/header export into a Netscape yt-dlp cookie jar."""
    entries = _browser_cookie_entries(value, default_domain=".youtube.com")
    output: list[str] = []
    for item in entries:
        domain = str(item.get("domain") or ".youtube.com").strip()
        name = str(item.get("name") or "").strip()
        cookie_value = str(item.get("value") or "")
        if not _is_youtube_cookie_domain(domain):
            continue
        if not name or any(char in name for char in "=;\t\r\n"):
            continue
        if any(char in cookie_value for char in "\t\r\n"):
            continue
        host_only = bool(item.get("hostOnly", False))
        domain = domain.lstrip(".") if host_only else f".{domain.lstrip('.')}"
        include_subdomains = "FALSE" if host_only else "TRUE"
        secure = "TRUE" if bool(item.get("secure", True)) else "FALSE"
        try:
            expires = max(0, int(float(item.get("expirationDate") or 0)))
        except (TypeError, ValueError):
            expires = 0
        netscape_domain = f"#HttpOnly_{domain}" if bool(item.get("httpOnly")) else domain
        output.append("\t".join((netscape_domain, include_subdomains, str(item.get("path") or "/"), secure, str(expires), name, cookie_value)))
    if not output:
        raise ValueError("没有找到有效的 youtube.com Cookie")
    preserved: list[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) >= 7 and _is_youtube_cookie_domain(fields[0]):
                continue
            if line.strip() not in {"# Netscape HTTP Cookie File", "# HTTP Cookie File"}:
                preserved.append(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "# Netscape HTTP Cookie File\n"
    if preserved:
        text += "\n".join(preserved).strip("\n") + "\n"
    text += "\n".join(output) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return len(output)


def save_bilibili_cookies(value: str, path: Path = YTDLP_COOKIES) -> int:
    """Merge a Cookie-Editor Bilibili JSON/header export into the yt-dlp cookie jar."""
    entries = _browser_cookie_entries(value, default_domain=".bilibili.com")
    output: list[str] = []
    for item in entries:
        domain = str(item.get("domain") or ".bilibili.com").strip()
        name = str(item.get("name") or "").strip()
        cookie_value = str(item.get("value") or "")
        if not _is_bilibili_cookie_domain(domain):
            continue
        if not name or any(char in name for char in "=;\t\r\n"):
            continue
        if any(char in cookie_value for char in "\t\r\n"):
            continue
        host_only = bool(item.get("hostOnly", False))
        domain = domain.lstrip(".") if host_only else f".{domain.lstrip('.')}"
        include_subdomains = "FALSE" if host_only else "TRUE"
        secure = "TRUE" if bool(item.get("secure", True)) else "FALSE"
        try:
            expires = max(0, int(float(item.get("expirationDate") or 0)))
        except (TypeError, ValueError):
            expires = 0
        netscape_domain = f"#HttpOnly_{domain}" if bool(item.get("httpOnly")) else domain
        output.append("\t".join((netscape_domain, include_subdomains, str(item.get("path") or "/"), secure, str(expires), name, cookie_value)))
    if not output:
        raise ValueError("没有找到有效的 bilibili.com Cookie")
    preserved: list[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) >= 7 and _is_bilibili_cookie_domain(fields[0]):
                continue
            if line.strip() not in {"# Netscape HTTP Cookie File", "# HTTP Cookie File"}:
                preserved.append(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "# Netscape HTTP Cookie File\n"
    if preserved:
        text += "\n".join(preserved).strip("\n") + "\n"
    text += "\n".join(output) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return len(output)


def cookie_header_for_url(url: str, path: Path | None = None) -> str:
    """Return only the cookies applicable to a URL from the shared Netscape jar."""
    cookie_path = path or (Path(ytdlp_cookiefile()) if ytdlp_cookiefile() else None)
    if not cookie_path or not cookie_path.exists():
        return ""
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    request_path = parsed.path or "/"
    pairs: list[str] = []
    try:
        lines = cookie_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        fields = line.split("\t")
        if len(fields) < 7:
            continue
        domain, include_subdomains, cookie_path_value, secure, expires, name, value = fields[:7]
        cookie_domain = domain.removeprefix("#HttpOnly_").lstrip(".").lower()
        domain_matches = hostname == cookie_domain or (include_subdomains.upper() == "TRUE" and hostname.endswith("." + cookie_domain))
        if not domain_matches or not request_path.startswith(cookie_path_value or "/"):
            continue
        if secure.upper() == "TRUE" and parsed.scheme != "https":
            continue
        try:
            expires_at = int(float(expires or 0))
        except ValueError:
            expires_at = 0
        if expires_at and expires_at < int(time.time()):
            continue
        if name:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


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
