# x-download

基于 yt-dlp 的网页版视频下载工具，支持 YouTube、抖音、B站、Twitter 等主流平台。

## 功能特性

- 🎬 支持多平台视频下载
- 🎨 简洁的网页界面
- ⚡ 自动选择最佳画质
- 🗂️ 自动清理旧文件
- 📱 响应式设计，支持手机访问
- 🔄 实时显示下载进度

## 快速安装

### 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/Angasky/x-download/main/install.sh | bash
```

或下载后运行：

```bash
git clone https://github.com/Angasky/x-download.git
cd x-download
bash install.sh
```

### 手动安装

```bash
# 1. 安装依赖
apt-get update
apt-get install -y python3 python3-pip python3-venv ffmpeg

# 2. 克隆项目
git clone https://github.com/Angasky/x-download.git
cd x-download

# 3. 安装 yt-dlp
pip3 install yt-dlp

# 4. 运行服务
python3 app.py
```

## 配置说明

安装过程中会询问以下配置：

<!-- INSTALL_CONFIG_START -->
安装端口: 8080
最大保留视频数: 50
安装目录: /opt/x-download
Nginx反向代理: 否
<!-- INSTALL_CONFIG_END -->

## 使用说明

1. 在浏览器中访问服务地址（默认 http://服务器IP:8080）
2. 粘贴视频链接
3. 点击"获取信息"查看视频详情
4. 选择画质，点击"开始下载"
5. 下载完成后自动保存到服务器

## 支持平台

- YouTube
- 抖音
- B站（哔哩哔哩）
- Twitter / X
- Instagram
- TikTok
- 更多平台（yt-dlp 支持的所有平台）

## 服务管理

```bash
# 启动服务
systemctl start x-download

# 停止服务
systemctl stop x-download

# 重启服务
systemctl restart x-download

# 查看状态
systemctl status x-download

# 查看日志
journalctl -u x-download -f
```

## 环境变量

在 `.env` 文件中可以配置：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| PORT | 服务端口 | 8080 |
| MAX_FILES | 最大保留文件数 | 50 |
| DOWNLOAD_DIR | 下载目录 | /opt/x-download/downloads |

## 注意事项

- 请确保服务器已安装 ffmpeg
- 下载目录需要有足够磁盘空间
- 建议使用 systemd 管理服务，实现开机自启
- 如遇下载失败，请检查视频链接是否有效

## 技术栈

- **后端**: Python + Flask
- **下载引擎**: yt-dlp
- **前端**: HTML + CSS + JavaScript
- **服务管理**: systemd

## 许可证

MIT License

---

**注意**: 请遵守当地法律法规，仅下载您有权下载的内容。本工具仅供学习交流使用。
