from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
import re
import os
import json
import urllib.request
import urllib.error
import asyncio
import concurrent.futures
import sys
import time
from typing import Optional

router = APIRouter()

# 抖音解析上游端点：需自行部署一个兼容 /douyin/share + /douyin/detail 的服务。
# 部署时通过环境变量 KR_API_BASE 注入（见 deploy.sh），不要写死在代码里。
KR_BASE = os.environ.get("KR_API_BASE", "").rstrip("/")

# ── 成功结果缓存（TTL 120s）：热门/重复链接秒回 ──
_CACHE_TTL = 120.0
_cache: dict = {}


def _cache_get(key: str):
    v = _cache.get(key)
    if v and (time.time() - v[1]) < _CACHE_TTL:
        return v[0]
    if v:
        _cache.pop(key, None)
    return None


def _cache_put(key: str, val):
    _cache[key] = (val, time.time())


# yt-dlp 顶部 import（避免每次请求重复 import，省 0.5~1s）
try:
    import yt_dlp  # noqa: F401
except Exception:
    yt_dlp = None


def _extract_aweme_id(url: str) -> str:
    m = re.search(r"(?:video|share/video)/(\d{19})", url)
    if m:
        return m.group(1)
    m = re.search(r"/(\d{19})", url)
    if m:
        return m.group(1)
    digits = re.findall(r"\d{19}", url)
    if digits:
        return digits[0]
    return ""


def _post_json(base_url: str, path: str, payload: dict, timeout: int = 30) -> dict:
    if not base_url:
        return {"_error": "KR_API_BASE 未配置：请在部署时设置环境变量 KR_API_BASE 指向你的抖音解析上游服务"}
    url = f"{base_url}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            ctype = resp.headers.get("Content-Type", "")
            if "application/json" in ctype:
                return json.loads(body)
            return {"_raw": body, "_status": resp.status}
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8", errors="replace"))
        except Exception:
            return {"_http_error": e.code, "_msg": str(e)}
    except Exception as e:
        return {"_error": str(e)}


def _resolve_share_url(url: str, timeout: int = 30):
    data = _post_json(KR_BASE, "/douyin/share", {"text": url, "proxy": ""}, timeout=timeout)
    return (data.get("url") or ""), data


@router.post("/api/info", include_in_schema=False)
async def sg_api_info(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)

    url = (body.get("url") or "").strip()
    if not url:
        return JSONResponse({"success": False, "error": "url is required"}, status_code=400)

    cached = _cache_get("douyin:" + url)
    if cached is not None:
        return JSONResponse(cached)

    # 原 URL 已含 19 位 aweme_id：跳过 share 短链解析，省一次上游往返
    pre_id = _extract_aweme_id(url)
    resolved_url, share_data = url, {}
    if not pre_id:
        try:
            resolved_url, share_data = _resolve_share_url(url, timeout=10)
        except Exception as e:
            return JSONResponse({"success": False, "error": "share请求超时或异常: " + str(e)}, status_code=504)

    detail_id = _extract_aweme_id(resolved_url) or pre_id or _extract_aweme_id(url)
    if not detail_id:
        return JSONResponse({"success": False, "error": "无法提取作品ID", "data": {"resolved_url": resolved_url, "share_data": share_data}}, status_code=400)

    try:
        detail_data = _post_json(KR_BASE, "/douyin/detail", {"detail_id": detail_id, "proxy": "", "source": False, "cookie": ""}, timeout=12)
    except Exception as e:
        return JSONResponse({"success": False, "error": "detail请求超时或异常: " + str(e)}, status_code=504)

    if detail_data.get("_error") or detail_data.get("_http_error"):
        return JSONResponse({"success": False, "error": "detail请求失败: " + str(detail_data)}, status_code=502)

    inner = detail_data.get("data") or detail_data
    if isinstance(inner, dict):
        inner.setdefault("title", inner.get("desc") or inner.get("note") or "")
        inner.setdefault("thumbnail", inner.get("dynamic_cover") or inner.get("static_cover") or "")
        inner.setdefault("uploader", inner.get("nickname") or inner.get("unique_id") or "")
        if "duration" not in inner:
            inner["duration"] = inner.get("create_time") or ""
        dl = inner.get("downloads") or inner.get("url") or ""
        if dl and not isinstance(inner.get("formats"), list):
            inner["formats"] = [{"url": dl, "quality": "default"}]
        inner.setdefault("fallbackUrl", dl)
        inner.setdefault("url", dl)
        inner.setdefault("source", resolved_url or dl)
    result = {"success": True, "data": inner}
    _cache_put("douyin:" + url, result)
    return JSONResponse(result)


@router.post("/api/download", include_in_schema=False)
async def sg_api_download(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    url = (body.get("url") or "").strip()
    if not url:
        return JSONResponse({"error": "url is required"}, status_code=400)

    detail_id = _extract_aweme_id(url)
    resolved_url = ""
    if not detail_id:
        share_data = _post_json(KR_BASE, "/douyin/share", {"text": url, "proxy": ""}, timeout=30)
        if share_data.get("_error") or share_data.get("_http_error"):
            return JSONResponse({"error": f"share请求失败: {share_data}"}, status_code=502)
        resolved_url = share_data.get("url") or ""
        if not resolved_url:
            return JSONResponse({"error": "share接口未返回可用链接"}, status_code=400)
        detail_id = _extract_aweme_id(resolved_url) or _extract_aweme_id(url)
        if not detail_id:
            return JSONResponse({"error": "无法提取作品ID"}, status_code=400)

    payload = {"detail_id": detail_id, "proxy": "", "source": False, "cookie": ""}
    detail_data = _post_json(KR_BASE, "/douyin/detail", payload, timeout=60)
    if detail_data.get("_error") or detail_data.get("_http_error"):
        return JSONResponse({"error": f"detail请求失败: {detail_data}"}, status_code=502)

    inner = detail_data.get("data") or detail_data
    if not isinstance(inner, dict):
        return JSONResponse({"error": "detail接口数据格式错误"}, status_code=502)

    video_data = inner.get("video_data") or {}
    video_url = video_data.get("nwm_video_url_HQ") or video_data.get("wm_video_url_HQ") or inner.get("url") or ""
    if not video_url:
        return JSONResponse({"error": "未找到可下载视频地址，data_keys=" + ",".join(list(inner.keys())[:20])}, status_code=400)

    try:
        req = urllib.request.Request(video_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            headers = {}
            cd = r.headers.get("Content-Disposition") or ""
            if cd:
                headers["Content-Disposition"] = cd
            return Response(content=raw, media_type=r.headers.get("content-type", "video/mp4"), headers=headers)
    except Exception as e:
        return JSONResponse({"error": f"视频资源拉取异常: {e}"}, status_code=502)


# ── TikTok 解析（tikwm.com API）────────────────────────────
def _extract_tiktok_id(url: str) -> str:
    m = re.search(r"/video/(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/(\d{19,})", url)
    if m:
        return m.group(1)
    digits = re.findall(r"\d{19,}", url)
    return digits[0] if digits else ""


def _tikwm_extract(url: str) -> dict:
    """通过 tikwm.com API 解析 TikTok 视频"""
    api_url = f"https://www.tikwm.com/api/?url={url}"
    req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    if data.get("code") != 0 or not data.get("data"):
        raise Exception(data.get("msg") or "tikwm 返回错误")

    d = data["data"]
    return {
        "title": d.get("title") or "",
        "desc": d.get("title") or "",
        "thumbnail": d.get("cover") or d.get("origin_cover") or "",
        "duration": d.get("duration") or 0,
        "uploader": d.get("author", {}).get("nickname") if isinstance(d.get("author"), dict) else "",
        "unique_id": d.get("author", {}).get("unique_id") if isinstance(d.get("author"), dict) else "",
        "platform": "TikTok",
        "play_count": d.get("play_count"),
        "digg_count": d.get("digg_count"),
        "comment_count": d.get("comment_count"),
        "collect_count": d.get("collect_count"),
        "share_count": d.get("share_count"),
        "url": d.get("play") or "",
        "source": url,
    }


@router.post("/api/tkinfo", include_in_schema=False)
async def sg_api_tkinfo(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)

    url = (body.get("url") or "").strip()
    if not url:
        return JSONResponse({"success": False, "error": "url is required"}, status_code=400)

    if not _extract_tiktok_id(url):
        return JSONResponse({"success": False, "error": "无法提取 TikTok 视频ID"}, status_code=400)

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(_executor, _tikwm_extract, url)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"TikTok 解析失败: {str(e)}"}, status_code=500)

    if not data or not data.get("url"):
        return JSONResponse({"success": False, "error": "未找到视频播放地址"}, status_code=400)

    return JSONResponse({"success": True, "data": data})


# ── yt-dlp 通用解析（抖音/TikTok 除外）──────────────────────
_DOUYIN_DOMAINS = re.compile(
    r"(douyin\.com|iesdouyin\.com|v\.douyin\.com)", re.IGNORECASE
)

def _is_douyin(url: str) -> bool:
    return bool(_DOUYIN_DOMAINS.search(url))

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

def _ytdlp_extract(url: str) -> dict:
    """在线程池中运行 yt-dlp，避免阻塞事件循环"""
    if yt_dlp is None:
        raise Exception("yt-dlp 未安装")
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 30,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return {}
    # 选取最佳格式
    formats = info.get("formats") or []
    # 找最佳有视频+音频的，或最高质量的
    best_url = info.get("url") or ""
    if not best_url and formats:
        # 优先合并格式（有视频流）
        video_formats = [f for f in formats if f.get("vcodec") != "none" and f.get("url")]
        if video_formats:
            best = max(video_formats, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
            best_url = best.get("url", "")
        elif formats:
            best_url = formats[-1].get("url", "")

    result = {
        "title": info.get("title") or info.get("fulltitle") or "",
        "desc": info.get("description") or "",
        "thumbnail": info.get("thumbnail") or "",
        "duration": info.get("duration") or 0,
        "uploader": info.get("uploader") or info.get("creator") or "",
        "unique_id": info.get("uploader_id") or "",
        "uid": info.get("channel_id") or info.get("uploader_id") or "",
        "platform": info.get("extractor") or info.get("extractor_key") or "",
        "play_count": info.get("view_count"),
        "digg_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "repost_count": info.get("repost_count"),
        "url": best_url,
        "source": url,
        "formats": [
            {
                "url": f.get("url", ""),
                "quality": f.get("format_note") or f.get("format_id") or "",
                "ext": f.get("ext") or "",
                "width": f.get("width"),
                "height": f.get("height"),
                "fps": f.get("fps"),
                "vcodec": f.get("vcodec"),
                "acodec": f.get("acodec"),
                "tbr": f.get("tbr"),
            }
            for f in formats
            if f.get("url")
        ],
    }
    return result


@router.post("/api/ytdlp", include_in_schema=False)
async def sg_api_ytdlp(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)

    url = (body.get("url") or "").strip()
    if not url:
        return JSONResponse({"success": False, "error": "url is required"}, status_code=400)

    if _is_douyin(url):
        return JSONResponse(
            {"success": False, "error": "抖音链接请使用 /api/info 接口"},
            status_code=400,
        )

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(_executor, _ytdlp_extract, url)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"解析失败: {str(e)}"}, status_code=500)

    if not data or not data.get("url"):
        return JSONResponse({"success": False, "error": "未找到可播放的视频地址"}, status_code=400)

    return JSONResponse({"success": True, "data": data})


@router.get("/api/stream", include_in_schema=False)
@router.head("/api/stream", include_in_schema=False)
async def sg_api_stream(request: Request, url: Optional[str] = None):
    target = (url or request.query_params.get("url") or "").strip()
    if not target:
        return JSONResponse({"error": "url is required"}, status_code=400)

    if not target.startswith("http://") and not target.startswith("https://"):
        return JSONResponse({"error": "unsupported url"}, status_code=400)

    try:
        req = urllib.request.Request(
            target,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Accept-Encoding": "identity",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            resp_headers = {}
            for k in ("Content-Type", "Content-Disposition", "Cache-Control", "Accept-Ranges"):
                v = r.headers.get(k)
                if v:
                    resp_headers[k] = v
            return Response(content=body, media_type=r.headers.get("content-type", "video/mp4"), headers=resp_headers)
    except urllib.error.HTTPError as e:
        try:
            payload = e.read().decode("utf-8", errors="replace")
        except Exception:
            payload = ""
        return Response(status_code=e.code, content=payload, media_type="text/plain")
    except Exception as e:
        return JSONResponse({"error": f"stream proxy error: {e}"}, status_code=502)
