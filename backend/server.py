from __future__ import annotations

import asyncio
import os
import sys
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.paths import ROOT, WEB

from backend.media_api import router as media_router

app = FastAPI(
    title="x-download",
    description="一键启动的视频解析服务：抖音（DouK-Downloader）+ TikTok/其他平台解析",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(media_router)


@app.middleware("http")
async def disable_index_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in {"/", "/index.html"}:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.on_event("startup")
async def suppress_windows_browser_disconnects() -> None:
    if sys.platform != "win32":
        return
    loop = asyncio.get_running_loop()
    default_handler = loop.get_exception_handler()

    def handle_loop_exception(current_loop, context) -> None:
        error = context.get("exception")
        if isinstance(error, ConnectionResetError) and getattr(error, "winerror", None) == 10054:
            return
        if default_handler:
            default_handler(current_loop, context)
        else:
            current_loop.default_exception_handler(context)

    loop.set_exception_handler(handle_loop_exception)

if WEB.exists():
    app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")


def run() -> None:
    import uvicorn

    host = os.environ.get("XDOWNLOAD_HOST", "127.0.0.1")
    port = int(os.environ.get("XDOWNLOAD_PORT", "18111"))
    os.chdir(str(ROOT))
    uvicorn.run("backend.server:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    run()
