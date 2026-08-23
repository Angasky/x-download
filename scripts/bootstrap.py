#!/usr/bin/env python3
"""一键安装依赖、写入 Cookie、启动 x-download。"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
import webbrowser
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="backslashreplace")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VENDOR = ROOT / "vendor" / "TikTokDownloader"
VENDOR_REPO = "https://github.com/JoeanAmier/TikTokDownloader.git"
VENV_DIR = ROOT / ".venv"
CONFIG_DIR = ROOT / "config"
COOKIES_FILE = CONFIG_DIR / "cookies.yaml"
COOKIES_EXAMPLE = CONFIG_DIR / "cookies.example.yaml"
YTDLP_COOKIES = CONFIG_DIR / "ytdlp_cookies.txt"
APP_CONFIG = CONFIG_DIR / "app.yaml"


def py_exe() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, **kwargs)


def ensure_python() -> None:
    if sys.version_info < (3, 12):
        raise SystemExit(f"DouK-Downloader 需要 Python 3.12+，当前是 {sys.version}")


def ensure_venv() -> Path:
    exe = py_exe()
    if not exe.exists():
        print("[setup] 创建虚拟环境 .venv")
        venv.EnvBuilder(with_pip=True).create(str(VENV_DIR))
    if not exe.exists():
        raise SystemExit("创建虚拟环境失败")
    return exe


def dependency_check(python: Path) -> tuple[bool, str]:
    """Check imports that must work before the application can start."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [
            str(python),
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(VENDOR)!r}); "
                "import anyio, fastapi, httpx, sniffio, uvicorn, yaml, yt_dlp; "
                "from src.interface.detail import Detail"
            ),
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    error = result.stderr.decode("utf-8", errors="replace").strip()
    return result.returncode == 0, error


def recreate_venv() -> Path:
    """Recreate only this project's generated virtual environment."""
    resolved_root = ROOT.resolve()
    resolved_venv = VENV_DIR.resolve()
    if resolved_venv.parent != resolved_root or resolved_venv.name != ".venv":
        raise SystemExit(f"拒绝清理非项目虚拟环境：{resolved_venv}")
    if VENV_DIR.exists():
        print("[repair] 清理损坏的项目虚拟环境 .venv")
        shutil.rmtree(VENV_DIR)
    return ensure_venv()


def ensure_dependencies_healthy(python: Path) -> Path:
    healthy, error = dependency_check(python)
    if healthy:
        return python

    print("[warning] 检测到虚拟环境依赖缺失或损坏，将自动重建 .venv。")
    if error:
        print("  原因：", error.splitlines()[-1])
    python = recreate_venv()
    pip_install(python)
    healthy, error = dependency_check(python)
    if not healthy:
        detail = f"\n{error}" if error else ""
        raise SystemExit(f"虚拟环境重建后依赖检查仍未通过。{detail}")
    print("[ok] 虚拟环境已修复")
    return python


def validate_app_import(python: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [str(python), "-c", "from backend.media_api import router"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode == 0:
        return
    error = result.stderr.decode("utf-8", errors="replace").strip()
    raise SystemExit(f"应用启动检查失败：\n{error or '未知导入错误'}")


def ensure_vendor(update: bool) -> None:
    if not shutil.which("git"):
        raise SystemExit("未找到 git，请先安装 Git 后再运行一键启动。")
    VENDOR.parent.mkdir(parents=True, exist_ok=True)
    if not VENDOR.exists():
        print("[setup] 克隆 JoeanAmier/TikTokDownloader")
        run(["git", "clone", "--depth", "1", VENDOR_REPO, str(VENDOR)])
        return
    if update:
        print("[setup] 更新 JoeanAmier/TikTokDownloader")
        run(["git", "-C", str(VENDOR), "pull", "--ff-only"])


def pip_install(python: Path) -> None:
    run([str(python), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"])
    vendor_req = VENDOR / "requirements.txt"
    if vendor_req.exists():
        print("[setup] 安装 DouK-Downloader 依赖")
        run([str(python), "-m", "pip", "install", "-r", str(vendor_req)])
    print("[setup] 安装 yt-dlp 与本项目依赖")
    run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])


def load_app_config() -> tuple[str, int, bool]:
    host, port, open_browser = "127.0.0.1", 18111, True
    if APP_CONFIG.exists():
        for line in APP_CONFIG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("host:"):
                host = line.split(":", 1)[1].strip() or host
            elif line.startswith("port:"):
                try:
                    port = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith("open_browser:"):
                open_browser = line.split(":", 1)[1].strip().lower() in {"true", "1", "yes"}
    host = os.environ.get("XDOWNLOAD_HOST", host)
    port = int(os.environ.get("XDOWNLOAD_PORT", str(port)))
    return host, port, open_browser


def save_app_config(host: str, port: int, open_browser: bool) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    APP_CONFIG.write_text(
        "# x-download 服务配置\n"
        f"host: {host}\n"
        f"port: {port}\n"
        "# 浏览器自动打开（一键启动时）\n"
        f"open_browser: {'true' if open_browser else 'false'}\n",
        encoding="utf-8",
    )


def prompt_cookies(reconfigure: bool) -> None:
    from backend.cookies import load_cookies, save_cookies, save_x_cookies

    def prompt_pasted_value(label: str) -> str:
        first_line = input(label).strip()
        if not first_line:
            return ""
        lines = [first_line]
        if first_line.startswith("[") or first_line.startswith("{"):
            closing = "]" if first_line.startswith("[") else "}"
            while not lines[-1].rstrip().endswith(closing):
                lines.append(input())
        return "\n".join(lines)

    current = load_cookies() if COOKIES_FILE.exists() else {
        "douyin_cookie": "",
        "tiktok_cookie": "",
        "ytdlp_cookies_file": "",
    }
    need = reconfigure or not current.get("douyin_cookie")
    if not need:
        print("[ok] 已读取 config/cookies.yaml")
        return

    print()
    print("=" * 60)
    print("  Cookie 配置（抖音解析必须）")
    print("=" * 60)
    print("抖音：打开 https://www.douyin.com 并登录 -> F12 -> Network")
    print("     点任意 douyin.com 请求 -> 复制 Request Headers 的 Cookie")
    print("TikTok：同样从 https://www.tiktok.com 复制 Cookie（可回车跳过）")
    print("X/Twitter：可直接粘贴浏览器扩展导出的完整 Cookie JSON，用于受限视频")
    print("yt-dlp：Netscape cookies.txt 路径，可选；也可放到 config/ytdlp_cookies.txt")
    print()
    try:
        douyin = input("抖音 Cookie（直接回车保留已有值）:\n").strip() or current.get("douyin_cookie", "")
        tiktok = input("TikTok Cookie（可空）:\n").strip() or current.get("tiktok_cookie", "")
        ytdlp = input("yt-dlp cookies.txt 路径（可空）:\n").strip() or current.get("ytdlp_cookies_file", "")
        x_cookie_export = prompt_pasted_value(
            "X/Twitter Cookie JSON / 单行 Cookie（自动合并到 yt-dlp Cookie 文件；回车保留）:\n"
        )
    except EOFError:
        douyin = current.get("douyin_cookie", "")
        tiktok = current.get("tiktok_cookie", "")
        ytdlp = current.get("ytdlp_cookies_file", "")
        x_cookie_export = ""

    save_cookies({
        "douyin_cookie": douyin,
        "tiktok_cookie": tiktok,
        "ytdlp_cookies_file": ytdlp,
    })
    if not douyin:
        print("[warning] 未填写抖音 Cookie：抖音链接解析大概率失败，可稍后编辑 config/cookies.yaml 再启动。")
    else:
        print("[ok] 抖音 Cookie 已保存")
    if tiktok:
        print("[ok] TikTok Cookie 已保存")
    if x_cookie_export:
        target = Path(ytdlp).expanduser() if ytdlp else YTDLP_COOKIES
        if not target.is_absolute():
            target = ROOT / target
        try:
            count = save_x_cookies(x_cookie_export, target)
            print(f"[ok] X/Twitter Cookie 已保存（{count} 项），可解析需要登录的视频")
        except ValueError as exc:
            print(f"[warning] X/Twitter Cookie 未保存：{exc}")


def start_server(python: Path, host: str, port: int, open_browser: bool) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["XDOWNLOAD_HOST"] = host
    env["XDOWNLOAD_PORT"] = str(port)
    url = f"http://{host}:{port}/"
    print()
    print("=" * 60)
    print(f"  启动 x-download  ->  {url}")
    print("  API 文档          ->  http://%s:%s/docs" % (host, port))
    print("  健康检查          ->  http://%s:%s/api/health" % (host, port))
    if not shutil.which("ffmpeg"):
        print("  提示：未检测到 ffmpeg，部分 yt-dlp 音视频合并可能失败。")
        print("        Windows 可用 winget install Gyan.FFmpeg")
    print("  按 Ctrl+C 停止")
    print("=" * 60)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    os.chdir(str(ROOT))
    raise SystemExit(
        subprocess.call(
            [
                str(python),
                "-m",
                "uvicorn",
                "backend.server:app",
                "--host",
                host,
                "--port",
                str(port),
                "--no-use-colors",
            ],
            env=env,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="x-download 一键安装并启动")
    parser.add_argument("--skip-install", action="store_true", help="跳过 pip / git 克隆")
    parser.add_argument("--update-vendor", action="store_true", help="git pull 更新上游 API")
    parser.add_argument("--reconfigure", action="store_true", help="重新填写 Cookie")
    parser.add_argument("--no-start", action="store_true", help="只安装，不启动服务")
    parser.add_argument("--no-browser", action="store_true", help="启动后不打开浏览器")
    parser.add_argument("--host", help="设置并保存监听地址，例如 0.0.0.0")
    parser.add_argument("--port", type=int, help="设置并保存监听端口")
    parser.add_argument("--skip-cookie-prompt", action="store_true", help="不询问 Cookie")
    args = parser.parse_args()

    os.chdir(str(ROOT))
    ensure_python()
    python = ensure_venv()
    if not args.skip_install:
        ensure_vendor(update=args.update_vendor)
        pip_install(python)
    elif not VENDOR.exists():
        raise SystemExit("vendor 目录不存在，请先不要加 --skip-install")

    python = ensure_dependencies_healthy(python)
    validate_app_import(python)

    host, port, open_browser = load_app_config()
    if args.host:
        host = args.host
    if args.port is not None:
        if not 1 <= args.port <= 65535:
            raise SystemExit("端口必须在 1 到 65535 之间。")
        port = args.port
    if args.host or args.port is not None:
        save_app_config(host, port, open_browser)
        print(f"[ok] 服务监听配置已保存：{host}:{port}")

    if not args.skip_cookie_prompt:
        prompt_cookies(reconfigure=args.reconfigure)
    if args.no_start:
        print("安装完成。下次直接运行 start.bat / start.ps1 / ./start.sh")
        return
    if args.no_browser:
        open_browser = False
    start_server(python, host, port, open_browser)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已停止")
