# x-download

粘贴链接即可解析视频直链的本地服务。把三件事收进**一个命令**：

| 组件 | 作用 |
|------|------|
| **本仓库** | 前端页面 + `/api/parse` 兼容层 + 一键启动 |
| [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) | 抖音 / TikTok（及部分 B 站）解析，启动时自动克隆到 `vendor/` |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | YouTube、Twitter(X)、Instagram 等其余平台 |

首次启动会安装依赖、向你要 Cookie，然后打开浏览器。

## 一键启动

需要：**Python 3.10+**、**Git**。抖音解析还需要你自己的网页 Cookie。

**Windows**

```bat
start.bat
```

或 PowerShell：

```powershell
.\start.ps1
```

**macOS / Linux**

```bash
chmod +x start.sh
./start.sh
```

启动后访问：

- 页面：http://127.0.0.1:18111/
- 健康检查：http://127.0.0.1:18111/api/health
- 上游原始 API 文档：http://127.0.0.1:18111/docs

常用参数：

```text
start.bat --reconfigure     重新填写 Cookie
start.bat --skip-install    已安装过，只启动
start.bat --no-start        只安装，不启动
start.bat --update-vendor   更新 Douyin_TikTok_Download_API
start.bat --no-browser      不自动打开浏览器
```

端口改 `config/app.yaml`，或环境变量 `XDOWNLOAD_HOST` / `XDOWNLOAD_PORT`。

## Cookie 怎么填

启动脚本会生成 `config/cookies.yaml`（已 gitignore）。也可以先复制示例：

```bash
copy config\cookies.example.yaml config\cookies.yaml   # Windows
cp config/cookies.example.yaml config/cookies.yaml     # Unix
```

### 抖音（必填）

1. 浏览器打开 [https://www.douyin.com](https://www.douyin.com) 并登录。
2. `F12` → Network，随便点一个 `douyin.com` 请求。
3. 复制 Request Headers 里的整段 `Cookie`，贴进启动提示或 `config/cookies.yaml` 的 `douyin_cookie`。
4. 改完后必须重新运行启动脚本（或重启服务），Cookie 才会写进上游 `vendor/.../crawlers/douyin/web/config.yaml`。

请用**已登录账号**的 Cookie。上游项目本身也强调：风控靠 Cookie，过期就重新复制。

### TikTok（建议填）

同样从 [https://www.tiktok.com](https://www.tiktok.com) 复制 Cookie 到 `tiktok_cookie`。不填时会尝试公共接口兜底，不稳定。

### yt-dlp（可选）

YouTube 会员视频、需登录的 Instagram / X 等，把浏览器 Cookie 导出成 **Netscape `cookies.txt`**：

- 填 `ytdlp_cookies_file` 为文件路径，或直接放到 `config/ytdlp_cookies.txt`。
- 不要把 Cookie 文件提交到 git。

安装 [ffmpeg](https://ffmpeg.org/) 后，yt-dlp 合并音视频更稳。Windows 示例：`winget install Gyan.FFmpeg`。

## 三个项目怎么拼在一起

```
浏览器
  └─ web/index.html
        POST /api/parse
              │
              ├─ 抖音 / TikTok ── HybridCrawler（vendor 里的 Evil0ctal 项目）
              │                      Cookie 来自 config/cookies.yaml
              ├─ TikTok 失败时 ── tikwm 公共接口兜底
              └─ 其他平台 ────── yt-dlp（可选 cookies.txt）
```

不再需要单独部署 `LEGACY_DOUYIN_API_BASE`。旧的 `/douyin/share` + `/douyin/detail` 桥接仍保留在 `backend/compat_app.py`，仅供特殊部署。

前端只打相对路径 `/api/*`，本机和后面用 nginx 反代都可以。

| 路径 | 说明 |
|------|------|
| `POST /api/parse` | 自动分流（推荐） |
| `POST /api/info` | 与 parse 相同（兼容旧前端） |
| `POST /api/tkinfo` | TikTok |
| `POST /api/ytdlp` | 强制走 yt-dlp |
| `GET /api/stream?url=` | 视频流代理；加 `&download=1` 当附件下载 |
| `GET /api/health` | 依赖 / Cookie 是否就绪 |
| `/api/hybrid/video_data` 等 | 上游 Evil0ctal 原接口 |

## 仓库结构

```
start.bat / start.ps1 / start.sh   一键入口
scripts/bootstrap.py               克隆上游、建 venv、装依赖、问 Cookie、起服务
config/app.yaml                    监听地址
config/cookies.example.yaml        Cookie 模板
web/index.html                     解析页
backend/server.py                  FastAPI 入口
backend/media_api.py               媒体解析与 API 路由
vendor/                            启动时克隆，不入库
.venv/                             虚拟环境，不入库
```

## 生产环境（可选，Linux + nginx）

本机先 `./start.sh --no-start` 装好依赖，再用 `deploy.sh` 写 nginx / systemd。证书路径要自己补。日常开发用一键脚本即可，不必上 nginx。

## 使用边界

仅供学习、调试和下载**你有权保存**的内容。请遵守抖音 / TikTok / YouTube 等平台条款以及当地版权法。不要传播他人 Cookie，也不要把 `config/cookies.yaml` 推到公开仓库。

上游许可证：[Apache-2.0](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)。yt-dlp 使用其自己的 Unlicense。
