from __future__ import annotations

import asyncio
import importlib.util
import logging
import re
import sys
from typing import Any

from backend.paths import DOUK_VENDOR

_request_lock = asyncio.Lock()


def _load_abogus(default_class):
    extension = DOUK_VENDOR / "encipher.py"
    if not extension.exists():
        return default_class()
    spec = importlib.util.spec_from_file_location("x_download_douk_encipher", extension)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 DouK-Downloader 加密扩展：{extension}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    implementation = getattr(module, "ABogus", None)
    if implementation is None:
        raise RuntimeError("DouK-Downloader encipher.py 缺少 ABogus 实现")
    return implementation()


class _AdapterLogger:
    def __init__(self) -> None:
        self._logger = logging.getLogger("x-download.douk")

    def debug(self, message: Any, *_args, **_kwargs) -> None:
        self._logger.debug("%s", message)

    def info(self, message: Any, *_args, **_kwargs) -> None:
        self._logger.info("%s", message)

    def warning(self, message: Any, *_args, **_kwargs) -> None:
        self._logger.warning("%s", message)

    def error(self, message: Any, *_args, **_kwargs) -> None:
        self._logger.error("%s", message)


def _ensure_douk_path() -> None:
    if not DOUK_VENDOR.exists():
        raise RuntimeError("DouK-Downloader 未安装，请重新运行启动脚本")
    vendor = str(DOUK_VENDOR)
    if vendor not in sys.path:
        sys.path.insert(0, vendor)


class _DouKParameters:
    def __init__(self, cookie: str) -> None:
        _ensure_douk_path()

        from rich.console import Console
        from src.custom import DATA_HEADERS
        from src.encrypt import ABogus
        from src.tools import create_client

        self.headers = DATA_HEADERS | ({"Cookie": cookie} if cookie else {})
        self.logger = _AdapterLogger()
        self.ab = _load_abogus(ABogus)
        self.console = Console(stderr=True, quiet=True)
        self.max_retry = 2
        self.timeout = 15
        self.proxy = None
        self.client = create_client(
            headers=self.headers,
            timeout=self.timeout,
            proxy=self.proxy,
        )

    async def close(self) -> None:
        await self.client.aclose()


async def fetch_douyin_detail(detail_id: str, cookie: str = "") -> dict[str, Any]:
    """Fetch one Douyin work through JoeanAmier/DouK-Downloader."""
    _ensure_douk_path()
    from src.interface.detail import Detail
    from src.interface.template import API

    parameters = _DouKParameters(cookie)
    try:
        cookie_values: dict[str, str] = {}
        cookie_name = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
        for part in cookie.replace("\r", "").replace("\n", "").split(";"):
            name, separator, value = part.strip().partition("=")
            if separator and cookie_name.fullmatch(name):
                cookie_values[name] = value.strip().strip('"')
        async with _request_lock:
            API.params["msToken"] = cookie_values.get("msToken", "")
            API.params["uifid"] = cookie_values.get("UIFID", "")
            data = await Detail(
                parameters,
                cookie=cookie,
                detail_id=detail_id,
            ).run()
    finally:
        await parameters.close()
    if not isinstance(data, dict) or not data:
        raise RuntimeError("DouK-Downloader 未返回有效作品数据")
    return data
