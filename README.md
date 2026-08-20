# x-download · 视频解析服务

一个部署在域名下的「智能视频解析」前端 + 后端兼容层，支持抖音 / TikTok / YouTube / Bilibili / Twitter(X) / Instagram 等 1000+ 平台去水印直链解析。


## 架构

```
浏览器 ── https://<你的域名>/ ──┐
                               nginx (反代 /api/ → 127.0.0.1:18111)
                               │
                 compat_sg (FastAPI router)  ← 本仓库 backend/compat_sg.py
                               │
           挂载进 Evil0ctal/Douyin_TikTok_Download_API 主程序
                               │
           抖音详情 ← KR_API_BASE（你自建的 /douyin/share + /douyin/detail 上游）
           TikTok  ← tikwm.com 公共 API
           其他    ← yt-dlp（需自行安装）
```

| 文件 | 作用 |
|------|------|
| `www/index.html` | 视频解析前端（粘贴链接 → 解析 → 播放/下载） |
| `backend/compat_sg.py` | 后端兼容路由：`/api/info`(抖音) `/api/tkinfo`(TikTok) `/api/ytdlp`(通用) `/api/stream`(视频流代理) |
| `backend/compat_app.py` | 附加的 FastAPI 兼容层（`/douyin/share`、`/douyin/detail`、`/health`） |
| `deploy.sh` | 一键部署脚本：交互填写配置 → 生成 `.env` / nginx vhost / systemd 服务 |
| `nginx/x-download.conf` | nginx 反代模板（静态参考，deploy.sh 也会生成） |
| `systemd/x-download-api.service` | systemd 单元模板（静态参考） |

## 后端依赖说明（重要）

`compat_sg.py` 不是独立进程，它依赖开源主程序 **[Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)**：

1. 克隆并安装上游主程序（含 `app/main.py`、`config.yaml`、`start.py`、`venv`）。
2. 把本仓库的 `backend/compat_sg.py` 放到 `<douyin-api>/app/compat_sg.py`。
3. 在 `<douyin-api>/app/main.py` 的 `app = FastAPI(...)` 之后追加一行：
   ```python
   from app.compat_sg import router as sg_router
   app.include_router(sg_router)
   ```
4. 用 `KR_API_BASE=<你的上游>` 环境变量启动 `start.py`（见下方）。

抖音解析需要你自建一个提供 `/douyin/share` 与 `/douyin/detail` 的上游服务，并通过环境变量 `KR_API_BASE` 注入（**不要写死在主程序里**）。TikTok 走公共 tikwm API；其余平台走 yt-dlp。

## 快速部署

```bash
git clone <本仓库> x-download && cd x-download
chmod +x deploy.sh
sudo ./deploy.sh          # 交互填写域名 / 根目录 / 端口 / KR_API_BASE / 运行用户
```

脚本会：复制前端到站点根目录、生成 nginx vhost、生成 systemd 服务、注入 `KR_API_BASE`、reload nginx 并启动服务。
完成后补全 nginx 里的 `ssl_certificate` / `ssl_certificate_key` 路径并配置 HTTPS 即可访问。

## 手动部署要点

- 前端只通过相对路径 `/api/*` 调后端，无需硬编码域名。
- 后端监听 `127.0.0.1:18111`（可在 `config.yaml` 改），nginx 反代 `/api/` 到该端口。
- 视频流代理 `/api/stream` 为同步读取全 body，大视频会占用线程池，属下载阶段非解析阶段。

## 安全 / 隐私

- 原生产环境硬编码的域名（`sg.mxvv.cn`、`kr.mxvv.cn:5555`）、绝对路径（`/www/wwwroot/...`）均已剔除，改为部署时通过 `.env` / 环境变量注入。
- `compat_sg.py` 默认 `KR_API_BASE` 为空，未配置时返回明确错误，不会泄露任何内部地址。
- `.env` 已在 `.gitignore`，请勿提交。
