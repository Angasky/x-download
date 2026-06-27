# ⬇️ x-download

**yt-dlp 視頻下載服務 / Video Downloader Web API**

一個輕量級、易於部署的視頻下載 Web 服務，支持 YouTube、Bilibili、Twitter/X、TikTok、抖音等主流平台。

A lightweight, easy-to-deploy video download web service supporting YouTube, Bilibili, Twitter/X, TikTok, Douyin, and more.

---

## ✨ 特性 / Features

- 🚀 **一鍵安裝** / One-click install
- 🌐 **多平台支持** / Multi-platform: YouTube, Bilibili, Twitter, TikTok, Douyin...
- 🧹 **自動清理** / Auto-cleanup: keeps latest N files
- 🌍 **中英雙文界面** / Bilingual UI (中文為主 / Chinese primary)
- 📱 **響應式設計** / Responsive design
- 🔄 **後台下載** / Background downloads with real-time status
- ⚙️ **環境變量配置** / Environment variable based config

---

## 🚀 快速開始 / Quick Start

```bash
# 1. Clone 倉庫 / Clone repository
git clone git@github.com:Angasky/x-download.git
cd x-download

# 2. 一鍵安裝 / One-click install
chmod +x install.sh
./install.sh
```

安裝向導會詢問以下配置 / The installer will ask for:

- 服務端口 / Service port (默認 / default: `8080`)
- 最大保留文件數 / Max files to keep (默認 / default: `50`)
- 安裝目錄 / Install directory (默認 / default: `/opt/x-download`)
- 是否安裝 Nginx 反向代理 / Install Nginx reverse proxy

---

## 📋 系統要求 / Requirements

- Linux (Debian/Ubuntu/CentOS/RHEL)
- Python 3.8+
- ffmpeg
- 2GB+ RAM (推薦 / recommended)

---

## 🔧 配置說明 / Configuration

安裝完成後，配置文件位於 / After installation, config file is at:

```bash
/opt/x-download/.env
```

### 環境變量 / Environment Variables

| 變量 / Variable | 說明 / Description | 默認值 / Default |
|----------------|-------------------|-----------------|
| `PORT` | 服務端口 / Service port | `8080` |
| `MAX_FILES` | 最大保留文件數 / Max files to retain | `50` |
| `DOWNLOAD_DIR` | 下載文件存儲路徑 / Download directory | `/opt/x-download/downloads` |
| `LANG` | 界面語言 / Interface language | `zh` |

修改配置後重啟服務 / Restart after changes:

```bash
sudo systemctl restart x-download
```

---

## 🛠️ 管理命令 / Management

```bash
# 查看狀態 / Check status
sudo systemctl status x-download

# 重啟服務 / Restart
sudo systemctl restart x-download

# 查看日誌 / View logs
sudo journalctl -u x-download -f

# 停止服務 / Stop
sudo systemctl stop x-download
```

---

## 📁 項目結構 / Project Structure

```
x-download/
├── install.sh          # 一鍵安裝腳本 / One-click installer
├── app.py              # Flask Web API 後端 / Backend
├── .env.example        # 環境變量示例 / Env example
├── templates/
│   └── index.html      # 前端頁面 / Frontend
├── static/
│   └── style.css       # 樣式文件 / Styles
├── downloads/          # 下載文件存儲目錄 / Download storage
├── README.md           # 英文文檔 / English docs
└── README_CN.md        # 中文文檔 / Chinese docs
```

---

## 🌐 支持的平台 / Supported Platforms

| 平台 / Platform | 示例 / Example |
|----------------|---------------|
| YouTube | `https://www.youtube.com/watch?v=...` |
| Bilibili | `https://www.bilibili.com/video/...` |
| Twitter/X | `https://x.com/user/status/...` |
| TikTok | `https://www.tiktok.com/@user/video/...` |
| 抖音 | `https://www.douyin.com/video/...` |

更多平台請參見 [yt-dlp 支持站點列表](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)

---

## 📝 安裝記錄 / Installation Log

> 以下為最近一次安裝時自動更新的配置信息 / Auto-updated on last install.

<!-- INSTALL_CONFIG_START -->
端口 / Port: 8080  
最大保留文件數 / Max Files: 50  
安裝目錄 / Install Dir: /opt/x-download  
Nginx 反向代理 / Nginx Reverse Proxy: false
<!-- INSTALL_CONFIG_END -->

---

## 📄 License

MIT

---

## 🤝 Contributing

PRs and issues are welcome!

---

<p align="center">Made with ❤️ by <a href="https://github.com/Angasky">Angasky</a></p>
