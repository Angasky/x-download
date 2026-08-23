# x-download

x-download 是一个本地视频解析与下载服务。粘贴作品链接后，页面会展示视频、作者资料、互动数据、可用清晰度和预计文件大小，并通过本地代理完成预览或下载。

## 功能

- 抖音：使用 [JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader)（DouK-Downloader）解析。
- TikTok：优先使用 tikwm，失败时使用 yt-dlp。
- YouTube、Bilibili、X、Instagram 等：使用 [yt-dlp](https://github.com/yt-dlp/yt-dlp)；实际支持情况以上游 Extractor 为准。
- 展示作者头像、名称、平台账号 ID、UID、主页链接、主页简介和视频文案。
- 展示点赞、评论、收藏、分享；TikTok 额外展示播放量。
- 将同一分辨率的重复码率档位自动合并，只保留综合质量更合适的版本。
- 使用按钮选择分辨率；下载、直链和页面预览会同步切换。
- 显示上游提供的精确文件大小；没有精确值时根据码率和时长显示估算值。
- 自动创建 Python 虚拟环境、安装依赖、克隆上游项目并打开本地页面。

## 工作方式

```text
浏览器 web/index.html
        │
        └── POST /api/parse
               ├── 抖音 ───── DouK-Downloader
               │                └── 失败时尝试 yt-dlp
               ├── TikTok ─── tikwm
               │                └── 失败时尝试 yt-dlp
               └── 其他平台 ─ yt-dlp
                                └── 可选 Netscape cookies.txt
```

项目不再使用 `Evil0ctal/Douyin_TikTok_Download_API`。

## 环境要求

- Python 3.12 或更高版本
- Git
- 可访问目标网站的网络
- ffmpeg（可选但推荐，用于合并 yt-dlp 的独立视频轨和音频轨）

Windows 安装 ffmpeg：

```powershell
winget install Gyan.FFmpeg
```

## 一键启动

### Windows

双击 `start.bat`，或者在终端运行：

```bat
start.bat
```

PowerShell 入口：

```powershell
.\start.ps1
```

### macOS / Linux

```bash
chmod +x start.sh
./start.sh
```

首次运行会：

1. 创建 `.venv` 虚拟环境。
2. 安装项目与 DouK-Downloader 依赖。
3. 将上游项目克隆到 `vendor/TikTokDownloader`。
4. 提示填写抖音、TikTok 和 yt-dlp Cookie 配置。
5. 启动服务并打开浏览器。

默认地址：

| 功能 | 地址 |
|---|---|
| 操作页面 | http://127.0.0.1:18111/ |
| API 文档 | http://127.0.0.1:18111/docs |
| 健康检查 | http://127.0.0.1:18111/api/health |

常用启动参数：

```text
start.bat --reconfigure     重新填写 Cookie
start.bat --skip-install    跳过依赖安装和上游克隆
start.bat --no-start        只安装和检查，不启动服务
start.bat --update-vendor   更新 DouK-Downloader
start.bat --no-browser      启动后不自动打开浏览器
```

监听地址和端口可以在 `config/app.yaml` 中修改，也可以使用环境变量 `XDOWNLOAD_HOST` 和 `XDOWNLOAD_PORT`。

## Cookie 配置

启动脚本会把配置写入 `config/cookies.yaml`。该文件和 `config/ytdlp_cookies.txt` 已被 Git 忽略，不会正常提交到仓库。

配置结构：

```yaml
douyin_cookie: "抖音网页请求中的完整 Cookie"
tiktok_cookie: "TikTok 网页请求中的完整 Cookie，可选"
ytdlp_cookies_file: "Netscape cookies.txt 的绝对路径，可选"
```

修改 Cookie 后需要重启服务。也可以运行：

```bat
start.bat --reconfigure
```

### 获取抖音 Cookie

1. 浏览器打开 [抖音网页版](https://www.douyin.com/)并登录。
2. 按 `F12` 打开开发者工具，进入 `Network`。
3. 刷新页面或打开任意作品。
4. 选择一个发往 `douyin.com` 的请求。
5. 在 `Request Headers` 中复制完整的 `Cookie` 值。
6. 运行 `start.bat --reconfigure` 粘贴，或者填写 `config/cookies.yaml` 中的 `douyin_cookie`。

Cookie 过期、账号状态变化或网络环境变化后，需要重新复制最新 Cookie。VPN 无法连接抖音服务器时，请关闭 VPN 后再解析。

### 获取 TikTok Cookie

TikTok Cookie 不是所有公开视频的必填项。需要时可在 [TikTok](https://www.tiktok.com/) 登录后，按照与抖音相同的方法复制完整请求 Cookie，并写入 `tiktok_cookie`。

### 获取 YouTube Cookie

YouTube Cookie 主要用于需要账号访问的内容，例如年龄限制视频、私人播放列表和会员内容。普通公开视频不一定需要 Cookie。

> 使用账号 Cookie 进行大量或高频下载存在账号被临时或永久限制的风险。仅在必要时使用，控制请求频率，推荐使用专门的备用账号。

YouTube 会频繁轮换普通浏览器标签页里的账号 Cookie。为了导出相对稳定的 Cookie，按照 [yt-dlp 官方 YouTube Cookie 指南](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies)操作：

1. 安装 yt-dlp 官方 FAQ 推荐的本地导出扩展：
   - Chrome / Edge：`Get cookies.txt LOCALLY`
   - Firefox：`cookies.txt`
2. 如果使用无痕窗口，在扩展管理页面允许该扩展在无痕模式中运行。
3. 新建一个无痕或隐私窗口，只保留一个标签页。
4. 在该标签页登录 YouTube。
5. 使用同一个标签页访问 [https://www.youtube.com/robots.txt](https://www.youtube.com/robots.txt)。
6. 使用扩展只导出 `youtube.com` 的 Cookie。
7. 将文件保存为：

   ```text
   C:\Users\Administrator\Projects\x-download\config\ytdlp_cookies.txt
   ```

   如果项目位于其他目录，请保存到实际项目的 `config/ytdlp_cookies.txt`。

8. 导出后立即关闭整个无痕窗口，不要继续使用该登录会话，以免 YouTube 再次轮换 Cookie。
9. 重启 `start.bat`，健康检查中的 `yt-dlp cookies` 应显示为已配置。

也可以把 Cookie 文件放在其他位置，然后将绝对路径填写到 `config/cookies.yaml`：

```yaml
ytdlp_cookies_file: "D:\\private\\youtube-cookies.txt"
```

Cookie 文件必须采用 Mozilla/Netscape 格式，第一行必须是以下内容之一：

```text
# Netscape HTTP Cookie File
```

```text
# HTTP Cookie File
```

Windows 文件建议使用 `CRLF` 换行，Linux 和 macOS 使用 `LF`。如果使用 Cookie 后出现 `HTTP Error 400: Bad Request`，请优先检查文件格式和换行符。详细要求参见 [yt-dlp Cookie FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)。

不要使用下面的方式导出上述无痕 YouTube 会话：

```bash
yt-dlp --cookies-from-browser chrome --cookies cookies.txt
```

这个命令会读取普通浏览器配置中的所有网站 Cookie，无法正确导出上述无痕 YouTube 会话，还会把其他网站的敏感 Cookie 一起写入文件。

如果页面提示以下内容，说明需要重新配置有效的 YouTube Cookie：

```text
请配置 COOKIE，教程可查看 README.md 或 yt-dlp Wiki：https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies
```

Cookie 不能解决所有 YouTube 限制。YouTube 正在逐步要求 PO Token，部分客户端、格式或功能即使配置 Cookie 也可能不可用，详情参见 [yt-dlp PO Token 指南](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide)。

## 解析结果与清晰度

抖音解析结果可以包含：

- 作者头像、名称、抖音号、UID、主页链接和主页简介
- 视频文案
- 点赞、评论、收藏和分享数量
- 分辨率、帧率、文件大小、预览地址和下载地址

TikTok 在这些信息基础上还会展示播放量。

DouK 可能为同一分辨率返回多个内部码率档位。前端会按照音轨、帧率、文件大小和码率自动选择更合适的版本，只显示简洁按钮，例如：

```text
1440P · 60 FPS
1440 × 2560 · 2.4 MB
```

文件大小显示规则：

- 上游返回文件大小：直接显示 `KB / MB / GB`。
- 上游没有大小但返回码率和时长：显示“约”。
- 两者都没有：显示“大小未知”。
- yt-dlp 返回没有音轨的视频规格时，会标记“仅视频”；这类格式需要 ffmpeg 与音频轨合并。

## API

推荐使用统一接口：

```http
POST /api/parse
Content-Type: application/json

{
  "url": "https://www.douyin.com/video/..."
}
```

主要接口：

| 方法与路径 | 说明 |
|---|---|
| `POST /api/parse` | 自动识别平台并解析，推荐使用 |
| `POST /api/info` | 与 `/api/parse` 相同，保留旧接口兼容 |
| `POST /api/tkinfo` | TikTok 兼容接口 |
| `POST /api/ytdlp` | 强制使用 yt-dlp；不用于抖音 |
| `POST /api/download` | 解析并下载默认视频 |
| `GET /api/stream?url=...` | 代理预览媒体 |
| `GET /api/stream?url=...&download=1` | 代理下载媒体 |
| `GET /api/health` | 检查依赖、ffmpeg、DouK 和 Cookie 状态 |

成功响应中的常用字段：

```text
title / desc / thumbnail / duration
uploader / unique_id / uid / avatar / author_signature / profile_url
play_count / digg_count / comment_count / collect_count / share_count
url / images / formats / platform / source
```

## 项目结构

```text
backend/
  cookies.py          Cookie 读写与 yt-dlp Cookie 文件定位
  douk_adapter.py     JoeanAmier/TikTokDownloader 适配层
  media_api.py        平台分流、数据映射、清晰度和 API
  paths.py            项目路径
  server.py           FastAPI 服务入口
config/
  app.yaml            监听地址与浏览器配置
  cookies.example.yaml
  cookies.yaml        本地私密 Cookie，不入库
  ytdlp_cookies.txt   可选 Netscape Cookie 文件，不入库
scripts/
  bootstrap.py        安装、更新、配置和启动逻辑
vendor/
  TikTokDownloader/   启动时克隆的 DouK-Downloader，不入库
web/
  index.html          前端页面
start.bat             Windows 一键入口
start.ps1             PowerShell 入口
start.sh              macOS / Linux 入口
```

## 常见问题

### YouTube 提示确认不是机器人

按照“获取 YouTube Cookie”章节重新导出 Cookie，保存到 `config/ytdlp_cookies.txt` 后重启服务。不要把浏览器请求头中的一整段 Cookie 直接粘贴成 Netscape 文件。

### 抖音解析失败或提示 Cookie 失效

关闭无法访问抖音的 VPN，确认浏览器可以打开抖音，然后运行 `start.bat --reconfigure` 填写最新 Cookie。

### 页面出现 CSS 404

类似 `/css/modules/laydate/`、`/css/modules/layer/` 或 `/.well-known/appspecific/` 的请求通常来自浏览器扩展或开发者工具探测，不是 x-download 页面依赖。

### Windows 出现 WinError 10054

这通常是浏览器主动中断媒体或探测连接造成的连接重置。服务已忽略该类已知噪声；只要健康检查正常，就不代表服务崩溃。

### 高分辨率没有声音

部分网站会把高分辨率视频和音频分开提供。安装 ffmpeg 后让 yt-dlp 合并，或者选择标记为带音频的规格；“仅视频”档位本身不包含声音。

### 页面仍显示旧样式

停止服务后重新运行 `start.bat`，然后在浏览器中按 `Ctrl+F5` 强制刷新。

## 部署

日常本机使用只需一键启动。Linux 生产部署可以先运行：

```bash
./start.sh --no-start
```

再根据实际域名和证书配置 `nginx/x-download.conf`、`systemd/x-download-api.service` 或 `deploy.sh`。前端使用相对 `/api/*` 路径，可以放在 nginx 反向代理后面。

## 安全与使用边界

- 仅解析和下载你有权访问、保存和使用的内容。
- 遵守抖音、TikTok、YouTube 等平台条款以及适用法律。
- Cookie 文件等同于登录凭证，不要发送给他人、上传网盘、提交到 Git 或粘贴到公开 Issue。
- 不要使用主账号进行高频、自动化或批量下载。
- `config/cookies.yaml`、`config/ytdlp_cookies.txt`、`.venv/` 和 `vendor/` 均不应提交。

DouK-Downloader 使用 [GPL-3.0](https://github.com/JoeanAmier/TikTokDownloader/blob/master/license)，yt-dlp 使用 [Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE)。
