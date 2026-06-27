# x-download

基于 yt-dlp 的网页版视频下载工具，支持 YouTube、抖音、B站、Twitter 等主流平台。

## 功能特性 / Features

- 🎬 支持多平台视频下载 / Multi-platform video download
- 🎨 简洁的网页界面 / Clean web interface
- ⚡ 自动选择最佳画质 / Auto-select best quality
- 🗂️ 自动清理旧文件 / Auto cleanup old files
- 📱 响应式设计，支持手机访问 / Responsive design
- 🔄 实时显示下载进度 / Real-time download progress
- 🌐 支持中英文界面 / Bilingual UI (Chinese/English)

## 快速安装 / Quick Install

### 一键安装 / One-click Install

```bash
curl -fsSL https://raw.githubusercontent.com/Angasky/x-download/main/install.sh | bash
```

或下载后运行 / Or download and run:

```bash
git clone https://github.com/Angasky/x-download.git
cd x-download
bash install.sh
```

### 手动安装 / Manual Install

```bash
# 1. 安装依赖 / Install dependencies
apt-get update
apt-get install -y python3 python3-pip python3-venv ffmpeg

# 2. 克隆项目 / Clone project
git clone https://github.com/Angasky/x-download.git
cd x-download

# 3. 安装 yt-dlp / Install yt-dlp
pip3 install yt-dlp

# 4. 运行服务 / Run service
python3 app.py
```

## 配置说明 / Configuration

安装过程中会询问以下配置 / The installer will ask for:

<!-- INSTALL_CONFIG_START -->
安装端口 / Install Port: 8080
最大保留视频数 / Max Files: 50
安装目录 / Install Dir: /opt/x-download
Nginx反向代理 / Nginx Reverse Proxy: 否
<!-- INSTALL_CONFIG_END -->

## 使用说明 / Usage

1. 在浏览器中访问服务地址（默认 http://服务器IP:8080）/ Access in browser (default http://server-ip:8080)
2. 粘贴视频链接 / Paste video URL
3. 点击"获取信息"查看视频详情 / Click "Get Info" to view details
4. 选择画质，点击"开始下载" / Select quality and click "Start Download"
5. 下载完成后自动保存到服务器 / Files auto-saved to server after download

## 支持平台 / Supported Platforms

- YouTube
- 抖音 / Douyin
- B站（哔哩哔哩）/ Bilibili
- Twitter / X
- Instagram
- TikTok
- 更多平台（yt-dlp 支持的所有平台）/ More (all yt-dlp supported platforms)

## 服务管理 / Service Management

```bash
# 启动服务 / Start service
systemctl start x-download

# 停止服务 / Stop service
systemctl stop x-download

# 重启服务 / Restart service
systemctl restart x-download

# 查看状态 / Check status
systemctl status x-download

# 查看日志 / View logs
journalctl -u x-download -f
```

## 环境变量 / Environment Variables

在 `.env` 文件中可以配置 / Configure in `.env`:

| 变量名 / Variable | 说明 / Description | 默认值 / Default |
|-------------------|---------------------|------------------|
| PORT | 服务端口 / Service port | 8080 |
| MAX_FILES | 最大保留文件数 / Max files to keep | 50 |
| DOWNLOAD_DIR | 下载目录 / Download directory | /opt/x-download/downloads |
| LANG | 界面语言 / UI language | zh |

## 注意事项 / Notes

- 请确保服务器已安装 ffmpeg / Make sure ffmpeg is installed
- 下载目录需要有足够磁盘空间 / Ensure enough disk space for downloads
- 建议使用 systemd 管理服务，实现开机自启 / Use systemd for auto-start on boot
- 如遇下载失败，请检查视频链接是否有效 / If download fails, check if URL is valid
- 请遵守当地法律法规，仅下载您有权下载的内容 / Comply with local laws, only download content you have rights to

## 技术栈 / Tech Stack

- **后端**: Python + Flask / Backend: Python + Flask
- **下载引擎**: yt-dlp / Download engine: yt-dlp
- **前端**: HTML + CSS + JavaScript / Frontend: HTML + CSS + JavaScript
- **服务管理**: systemd / Service management: systemd

## 许可证 / License

MIT License
