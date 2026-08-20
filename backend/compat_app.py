import re, json, httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

API_BASE = "http://127.0.0.1:18111"
app = FastAPI()

def extract_ids(text: str):
    text = text.strip()
    m = re.search(r"/video/(\d+)", text)
    if m:
        return m.group(1), None
    m = re.search(r"/user/([A-Za-z0-9_-]+)", text)
    if m:
        return None, m.group(1)
    return None, None

def pick_first_url(obj):
    if isinstance(obj, dict):
        return pick_first_url(obj.get("url_list") or obj.get("url") or "")
    if isinstance(obj, list) and obj:
        return pick_first_url(obj[0])
    if isinstance(obj, str):
        return obj
    return ""

@app.post("/douyin/share")
async def douyin_share(request: Request):
    body = await request.json()
    text = body.get("text", "")
    video_id, _ = extract_ids(text)
    if not video_id:
        raise HTTPException(status_code=400, detail={"msg": "无法从链接提取视频ID", "text": text})
    return {"url": f"https://www.douyin.com/video/{video_id}"}

@app.post("/douyin/detail")
async def douyin_detail(request: Request):
    body = await request.json()
    detail_id = body.get("detail_id", "")
    if not detail_id:
        raise HTTPException(status_code=400, detail={"msg": "缺少 detail_id"})
    async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=5.0)) as client:
        r = await client.get(
            f"{API_BASE}/api/hybrid/video_data",
            params={"url": f"https://www.douyin.com/video/{detail_id}"},
            headers={"Accept": "application/json"},
        )
    try:
        upstream = r.json()
    except Exception:
        raise HTTPException(status_code=502, detail={"msg": "上游响应异常", "raw": r.text[:200]})
    d = upstream.get("data") if isinstance(upstream, dict) else None
    if not isinstance(d, dict):
        d = upstream if isinstance(upstream, dict) else {}
    author = d.get("author") or {}
    video = d.get("video") or {}
    statistics = d.get("statistics") or {}
    music = d.get("music") or {}
    mapped = {
        "desc": d.get("desc") or d.get("caption") or "",
        "create_time": d.get("create_time") or "",
        "duration": (video.get("duration") if isinstance(video, dict) else None)
        or (music.get("duration") if isinstance(music, dict) else None),
        "nickname": author.get("nickname") if isinstance(author, dict) else "",
        "unique_id": (author.get("unique_id") or author.get("short_id") or "")
        if isinstance(author, dict)
        else "",
        "signature": (author.get("signature") or "") if isinstance(author, dict) else "",
        "digg_count": statistics.get("digg_count") if isinstance(statistics, dict) else None,
        "comment_count": statistics.get("comment_count") if isinstance(statistics, dict) else None,
        "collect_count": statistics.get("collect_count") if isinstance(statistics, dict) else None,
        "share_count": statistics.get("share_count") if isinstance(statistics, dict) else None,
        "static_cover": pick_first_url(video.get("cover") if isinstance(video, dict) else None),
        "dynamic_cover": pick_first_url(video.get("dynamic_cover") if isinstance(video, dict) else None),
        "downloads": pick_first_url(video.get("play_addr") if isinstance(video, dict) else None)
        or pick_first_url(video.get("download_addr") if isinstance(video, dict) else None),
        "music_url": pick_first_url(music.get("play_url") if isinstance(music, dict) else None),
    }
    return {"data": mapped, "code": 200}

@app.get("/health")
async def health():
    return {"ok": True}
