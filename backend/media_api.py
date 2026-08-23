from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import http.cookiejar
import json
import mimetypes
import re
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from backend.cookies import load_cookies, ytdlp_cookiefile
from backend.douk_adapter import fetch_douyin_detail
from backend.paths import DOUK_VENDOR

router = APIRouter()

_CACHE_TTL = 120.0
_cache: dict[str, tuple[Any, float]] = {}
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
_download_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
_DOWNLOAD_JOB_TTL = 60 * 60
_download_jobs: dict[str, dict[str, Any]] = {}
_download_jobs_lock = threading.Lock()

try:
    import yt_dlp  # noqa: F401
except Exception:
    yt_dlp = None


def _cache_get(key: str):
    v = _cache.get(key)
    if v and (time.time() - v[1]) < _CACHE_TTL:
        return v[0]
    if v:
        _cache.pop(key, None)
    return None


def _cache_put(key: str, val):
    _cache[key] = (val, time.time())


def _pick_url(obj: Any) -> str:
    if isinstance(obj, dict):
        return _pick_url(obj.get("url_list") or obj.get("url") or "")
    if isinstance(obj, list) and obj:
        return _pick_url(obj[-1])
    if isinstance(obj, str):
        return obj
    return ""


def _attachment_filename(requested: str | None, media: str, target: str) -> str:
    safe_name = re.sub(r"[^0-9A-Za-z._-]+", "-", requested or "").strip(".-")[:96]
    media_type = media.split(";", 1)[0].strip().lower()
    known_extensions = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/avif": ".avif",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/aac": ".aac",
        "audio/x-m4a": ".m4a",
    }
    extension = known_extensions.get(media_type) or mimetypes.guess_extension(media_type) or Path(urllib.parse.urlparse(target).path).suffix
    if not re.fullmatch(r"\.[0-9A-Za-z]{1,8}", extension or ""):
        extension = ".mp4"
    if safe_name:
        return safe_name if re.search(r"\.[0-9A-Za-z]{1,8}$", safe_name) else safe_name + extension
    return ("image" if media_type.startswith("image/") else "video") + extension


def _build_gallery_archive(image_urls: list[str], filename_prefix: str = "image") -> tuple[Path, Path]:
    filename_prefix = re.sub(r"[^0-9A-Za-z_-]+", "-", filename_prefix).strip("-")[:24] or "image"
    directory = Path(tempfile.mkdtemp(prefix="x-download-gallery-"))
    archive = directory / f"{filename_prefix}-images.zip"
    request_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    try:
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
            for index, image_url in enumerate(image_urls[:50], start=1):
                request = urllib.request.Request(image_url, headers={**request_headers, "Referer": image_url})
                with urllib.request.urlopen(request, timeout=60) as response:
                    filename = _attachment_filename(
                        f"{filename_prefix}-image-{index:02d}",
                        response.headers.get("content-type", "image/jpeg"),
                        image_url,
                    )
                    with bundle.open(filename, "w") as output:
                        shutil.copyfileobj(response, output, length=128 * 1024)
        return archive, directory
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise


def _extract_aweme_id(url: str) -> str:
    m = re.search(r"(?:video|share/video)/(\d{19})", url)
    if m:
        return m.group(1)
    m = re.search(r"/(\d{19})", url)
    if m:
        return m.group(1)
    digits = re.findall(r"\d{19}", url)
    return digits[0] if digits else ""


def _extract_tiktok_id(url: str) -> str:
    m = re.search(r"/video/(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/(\d{19,})", url)
    if m:
        return m.group(1)
    digits = re.findall(r"\d{19,}", url)
    return digits[0] if digits else ""


_DOUYIN_DOMAINS = re.compile(r"(douyin\.com|iesdouyin\.com|v\.douyin\.com)", re.IGNORECASE)
_TIKTOK_DOMAINS = re.compile(r"(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)", re.IGNORECASE)
_KUAISHOU_DOMAINS = re.compile(
    r"(kuaishou\.com|gifshow\.com|kwai\.com)",
    re.IGNORECASE,
)
_YOUTUBE_DOMAINS = re.compile(r"(youtube\.com|youtu\.be)", re.IGNORECASE)
_X_DOMAINS = re.compile(r"(^|\.)(x\.com|twitter\.com)$", re.IGNORECASE)
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_YOUTUBE_COOKIE_HELP = (
    "请配置 COOKIE，教程可查看 README.md 或 yt-dlp Wiki："
    "https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies"
)


def _is_douyin(url: str) -> bool:
    return bool(_DOUYIN_DOMAINS.search(url))


def _is_douyin_source(url: str) -> bool:
    hostname = (urllib.parse.urlparse(_extract_url(url)).hostname or "").lower().rstrip(".")
    return hostname in {"douyin.com", "iesdouyin.com"} or hostname.endswith((".douyin.com", ".iesdouyin.com"))


def _is_tiktok(url: str) -> bool:
    return bool(_TIKTOK_DOMAINS.search(url))


def _is_kuaishou(url: str) -> bool:
    return bool(_KUAISHOU_DOMAINS.search(url))


def _is_x_source(url: str) -> bool:
    hostname = (urllib.parse.urlparse(_extract_url(url)).hostname or "").lower().rstrip(".")
    return bool(_X_DOMAINS.search(hostname))


def _normalize_x_status_url(url: str) -> str:
    source = _extract_url(url)
    parsed = urllib.parse.urlparse(source)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not _X_DOMAINS.search(hostname):
        return source
    match = re.match(r"^/([^/]+)/status/(\d{2,20})(?:/(?:photo|video)/\d+)?/?$", parsed.path, re.IGNORECASE)
    if not match:
        return source
    username, status_id = match.groups()
    return f"https://x.com/{username}/status/{status_id}/"


def _extract_x_status_id(url: str) -> str:
    match = re.search(r"/(?:status|statuses)/(\d{2,20})(?:/|$)", urllib.parse.urlparse(_normalize_x_status_url(url)).path)
    return match.group(1) if match else ""


def _friendly_error(url: str, error: Exception | str) -> str:
    message = _ANSI_ESCAPE.sub("", str(error)).strip()
    youtube_cookie_error = any(
        marker in message.lower()
        for marker in (
            "sign in to confirm you’re not a bot",
            "sign in to confirm you're not a bot",
            "use --cookies-from-browser or --cookies",
            "login_required",
        )
    )
    if _YOUTUBE_DOMAINS.search(url) and youtube_cookie_error:
        return _YOUTUBE_COOKIE_HELP
    return message


def _media_headers(*sources: Any) -> dict[str, str]:
    allowed = {"referer", "user-agent", "origin"}
    merged: dict[str, str] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            if key.lower() in allowed and isinstance(value, str) and "\r" not in value and "\n" not in value:
                merged[key.title()] = value
    return merged


def _extract_url(text: str) -> str:
    match = re.search(r"https?://[^\s]+", text)
    return match.group(0).rstrip("，。！？,.;!?)）]") if match else text.strip()


def _resolve_douyin_url(url: str) -> str:
    request = urllib.request.Request(
        _extract_url(url),
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.geturl()


def _map_douk_detail(url: str, data: dict) -> dict:
    author = data.get("author") or {}
    if not isinstance(author, dict):
        author = {}
    stats = data.get("statistics") or {}
    if not isinstance(stats, dict):
        stats = {}
    video = data.get("video") or {}
    if not isinstance(video, dict):
        video = {}
    music = data.get("music") or {}
    if not isinstance(music, dict):
        music = {}
    duration_ms = video.get("duration") or data.get("duration") or 0

    formats: list[dict[str, Any]] = []
    for bitrate in video.get("bit_rate") or []:
        if not isinstance(bitrate, dict):
            continue
        play = bitrate.get("play_addr") or {}
        media_url = _pick_url(play)
        if media_url:
            bit_rate = bitrate.get("bit_rate") or 0
            file_size = play.get("data_size") or bitrate.get("data_size")
            estimated_size = None
            if not file_size and isinstance(bit_rate, (int, float)) and isinstance(duration_ms, (int, float)):
                estimated_size = round(bit_rate * duration_ms / 8000)
            formats.append(
                {
                    "url": media_url,
                    "quality": bitrate.get("gear_name") or bitrate.get("quality_type") or "",
                    "width": play.get("width"),
                    "height": play.get("height"),
                    "fps": bitrate.get("FPS"),
                    "tbr": bit_rate,
                    "filesize": file_size,
                    "filesize_approx": estimated_size,
                }
            )
    formats.sort(
        key=lambda item: (
            max(item.get("width") or 0, item.get("height") or 0),
            item.get("tbr") or 0,
        ),
        reverse=True,
    )
    video_url = (formats[0]["url"] if formats else "") or _pick_url(video.get("play_addr"))

    image_urls = [
        image_url
        for image in data.get("images") or []
        if isinstance(image, dict) and (image_url := _pick_url(image))
    ]
    audio_url = _pick_url(music.get("play_url"))
    if video_url and not formats:
        formats = [{"url": video_url, "quality": "default"}]
    if not video_url:
        formats = [{"url": image_url, "quality": "image"} for image_url in image_urls]

    share_info = data.get("share_info") or {}
    if not isinstance(share_info, dict):
        share_info = {}
    description = data.get("desc") or share_info.get("share_title") or ""
    thumb = _pick_url(video.get("dynamic_cover")) or _pick_url(video.get("cover"))
    avatar = (
        _pick_url(author.get("avatar_larger"))
        or _pick_url(author.get("avatar_medium"))
        or _pick_url(author.get("avatar_thumb"))
        or _pick_url(author.get("avatar_300x300"))
        or _pick_url(author.get("avatar_168x168"))
        or author.get("avatar_url")
        or ""
    )
    author_share = author.get("share_info") or {}
    if not isinstance(author_share, dict):
        author_share = {}
    sec_uid = author.get("sec_uid") or ""
    profile_url = author_share.get("share_url") or (
        f"https://www.douyin.com/user/{urllib.parse.quote(str(sec_uid), safe='')}"
        if sec_uid
        else ""
    )
    duration = duration_ms
    if isinstance(duration, (int, float)) and duration > 1000:
        duration /= 1000
    return {
        "title": description,
        "desc": description,
        "thumbnail": thumb,
        "duration": duration,
        "uploader": author.get("nickname") or "",
        "unique_id": author.get("unique_id") or author.get("short_id") or "",
        "uid": author.get("uid") or "",
        "sec_uid": sec_uid,
        "avatar": avatar,
        "author_signature": author.get("signature") or author_share.get("share_desc") or "",
        "profile_url": profile_url,
        "platform": "Douyin",
        "play_count": stats.get("play_count"),
        "digg_count": stats.get("digg_count"),
        "comment_count": stats.get("comment_count"),
        "collect_count": stats.get("collect_count"),
        "share_count": stats.get("share_count"),
        "url": video_url or (image_urls[0] if image_urls else ""),
        "source": url,
        "type": "image" if image_urls else "video",
        "images": image_urls,
        "audio_url": audio_url,
        "audio_title": music.get("title") or music.get("author") or "图集背景音乐",
        "video_data": video,
        "fallbackUrl": video_url,
        "formats": formats,
    }


async def _douk_parse(url: str) -> dict:
    detail_id = _extract_aweme_id(url)
    resolved_url = url
    if not detail_id:
        loop = asyncio.get_running_loop()
        resolved_url = await loop.run_in_executor(_executor, _resolve_douyin_url, url)
        detail_id = _extract_aweme_id(resolved_url)
    if not detail_id:
        raise RuntimeError("无法从抖音链接提取作品 ID")
    cookie = load_cookies().get("douyin_cookie") or ""
    data = await fetch_douyin_detail(detail_id, cookie)
    return _map_douk_detail(resolved_url, data)


def _tikwm_extract(url: str) -> dict:
    api_url = f"https://www.tikwm.com/api/?url={urllib.parse.quote(url, safe='')}"
    req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != 0 or not data.get("data"):
        raise Exception(data.get("msg") or "tikwm 返回错误")
    d = data["data"]
    author = d.get("author") if isinstance(d.get("author"), dict) else {}
    unique_id = author.get("unique_id") or ""
    tiktok_formats = []
    for key, quality, size_key in (
        ("hdplay", "高清无水印", "hd_size"),
        ("play", "无水印", "size"),
        ("wmplay", "带水印", "wm_size"),
    ):
        if media_url := d.get(key):
            tiktok_formats.append({"url": media_url, "quality": quality, "filesize": d.get(size_key)})
    return {
        "title": d.get("title") or "",
        "desc": d.get("title") or "",
        "thumbnail": d.get("cover") or d.get("origin_cover") or "",
        "duration": d.get("duration") or 0,
        "uploader": author.get("nickname") or "",
        "unique_id": unique_id,
        "uid": author.get("uid") or author.get("id") or "",
        "avatar": _pick_url(author.get("avatar")) or _pick_url(author.get("avatar_thumb")),
        "author_signature": author.get("signature") or author.get("bio") or "",
        "profile_url": f"https://www.tiktok.com/@{urllib.parse.quote(str(unique_id), safe='')}" if unique_id else "",
        "platform": "TikTok",
        "play_count": d.get("play_count"),
        "digg_count": d.get("digg_count"),
        "comment_count": d.get("comment_count"),
        "collect_count": d.get("collect_count"),
        "share_count": d.get("share_count"),
        "url": d.get("hdplay") or d.get("play") or "",
        "source": url,
        "formats": tiktok_formats,
    }


_KUAISHOU_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
)


def _kuaishou_photo_state(value: Any) -> dict:
    if isinstance(value, dict):
        photo = value.get("photo")
        if isinstance(photo, dict) and photo:
            return photo
        for child in value.values():
            if result := _kuaishou_photo_state(child):
                return result
    elif isinstance(value, list):
        for child in value:
            if result := _kuaishou_photo_state(child):
                return result
    return {}


def _kuaishou_extract(url: str) -> dict:
    source = _extract_url(url)
    photo_id_match = re.search(
        r"/(?:short-video|fw/photo)/([0-9A-Za-z_-]+)",
        urllib.parse.urlparse(source).path,
        re.IGNORECASE,
    )
    request_url = (
        f"https://www.kuaishou.com/short-video/{photo_id_match.group(1)}"
        if photo_id_match
        else source
    )
    request = urllib.request.Request(
        request_url,
        headers={
            "User-Agent": _KUAISHOU_MOBILE_UA,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.kuaishou.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        page = response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")
        resolved_url = response.geturl()

    state_match = re.search(
        r"window\.INIT_STATE\s*=\s*(\{.*?\})\s*;?\s*</script>",
        page,
        re.DOTALL | re.IGNORECASE,
    )
    if not state_match:
        raise RuntimeError("快手页面未返回作品数据，请确认链接可访问后重试")
    try:
        state = json.loads(state_match.group(1))
    except json.JSONDecodeError as error:
        raise RuntimeError("快手作品数据格式发生变化，请稍后重试") from error
    photo = _kuaishou_photo_state(state)
    if not photo:
        raise RuntimeError("未在快手页面中找到作品信息，作品可能已删除或不可见")

    request_headers = {
        "Referer": "https://www.kuaishou.com/",
        "User-Agent": _KUAISHOU_MOBILE_UA,
    }
    formats: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    adaptation_sets = (photo.get("manifest") or {}).get("adaptationSet") or []
    for adaptation in adaptation_sets:
        if not isinstance(adaptation, dict):
            continue
        for index, representation in enumerate(adaptation.get("representation") or []):
            if not isinstance(representation, dict):
                continue
            media_url = representation.get("url") or _pick_url(representation.get("backupUrl"))
            if not media_url or media_url in seen_urls:
                continue
            seen_urls.add(media_url)
            format_id = str(
                representation.get("id")
                or representation.get("qualityType")
                or len(formats) + index + 1
            )
            formats.append(
                {
                    "url": media_url,
                    "format_id": f"ks-{format_id}",
                    "quality": representation.get("qualityLabel")
                    or representation.get("qualityType")
                    or "",
                    "ext": "mp4",
                    "width": representation.get("width") or photo.get("width"),
                    "height": representation.get("height") or photo.get("height"),
                    "fps": representation.get("frameRate"),
                    "vcodec": representation.get("videoCodec") or "h264",
                    "acodec": "aac",
                    "tbr": representation.get("avgBitrate"),
                    "filesize": representation.get("fileSize"),
                    "http_headers": request_headers,
                }
            )

    if not formats:
        for item in photo.get("mainMvUrls") or []:
            media_url = _pick_url(item)
            if not media_url or media_url in seen_urls:
                continue
            seen_urls.add(media_url)
            formats.append(
                {
                    "url": media_url,
                    "format_id": f"ks-{len(formats) + 1}",
                    "quality": "原始画质",
                    "ext": "mp4",
                    "width": photo.get("width"),
                    "height": photo.get("height"),
                    "fps": (photo.get("ext_params") or {}).get("interval"),
                    "vcodec": "h264",
                    "acodec": "aac",
                    "http_headers": request_headers,
                }
            )
    formats.sort(
        key=lambda item: (
            max(item.get("width") or 0, item.get("height") or 0),
            item.get("filesize") or 0,
            item.get("tbr") or 0,
        ),
        reverse=True,
    )
    video_url = formats[0]["url"] if formats else ""
    if not video_url:
        raise RuntimeError("已找到快手作品信息，但没有可用的视频地址")

    duration = photo.get("duration") or 0
    if isinstance(duration, (int, float)) and duration > 1000:
        duration /= 1000
    user_eid = str(photo.get("userEid") or "")
    return {
        "title": photo.get("caption") or "快手作品",
        "desc": photo.get("caption") or "",
        "thumbnail": _pick_url(photo.get("coverUrls"))
        or _pick_url(photo.get("webpCoverUrls")),
        "duration": duration,
        "uploader": photo.get("userName") or "",
        "unique_id": user_eid,
        "uid": str(photo.get("userId") or ""),
        "avatar": photo.get("headUrl") or _pick_url(photo.get("headUrls")),
        "author_signature": "",
        "profile_url": (
            f"https://www.kuaishou.com/profile/{urllib.parse.quote(user_eid, safe='')}"
            if user_eid
            else ""
        ),
        "platform": "Kuaishou",
        "play_count": photo.get("viewCount"),
        "digg_count": photo.get("likeCount"),
        "comment_count": photo.get("commentCount"),
        "collect_count": None,
        "share_count": photo.get("shareCount") or photo.get("forwardCount"),
        "url": video_url,
        "http_headers": request_headers,
        "source": resolved_url or source,
        "type": "video",
        "images": [],
        "formats": formats,
    }


def _temporary_douyin_cookiefile() -> Path | None:
    raw_cookie = load_cookies().get("douyin_cookie") or ""
    if not raw_cookie:
        return None

    # Browser Cookie headers are often less strict than SimpleCookie accepts.
    # Parse each name=value pair independently so one unusual value does not
    # invalidate the entire cookie header.
    parsed: dict[str, str] = {}
    cookie_name = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
    for part in raw_cookie.replace("\r", "").replace("\n", "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and cookie_name.fullmatch(name):
            parsed[name] = value.strip().strip('"')
    if not parsed:
        return None

    handle = tempfile.NamedTemporaryFile(prefix="x-download-douyin-", suffix=".txt", delete=False)
    handle.close()
    path = Path(handle.name)
    jar = http.cookiejar.MozillaCookieJar(str(path))
    for name, value in parsed.items():
        jar.set_cookie(
            http.cookiejar.Cookie(
                version=0,
                name=name,
                value=value,
                port=None,
                port_specified=False,
                domain=".douyin.com",
                domain_specified=True,
                domain_initial_dot=True,
                path="/",
                path_specified=True,
                secure=True,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            )
        )
    jar.save(ignore_discard=True, ignore_expires=True)
    return path


def _fxtwitter_extract(url: str) -> dict:
    source = _normalize_x_status_url(url)
    status_id = _extract_x_status_id(source)
    if not status_id:
        raise RuntimeError("无法从 X/Twitter 链接提取状态 ID")
    request = urllib.request.Request(
        f"https://api.fxtwitter.com/2/status/{status_id}",
        headers={"User-Agent": "x-download/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    status = payload.get("status") or {}
    if payload.get("code") != 200 or not isinstance(status, dict) or not status.get("id"):
        raise RuntimeError(payload.get("message") or "X/Twitter 作品不可用")
    author = status.get("author") or {}
    if not isinstance(author, dict):
        author = {}
    media = status.get("media") or {}
    if not isinstance(media, dict):
        media = {}

    images: list[str] = []
    for photo in media.get("photos") or []:
        photo_url = photo.get("url") if isinstance(photo, dict) else ""
        if photo_url and photo_url not in images:
            images.append(photo_url)

    formats: list[dict[str, Any]] = []
    for video_index, video in enumerate(media.get("videos") or [], start=1):
        if not isinstance(video, dict):
            continue
        candidates = video.get("formats") or [{"url": video.get("url")}]
        for format_index, item in enumerate(candidates, start=1):
            if not isinstance(item, dict) or not item.get("url"):
                continue
            formats.append(
                {
                    "url": item["url"],
                    "format_id": f"fx-{video_index}-{format_index}",
                    "quality": item.get("height") or video.get("height") or "原始画质",
                    "ext": item.get("container") or "mp4",
                    "width": item.get("width") or video.get("width"),
                    "height": item.get("height") or video.get("height"),
                    "vcodec": item.get("codec") or "h264",
                    "acodec": "aac",
                    "tbr": item.get("bitrate"),
                    "filesize": item.get("size") or video.get("filesize"),
                }
            )
    formats.sort(key=lambda item: (item.get("height") or 0, item.get("tbr") or 0), reverse=True)
    video_url = formats[0]["url"] if formats else ""
    if not images and not video_url:
        raise RuntimeError("该 X/Twitter 作品没有可下载的媒体")
    screen_name = author.get("screen_name") or ""
    first_video = next((item for item in media.get("videos") or [] if isinstance(item, dict)), {})
    return {
        "title": status.get("text") or "X/Twitter 作品",
        "desc": status.get("text") or "",
        "thumbnail": images[0] if images else _pick_url(first_video.get("thumbnail_url")),
        "duration": first_video.get("duration") or 0,
        "uploader": author.get("name") or screen_name,
        "unique_id": screen_name,
        "uid": str(author.get("id") or ""),
        "avatar": author.get("avatar_url") or "",
        "author_signature": author.get("description") or "",
        "profile_url": author.get("url") or (f"https://x.com/{screen_name}" if screen_name else ""),
        "platform": "Twitter",
        "play_count": status.get("views"),
        "digg_count": status.get("likes"),
        "comment_count": status.get("replies"),
        "collect_count": status.get("bookmarks"),
        "share_count": status.get("reposts"),
        "url": video_url or images[0],
        "source": source,
        "type": "image" if images and not video_url else "video",
        "images": images,
        "audio_url": "",
        "audio_title": "",
        "formats": formats,
    }


def _ytdlp_extract(url: str) -> dict:
    url = _normalize_x_status_url(url)
    if yt_dlp is None:
        raise Exception("yt-dlp 未安装，请重新运行一键启动脚本")
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "nocolor": True,
        "skip_download": True,
        "socket_timeout": 30,
        "nocheckcertificate": True,
    }
    temporary_cookiefile = None
    cookiefile = ytdlp_cookiefile()
    if not cookiefile and _is_douyin(url):
        temporary_cookiefile = _temporary_douyin_cookiefile()
        cookiefile = str(temporary_cookiefile) if temporary_cookiefile else None
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    finally:
        if temporary_cookiefile:
            with contextlib.suppress(OSError):
                temporary_cookiefile.unlink()
    if not info:
        return {}
    formats = info.get("formats") or []
    best_url = info.get("url") or ""
    selected_format = next((f for f in formats if f.get("url") == best_url), {})
    if not best_url and formats:
        video_formats = [f for f in formats if f.get("vcodec") != "none" and f.get("url")]
        if video_formats:
            selected_format = max(video_formats, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
            best_url = selected_format.get("url", "")
        elif formats:
            selected_format = formats[-1]
            best_url = selected_format.get("url", "")
    common_headers = _media_headers(info.get("http_headers"))
    selected_headers = _media_headers(common_headers, selected_format.get("http_headers"))
    return {
        "title": info.get("title") or info.get("fulltitle") or "",
        "desc": info.get("description") or "",
        "thumbnail": info.get("thumbnail") or "",
        "duration": info.get("duration") or 0,
        "uploader": info.get("uploader") or info.get("creator") or "",
        "unique_id": info.get("uploader_id") or "",
        "uid": info.get("channel_id") or info.get("uploader_id") or "",
        "avatar": info.get("uploader_avatar") or "",
        "author_signature": info.get("channel_follower_count_text") or "",
        "profile_url": info.get("uploader_url") or info.get("channel_url") or "",
        "platform": info.get("extractor") or info.get("extractor_key") or "",
        "play_count": info.get("view_count"),
        "digg_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "collect_count": (
            info.get("favourite_count")
            if info.get("favourite_count") is not None
            else info.get("favorite_count")
        ),
        "share_count": (
            info.get("share_count")
            if info.get("share_count") is not None
            else info.get("repost_count")
        ),
        "url": best_url,
        "http_headers": selected_headers,
        "source": url,
        "formats": [
            {
                "url": f.get("url", ""),
                "format_id": str(f.get("format_id") or ""),
                "quality": f.get("format_note") or f.get("format_id") or "",
                "ext": f.get("ext") or "",
                "width": f.get("width"),
                "height": f.get("height"),
                "fps": f.get("fps"),
                "vcodec": f.get("vcodec"),
                "acodec": f.get("acodec"),
                "tbr": f.get("tbr"),
                "filesize": f.get("filesize"),
                "filesize_approx": f.get("filesize_approx"),
                "http_headers": _media_headers(common_headers, f.get("http_headers")),
            }
            for f in formats
            if f.get("url")
        ],
    }


async def _parse_url(url: str) -> dict:
    url = _normalize_x_status_url(url)
    if _is_douyin(url):
        try:
            return await _douk_parse(url)
        except Exception as douk_error:
            try:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(_executor, _ytdlp_extract, url)
            except Exception as ytdlp_error:
                raise RuntimeError(
                    f"DouK-Downloader 解析失败：{douk_error}；"
                    f"yt-dlp 兜底失败：{ytdlp_error}"
                ) from douk_error
    if _is_tiktok(url):
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(_executor, _tikwm_extract, url)
        except Exception:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(_executor, _ytdlp_extract, url)
    if _is_kuaishou(url):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _kuaishou_extract, url)
    if _is_x_source(url):
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(_executor, _fxtwitter_extract, url)
        except Exception:
            return await loop.run_in_executor(_executor, _ytdlp_extract, url)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _ytdlp_extract, url)


@router.get("/api/health", include_in_schema=False)
async def health_check():
    cookies = load_cookies()
    return {
        "ok": True,
        "yt_dlp": yt_dlp is not None,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "douk_downloader": DOUK_VENDOR.exists(),
        "douyin_cookie": bool(cookies.get("douyin_cookie")),
        "tiktok_cookie": bool(cookies.get("tiktok_cookie")),
        "ytdlp_cookies_file": bool(ytdlp_cookiefile()),
    }


@router.post("/api/parse", include_in_schema=False)
@router.post("/api/info", include_in_schema=False)
async def parse_media(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)

    url = _normalize_x_status_url((body.get("url") or "").strip())
    if not url:
        return JSONResponse({"success": False, "error": "url is required"}, status_code=400)

    cache_key = "parse:" + url
    cached = _cache_get(cache_key)
    if cached is not None:
        return JSONResponse(cached)

    try:
        data = await _parse_url(url)
    except Exception as e:
        hint = _friendly_error(url, e)
        status_code = 502
        if _YOUTUBE_DOMAINS.search(url) and hint == _YOUTUBE_COOKIE_HELP:
            status_code = 422
        elif _is_douyin(url):
            if not load_cookies().get("douyin_cookie"):
                hint = "尚未配置抖音 Cookie，请运行 start.bat --reconfigure 后重新填写"
                status_code = 422
            elif "Fresh cookies" in hint:
                hint = (
                    "当前抖音 Cookie 已过期或未被抖音接受。请关闭服务，运行 "
                    "start.bat --reconfigure，并粘贴刚从 douyin.com 网络请求中复制的完整 Cookie"
                )
                status_code = 422
        return JSONResponse({"success": False, "error": hint}, status_code=status_code)

    if not data or not (data.get("url") or data.get("images")):
        return JSONResponse({"success": False, "error": "未找到可播放的视频地址"}, status_code=400)

    result = {"success": True, "data": data}
    _cache_put(cache_key, result)
    return JSONResponse(result)


@router.post("/api/tkinfo", include_in_schema=False)
async def parse_tiktok_legacy(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)
    url = (body.get("url") or "").strip()
    if not url:
        return JSONResponse({"success": False, "error": "url is required"}, status_code=400)
    if not _extract_tiktok_id(url) and not _is_tiktok(url):
        return JSONResponse({"success": False, "error": "无法提取 TikTok 视频ID"}, status_code=400)
    try:
        data = await _parse_url(url)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"TikTok 解析失败: {_friendly_error(url, e)}"}, status_code=500)
    if not data or not data.get("url"):
        return JSONResponse({"success": False, "error": "未找到视频播放地址"}, status_code=400)
    return JSONResponse({"success": True, "data": data})


@router.post("/api/ytdlp", include_in_schema=False)
async def parse_with_ytdlp(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)
    url = _normalize_x_status_url((body.get("url") or "").strip())
    if not url:
        return JSONResponse({"success": False, "error": "url is required"}, status_code=400)
    if _is_douyin(url):
        return JSONResponse({"success": False, "error": "抖音链接请使用 /api/info"}, status_code=400)
    try:
        loop = asyncio.get_event_loop()
        extractor = _fxtwitter_extract if _is_x_source(url) else _ytdlp_extract
        data = await loop.run_in_executor(_executor, extractor, url)
    except Exception as e:
        return JSONResponse({"success": False, "error": _friendly_error(url, e)}, status_code=422)
    if not data or not data.get("url"):
        return JSONResponse({"success": False, "error": "未找到可播放的视频地址"}, status_code=400)
    return JSONResponse({"success": True, "data": data})


@router.post("/api/download", include_in_schema=False)
async def download_media(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    url = _normalize_x_status_url((body.get("url") or "").strip())
    if not url:
        return JSONResponse({"error": "url is required"}, status_code=400)
    try:
        data = await _parse_url(url)
    except Exception as e:
        return JSONResponse({"error": _friendly_error(url, e)}, status_code=502)
    video_url = data.get("url") or ""
    if not video_url:
        return JSONResponse({"error": "未找到可下载视频地址"}, status_code=400)
    selected_format = next(
        (item for item in data.get("formats") or [] if item.get("url") == video_url),
        {},
    )
    if selected_format.get("format_id") and selected_format.get("acodec") == "none":
        return await _prepare_ytdlp_download(url, selected_format["format_id"], merge_audio=True)
    headers = data.get("http_headers") or {}
    return await _proxy_stream(
        video_url,
        download=True,
        referer=headers.get("Referer"),
        user_agent=headers.get("User-Agent"),
        origin=headers.get("Origin"),
    )


@router.get("/api/ytdlp-download", include_in_schema=False)
async def download_ytdlp_format(
    url: str = "",
    format_id: str = "",
    merge_audio: int = 0,
):
    source = url.strip()
    selected_format = format_id.strip()
    if not source.startswith("http://") and not source.startswith("https://"):
        return JSONResponse({"error": "unsupported url"}, status_code=400)
    if not selected_format or not re.fullmatch(r"[0-9A-Za-z_.-]+", selected_format):
        return JSONResponse({"error": "invalid format_id"}, status_code=400)
    return await _prepare_ytdlp_download(source, selected_format, merge_audio=bool(merge_audio))


@router.get("/api/gallery-download", include_in_schema=False)
async def download_gallery(source: str = ""):
    source = _normalize_x_status_url(_extract_url(source))
    if not source or not (_is_douyin_source(source) or _is_x_source(source)):
        return JSONResponse({"error": "仅支持打包抖音或 X/Twitter 图集"}, status_code=400)
    try:
        detail = await _parse_url(source)
        image_urls = [item for item in detail.get("images") or [] if isinstance(item, str) and item.startswith("http")]
        if not image_urls:
            return JSONResponse({"error": "该作品没有可下载的图片"}, status_code=404)
        loop = asyncio.get_running_loop()
        filename_prefix = "x" if _is_x_source(source) else "douyin"
        archive, directory = await loop.run_in_executor(_executor, _build_gallery_archive, image_urls, filename_prefix)
        return FileResponse(
            archive,
            media_type="application/zip",
            filename=f"{filename_prefix}-images.zip",
            background=BackgroundTask(shutil.rmtree, directory, ignore_errors=True),
        )
    except Exception as error:
        return JSONResponse({"error": f"图集打包失败：{_friendly_error(source, error)}"}, status_code=502)


@router.get("/api/stream", include_in_schema=False)
@router.head("/api/stream", include_in_schema=False)
async def stream_media(
    request: Request,
    url: Optional[str] = None,
    download: int = 0,
    filename: Optional[str] = None,
    referer: Optional[str] = None,
    user_agent: Optional[str] = None,
    origin: Optional[str] = None,
):
    target = (url or request.query_params.get("url") or "").strip()
    if not target:
        return JSONResponse({"error": "url is required"}, status_code=400)
    if not target.startswith("http://") and not target.startswith("https://"):
        return JSONResponse({"error": "unsupported url"}, status_code=400)
    return await _proxy_stream(
        target,
        download=bool(download),
        filename=filename,
        referer=referer,
        user_agent=user_agent,
        origin=origin,
        byte_range=request.headers.get("range"),
    )


async def _proxy_stream(
    target: str,
    download: bool = False,
    filename: str | None = None,
    referer: str | None = None,
    user_agent: str | None = None,
    origin: str | None = None,
    byte_range: str | None = None,
):
    safe_headers = _media_headers(
        {
            "Referer": referer or target,
            "User-Agent": user_agent
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Origin": origin or "",
        }
    )
    headers = {
        "User-Agent": safe_headers["User-Agent"],
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Referer": safe_headers["Referer"],
    }
    if safe_headers.get("Origin"):
        headers["Origin"] = safe_headers["Origin"]
    if byte_range and re.fullmatch(r"bytes=\d*-\d*", byte_range.strip(), re.IGNORECASE):
        headers["Range"] = byte_range.strip()

    def _open():
        req = urllib.request.Request(target, headers=headers, method="GET")
        return urllib.request.urlopen(req, timeout=60)

    try:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(_executor, _open)
    except urllib.error.HTTPError as e:
        try:
            payload = e.read()
        except Exception:
            payload = b""
        return Response(status_code=e.code, content=payload, media_type="text/plain")
    except Exception as e:
        return JSONResponse({"error": f"stream proxy error: {e}"}, status_code=502)

    media = resp.headers.get("content-type", "video/mp4")
    out_headers = {}
    for k in (
        "Content-Disposition",
        "Cache-Control",
        "Accept-Ranges",
        "Content-Range",
        "Content-Length",
    ):
        v = resp.headers.get(k)
        if v:
            out_headers[k] = v
    if download:
        requested_name = _attachment_filename(filename, media, target)
        out_headers["Content-Disposition"] = f'attachment; filename="{requested_name}"'

    def iter_chunks():
        try:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            resp.close()

    return StreamingResponse(
        iter_chunks(),
        status_code=getattr(resp, "status", 200),
        media_type=media,
        headers=out_headers,
    )


def _download_ytdlp_file(
    source: str,
    format_id: str,
    merge_audio: bool,
    directory: Path,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> Path:
    if yt_dlp is None:
        raise RuntimeError("yt-dlp 未安装，请重新运行一键启动脚本")
    if merge_audio and not shutil.which("ffmpeg"):
        raise RuntimeError("该清晰度需要合并音频，请先安装 ffmpeg")
    selector = f"{format_id}+bestaudio/{format_id}" if merge_audio else format_id
    completed_tracks = 0

    def progress_hook(status: dict[str, Any]) -> None:
        nonlocal completed_tracks
        if progress_callback is None:
            return
        state = status.get("status")
        if state == "downloading":
            downloaded = int(status.get("downloaded_bytes") or 0)
            total = int(status.get("total_bytes") or status.get("total_bytes_estimate") or 0)
            ratio = min(downloaded / total, 1.0) if total else 0.0
            if merge_audio:
                if completed_tracks == 0:
                    percent = ratio * 70
                    phase = "正在下载视频轨"
                else:
                    percent = 70 + ratio * 20
                    phase = "正在下载音频轨"
            else:
                percent = ratio * 95
                phase = "正在下载视频"
            progress_callback(
                {
                    "status": "downloading",
                    "phase": phase,
                    "percent": round(percent, 1),
                    "downloaded_bytes": downloaded,
                    "total_bytes": total,
                    "speed": status.get("speed"),
                    "eta": status.get("eta"),
                }
            )
        elif state == "finished":
            completed_tracks += 1
            progress_callback(
                {
                    "status": "merging" if merge_audio and completed_tracks >= 2 else "downloading",
                    "phase": "正在合并音频与视频" if merge_audio and completed_tracks >= 2 else "正在准备音频轨",
                    "percent": 94 if merge_audio and completed_tracks >= 2 else 70,
                    "speed": None,
                    "eta": None,
                }
            )

    def postprocessor_hook(status: dict[str, Any]) -> None:
        if progress_callback is None or not merge_audio:
            return
        if status.get("status") in {"started", "processing"}:
            progress_callback(
                {
                    "status": "merging",
                    "phase": "正在合并音频与视频",
                    "percent": 96,
                    "speed": None,
                    "eta": None,
                }
            )

    options = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "nocolor": True,
        "format": selector,
        "outtmpl": str(directory / "%(title).120B [%(id)s].%(ext)s"),
        "merge_output_format": "mp4",
        "socket_timeout": 30,
        "nocheckcertificate": True,
        "windowsfilenames": True,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [postprocessor_hook],
    }
    if cookiefile := ytdlp_cookiefile():
        options["cookiefile"] = cookiefile
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.extract_info(source, download=True)
    files = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() not in {".part", ".ytdl", ".temp"}
    ]
    if not files:
        raise RuntimeError("yt-dlp 下载完成但未找到输出文件")
    return max(files, key=lambda path: path.stat().st_size)


async def _prepare_ytdlp_download(
    source: str,
    format_id: str,
    merge_audio: bool,
):
    directory = Path(tempfile.mkdtemp(prefix="x-download-ytdlp-"))
    try:
        loop = asyncio.get_running_loop()
        output = await loop.run_in_executor(
            _executor,
            _download_ytdlp_file,
            source,
            format_id,
            merge_audio,
            directory,
        )
    except Exception as error:
        shutil.rmtree(directory, ignore_errors=True)
        return JSONResponse(
            {"error": _friendly_error(source, error)},
            status_code=502,
        )
    media_type = mimetypes.guess_type(output.name)[0] or "application/octet-stream"
    return FileResponse(
        output,
        media_type=media_type,
        filename=output.name,
        background=BackgroundTask(shutil.rmtree, directory, ignore_errors=True),
    )


def _update_download_job(job_id: str, **changes: Any) -> None:
    with _download_jobs_lock:
        job = _download_jobs.get(job_id)
        if not job:
            return
        job.update(changes)
        job["updated_at"] = time.time()


def _public_download_job(job_id: str) -> dict[str, Any] | None:
    with _download_jobs_lock:
        job = _download_jobs.get(job_id)
        if not job:
            return None
        return {
            "job_id": job_id,
            "status": job.get("status"),
            "phase": job.get("phase"),
            "percent": job.get("percent", 0),
            "downloaded_bytes": job.get("downloaded_bytes", 0),
            "total_bytes": job.get("total_bytes", 0),
            "speed": job.get("speed"),
            "eta": job.get("eta"),
            "filename": job.get("filename") or "",
            "error": job.get("error") or "",
            "download_url": f"/api/download-jobs/{job_id}/file"
            if job.get("status") == "ready"
            else "",
        }


def _remove_download_job(job_id: str) -> None:
    with _download_jobs_lock:
        job = _download_jobs.pop(job_id, None)
    if job and job.get("directory"):
        shutil.rmtree(job["directory"], ignore_errors=True)


def _cleanup_download_jobs() -> None:
    cutoff = time.time() - _DOWNLOAD_JOB_TTL
    with _download_jobs_lock:
        expired = [
            job_id
            for job_id, job in _download_jobs.items()
            if job.get("status") in {"ready", "error"}
            and job.get("updated_at", 0) < cutoff
        ]
    for job_id in expired:
        _remove_download_job(job_id)


def _run_download_job(job_id: str) -> None:
    with _download_jobs_lock:
        job = _download_jobs.get(job_id)
        if not job:
            return
        source = job["source"]
        format_id = job["format_id"]
        merge_audio = job["merge_audio"]
        directory = Path(job["directory"])
    _update_download_job(
        job_id,
        status="downloading",
        phase="正在连接媒体服务器",
        percent=1,
    )
    try:
        output = _download_ytdlp_file(
            source,
            format_id,
            merge_audio,
            directory,
            lambda progress: _update_download_job(job_id, **progress),
        )
        size = output.stat().st_size
        _update_download_job(
            job_id,
            status="ready",
            phase="处理完成，正在开始下载",
            percent=100,
            downloaded_bytes=size,
            total_bytes=size,
            speed=None,
            eta=0,
            output=str(output),
            filename=output.name,
        )
    except Exception as error:
        shutil.rmtree(directory, ignore_errors=True)
        _update_download_job(
            job_id,
            status="error",
            phase="下载处理失败",
            error=_friendly_error(source, error),
            speed=None,
            eta=None,
        )


@router.post("/api/download-jobs", include_in_schema=False)
async def create_download_job(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    source = str(body.get("url") or "").strip()
    format_id = str(body.get("format_id") or "").strip()
    merge_audio = bool(body.get("merge_audio", True))
    if not source.startswith(("http://", "https://")):
        return JSONResponse({"error": "unsupported url"}, status_code=400)
    if not format_id or not re.fullmatch(r"[0-9A-Za-z_.-]+", format_id):
        return JSONResponse({"error": "invalid format_id"}, status_code=400)

    _cleanup_download_jobs()
    with _download_jobs_lock:
        active_jobs = sum(
            job.get("status") in {"queued", "downloading", "merging"}
            for job in _download_jobs.values()
        )
    if active_jobs >= 4:
        return JSONResponse(
            {"error": "当前下载任务较多，请等待已有任务完成后重试"},
            status_code=429,
        )
    job_id = uuid.uuid4().hex
    directory = Path(tempfile.mkdtemp(prefix="x-download-job-"))
    now = time.time()
    with _download_jobs_lock:
        _download_jobs[job_id] = {
            "source": source,
            "format_id": format_id,
            "merge_audio": merge_audio,
            "directory": str(directory),
            "status": "queued",
            "phase": "正在排队",
            "percent": 0,
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "speed": None,
            "eta": None,
            "created_at": now,
            "updated_at": now,
        }
    _download_executor.submit(_run_download_job, job_id)
    return JSONResponse(_public_download_job(job_id), status_code=202)


@router.get("/api/download-jobs/{job_id}", include_in_schema=False)
async def get_download_job(job_id: str):
    _cleanup_download_jobs()
    job = _public_download_job(job_id)
    if not job:
        return JSONResponse({"error": "download job not found"}, status_code=404)
    return JSONResponse(job)


@router.get("/api/download-jobs/{job_id}/file", include_in_schema=False)
async def get_download_job_file(job_id: str):
    with _download_jobs_lock:
        job = _download_jobs.get(job_id)
        status = job.get("status") if job else None
        output = Path(job["output"]) if job and job.get("output") else None
    if not job:
        return JSONResponse({"error": "download job not found"}, status_code=404)
    if status != "ready" or not output or not output.is_file():
        return JSONResponse({"error": "download is not ready"}, status_code=409)
    media_type = mimetypes.guess_type(output.name)[0] or "application/octet-stream"
    return FileResponse(
        output,
        media_type=media_type,
        filename=output.name,
        background=BackgroundTask(_remove_download_job, job_id),
    )
