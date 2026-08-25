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
WINDOWS_SETUP_MARKER = CONFIG_DIR / ".setup_complete"


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


def windows_logo() -> None:
    os.system("cls")
    print(
        r"""
███╗   ███╗██╗  ██╗██╗ ██████╗  ██████╗
████╗ ████║╚██╗██╔╝██║██╔═══██╗██╔════╝
██╔████╔██║ ╚███╔╝ ██║██║   ██║██║
██║╚██╔╝██║ ██╔██╗ ██║██║   ██║██║
██║ ╚═╝ ██║██╔╝ ██╗██║╚██████╔╝╚██████╗
╚═╝     ╚═╝╚═╝  ╚═╝╚═╝ ╚═════╝  ╚═════╝
""".strip("\n")
    )
    print("        x-download · Mxioc Windows 管理控制台")
    print("  ────────────────────────────────────────────")


def prompt_port(current: int) -> int:
    while True:
        value = input(f"请输入网页访问端口 [当前 {current}]：").strip()
        if not value:
            return current
        try:
            port = int(value)
        except ValueError:
            print("[提示] 请输入数字端口。")
            continue
        if 1 <= port <= 65535:
            return port
        print("[提示] 端口必须在 1 到 65535 之间。")


def prompt_yes_no(label: str, default: bool) -> bool:
    hint = "Y/n" if default else "y/N"
    value = input(f"{label} [{hint}]：").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "1", "是"}


def windows_first_run() -> None:
    windows_logo()
    print("  首次启动配置向导")
    print("  配置仅保存在当前项目的 config 目录中。")
    print("  ────────────────────────────────────────────")
    _, current_port, current_browser = load_app_config()
    port = prompt_port(current_port)
    print("  1. 仅本机访问（推荐，更安全）")
    print("  2. 局域网 / 公网访问")
    access = input("请选择访问模式 [默认 1]：").strip()
    host = "0.0.0.0" if access == "2" else "127.0.0.1"
    open_browser = prompt_yes_no("启动后自动打开浏览器", current_browser)
    save_app_config(host, port, open_browser)
    prompt_cookies(reconfigure=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    WINDOWS_SETUP_MARKER.write_text("configured\n", encoding="utf-8")
    print("\n[完成] 首次配置已保存，正在安装依赖并启动服务。")


def windows_menu(args: argparse.Namespace) -> bool:
    while True:
        host, port, open_browser = load_app_config()
        access_text = "公网 / 局域网" if host == "0.0.0.0" else "仅本机"
        browser_text = "开启" if open_browser else "关闭"
        windows_logo()
        print("   1.  启动服务          2.  修改 Cookie")
        print("   3.  修改访问端口      4.  修改访问模式")
        print("   5.  自动打开浏览器    6.  更新后启动")
        print("   7.  打开配置目录      0.  退出")
        print("  ────────────────────────────────────────────")
        print(f"  状态：{access_text} · 端口 {port} · 浏览器 {browser_text}")
        print(f"  配置：{CONFIG_DIR}")
        print()
        choice = input("请选择操作 [0-7]：").strip()
        if choice == "1":
            return True
        if choice == "2":
            prompt_cookies(reconfigure=True)
            input("\n按 Enter 返回菜单……")
        elif choice == "3":
            save_app_config(host, prompt_port(port), open_browser)
            print("[完成] 端口已保存。")
            input("\n按 Enter 返回菜单……")
        elif choice == "4":
            new_host = "127.0.0.1" if host == "0.0.0.0" else "0.0.0.0"
            save_app_config(new_host, port, open_browser)
            print(f"[完成] 已切换为{'仅本机访问' if new_host == '127.0.0.1' else '公网 / 局域网访问'}。")
            input("\n按 Enter 返回菜单……")
        elif choice == "5":
            save_app_config(host, port, not open_browser)
            print(f"[完成] 自动打开浏览器已{'开启' if not open_browser else '关闭'}。")
            input("\n按 Enter 返回菜单……")
        elif choice == "6":
            args.update_vendor = True
            return True
        elif choice == "7":
            os.startfile(CONFIG_DIR)  # type: ignore[attr-defined]
        elif choice == "0":
            return False
        else:
            print("[提示] 无效选项，请重新输入。")
            input("\n按 Enter 返回菜单……")


def prompt_cookies(reconfigure: bool) -> None:
    from backend.cookies import load_cookies, save_bilibili_cookies, save_cookies, save_x_cookies, save_youtube_cookies

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
    print("YouTube：可直接粘贴 Cookie-Editor 导出的完整 Cookie JSON")
    print("哔哩哔哩：可粘贴 Cookie-Editor JSON，用于获取登录后可用的无水印高清 DASH")
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
        try:
            youtube_cookie_export = prompt_pasted_value(
                "YouTube Cookie JSON / Netscape Cookie（自动合并；回车保留）:\n"
            )
        except (EOFError, StopIteration):
            youtube_cookie_export = ""
        try:
            bilibili_cookie_export = prompt_pasted_value(
                "哔哩哔哩 Cookie JSON / 单行 Cookie（自动合并；回车保留）:\n"
            )
        except (EOFError, StopIteration):
            bilibili_cookie_export = ""
    except EOFError:
        douyin = current.get("douyin_cookie", "")
        tiktok = current.get("tiktok_cookie", "")
        ytdlp = current.get("ytdlp_cookies_file", "")
        youtube_cookie_export = ""
        x_cookie_export = ""
        bilibili_cookie_export = ""

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
    target = Path(ytdlp).expanduser() if ytdlp else YTDLP_COOKIES
    if not target.is_absolute():
        target = ROOT / target
    if youtube_cookie_export:
        try:
            first_line = youtube_cookie_export.lstrip("\ufeff\r\n").splitlines()[0].strip()
            if first_line in {"# Netscape HTTP Cookie File", "# HTTP Cookie File"}:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(youtube_cookie_export.lstrip("\ufeff"), encoding="utf-8", newline="\n")
                print("[ok] YouTube Netscape Cookie 已保存")
            else:
                count = save_youtube_cookies(youtube_cookie_export, target)
                print(f"[ok] YouTube Cookie 已保存（{count} 项）")
        except ValueError as exc:
            print(f"[warning] YouTube Cookie 未保存：{exc}")
    if x_cookie_export:
        try:
            count = save_x_cookies(x_cookie_export, target)
            print(f"[ok] X/Twitter Cookie 已保存（{count} 项），可解析需要登录的视频")
        except ValueError as exc:
            print(f"[warning] X/Twitter Cookie 未保存：{exc}")
    if bilibili_cookie_export:
        try:
            count = save_bilibili_cookies(bilibili_cookie_export, target)
            print(f"[ok] 哔哩哔哩 Cookie 已保存（{count} 项），将尝试获取更多无水印清晰度")
        except ValueError as exc:
            print(f"[warning] 哔哩哔哩 Cookie 未保存：{exc}")


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
    parser.add_argument("--windows-menu", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    os.chdir(str(ROOT))
    if args.windows_menu and os.name == "nt":
        if not WINDOWS_SETUP_MARKER.exists():
            windows_first_run()
        elif not windows_menu(args):
            return
        # Windows 向导和菜单已经负责 Cookie 配置，启动阶段不再重复询问。
        args.skip_cookie_prompt = True
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
