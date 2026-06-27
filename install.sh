#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# x-download 一鍵安裝腳本 / One-click installer
# 中英雙文 / Bilingual (中文為主 / Chinese primary)
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
README_FILE="${SCRIPT_DIR}/README.md"

# 默認值 / Defaults
DEFAULT_PORT=8080
DEFAULT_MAX_FILES=50
DEFAULT_INSTALL_DIR="/opt/x-download"

# ============================================================
# 系統檢測 / System Detection
# ============================================================
echo ""
echo -e "\033[1;34m正在檢測系統環境... / Detecting system environment...\033[0m"

if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    OS="${ID:-unknown}"
    VER="${VERSION_ID:-unknown}"
    echo -e "\033[1;32m檢測到操作系統 / Detected OS: ${PRETTY_NAME:-$OS $VER}\033[0m"
else
    echo -e "\033[1;33m警告：無法檢測操作系統，假設為 Debian/Ubuntu。 / Warning: Cannot detect OS. Assuming Debian/Ubuntu.\033[0m"
    OS="debian"
fi

# ============================================================
# 收集用戶輸入 / Collect User Input
# ============================================================
echo ""
echo -e "\033[1;36m--- 配置選項 / Configuration ---\033[0m"

# Port
while true; do
    read -p "請輸入服務端口 / Enter service port (默認/default: $DEFAULT_PORT): " input_port
    if [[ -z "$input_port" ]]; then
        PORT=$DEFAULT_PORT
        break
    elif [[ "$input_port" =~ ^[0-9]+$ ]] && (( input_port >= 1 && input_port <= 65535 )); then
        PORT=$input_port
        break
    else
        echo -e "\033[1;31m輸入無效，請重新輸入 / Invalid input, please retry\033[0m"
    fi
done
echo "  端口 / Port: $PORT"

# Max files
while true; do
    read -p "請輸入最大保留文件數 / Enter max files to keep (默認/default: $DEFAULT_MAX_FILES): " input_max
    if [[ -z "$input_max" ]]; then
        MAX_FILES=$DEFAULT_MAX_FILES
        break
    elif [[ "$input_max" =~ ^[0-9]+$ ]] && (( input_max >= 1 )); then
        MAX_FILES=$input_max
        break
    else
        echo -e "\033[1;31m輸入無效，請重新輸入 / Invalid input, please retry\033[0m"
    fi
done
echo "  最大保留文件數 / Max files: $MAX_FILES"

# Install directory
while true; do
    read -p "請輸入安裝目錄 / Enter install directory (默認/default: $DEFAULT_INSTALL_DIR): " input_dir
    if [[ -z "$input_dir" ]]; then
        INSTALL_DIR=$DEFAULT_INSTALL_DIR
        break
    elif [[ -d "$input_dir" ]]; then
        echo -e "\033[1;33m目錄已存在，將使用現有目錄 / Directory exists, will use existing directory\033[0m"
        INSTALL_DIR="$input_dir"
        break
    elif [[ -w "$(dirname "$input_dir")" ]] || [[ "$(dirname "$input_dir")" == "/" ]]; then
        INSTALL_DIR="$input_dir"
        break
    else
        echo -e "\033[1;31m輸入無效，請重新輸入 / Invalid input, please retry\033[0m"
    fi
done
echo "  安裝目錄 / Install dir: $INSTALL_DIR"

# Nginx
while true; do
    read -p "是否安裝 Nginx 反向代理? / Install Nginx reverse proxy? (y/N, 默認/default N): " input_nginx
    case "${input_nginx,,}" in
        y|yes|是)
            USE_NGINX=true
            break
            ;;
        *)
            USE_NGINX=false
            break
            ;;
    esac
done
if $USE_NGINX; then
    echo "  Nginx 反向代理 / Nginx reverse proxy: 是 / Yes"
else
    echo "  Nginx 反向代理 / Nginx reverse proxy: 跳過 / Skip"
fi

echo ""
read -p "按 Enter 繼續... / Press Enter to continue..."

# ============================================================
# 安裝依賴 / Install Dependencies
# ============================================================
echo ""
echo -e "\033[1;34m正在安裝依賴包... / Installing dependencies...\033[0m"

if [[ "$OS" =~ ^(ubuntu|debian)$ ]] || [[ "$OS" == "linuxmint" ]] || [[ "$OS" == "pop" ]]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-flask ffmpeg yt-dlp nginx curl > /dev/null 2>&1 || {
        apt-get install -y python3 python3-pip python3-flask ffmpeg yt-dlp nginx curl
    }
    echo -e "\033[1;32m✓ 依賴安裝完成 / Dependencies installed\033[0m"
elif [[ "$OS" =~ ^(centos|rhel|fedora)$ ]]; then
    if command -v dnf &>/dev/null; then
        dnf install -y python3 python3-pip python3-flask ffmpeg yt-dlp nginx curl
    else
        yum install -y python3 python3-pip python3-flask ffmpeg yt-dlp nginx curl
    fi
    echo -e "\033[1;32m✓ 依賴安裝完成 / Dependencies installed\033[0m"
else
    echo -e "\033[1;33m不支持的操作系統: $OS / Unsupported OS. 請手動安裝 python3, flask, yt-dlp, ffmpeg, nginx / Please install manually.\033[0m"
fi

# ============================================================
# 部署應用 / Deploy Application
# ============================================================
echo ""
echo -e "\033[1;34m正在創建目錄... / Creating directories...\033[0m"

mkdir -p "${INSTALL_DIR}/downloads"
mkdir -p "${INSTALL_DIR}/static"
mkdir -p "${INSTALL_DIR}/templates"

# 複製文件 / Copy files
cp -f "${SCRIPT_DIR}/app.py" "${INSTALL_DIR}/app.py"
cp -f "${SCRIPT_DIR}/templates/index.html" "${INSTALL_DIR}/templates/index.html" 2>/dev/null || true
cp -f "${SCRIPT_DIR}/static/style.css" "${INSTALL_DIR}/static/style.css" 2>/dev/null || true

# ============================================================
# 生成 .env / Generate .env
# ============================================================
echo ""
echo -e "\033[1;34m正在生成 .env 文件... / Generating .env file...\033[0m"

cat > "${INSTALL_DIR}/.env" <<EOF
# x-download 配置 / Configuration
# 自動生成於 / Auto-generated at $(date)
LANG=zh
PORT=${PORT}
MAX_FILES=${MAX_FILES}
DOWNLOAD_DIR=${INSTALL_DIR}/downloads
EOF

chmod 644 "${INSTALL_DIR}/.env"
echo -e "\033[1;32m✓ .env 已創建於 / .env created at ${INSTALL_DIR}/.env\033[0m"

# ============================================================
# Systemd Service
# ============================================================
echo ""
echo -e "\033[1;34m正在生成 systemd 服務文件... / Generating systemd service file...\033[0m"

SERVICE_NAME="x-download"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=x-download Web API
After=network.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.service" > /dev/null 2>&1 || {
    echo -e "\033[1;31m服務啟動失敗，請檢查日誌 / Service failed to start, check logs\033[0m"
    journalctl -u "${SERVICE_NAME}.service" -n 20 --no-pager || true
    exit 1
}

sleep 2
if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
    echo -e "\033[1;32m✓ 服務已啟動並運行 / Service started and running\033[0m"
else
    echo -e "\033[1;33m⚠ 服務可能仍在啟動中... / Service may still be starting...\033[0m"
fi

# ============================================================
# Nginx Reverse Proxy
# ============================================================
if $USE_NGINX; then
    echo ""
    echo -e "\033[1;34m正在配置 Nginx 反向代理... / Configuring Nginx reverse proxy...\033[0m"
    
    DOMAIN="${INSTALL_DIR#/opt/}"
    NGINX_CONF="/etc/nginx/sites-available/x-download"
    NGINX_ENABLED="/etc/nginx/sites-enabled/x-download"
    
    sudo tee "$NGINX_CONF" > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

    ln -sf "$NGINX_CONF" "$NGINX_ENABLED"
    nginx -t && systemctl reload nginx
    echo -e "\033[1;32m✓ Nginx 已配置 / Nginx configured on port 80 -> ${PORT}\033[0m"
fi

# ============================================================
# 更新 README / Update README
# ============================================================
echo ""
echo -e "\033[1;34m正在更新 README.md... / Updating README.md...\033[0m"

if [[ -f "$README_FILE" ]]; then
    sed -i.bak "/INSTALL_CONFIG_START/,/INSTALL_CONFIG_END/{
        s|端口 / Port: .*|端口 / Port: ${PORT}  |
        s|最大保留文件數 / Max Files: .*|最大保留文件數 / Max Files: ${MAX_FILES}  |
        s|安裝目錄 / Install Dir: .*|安裝目錄 / Install Dir: ${INSTALL_DIR}  |
        s|Nginx 反向代理 / Nginx Reverse Proxy: .*|Nginx 反向代理 / Nginx Reverse Proxy: ${USE_NGINX}  |
    }" "$README_FILE" || true
    rm -f "${README_FILE}.bak"
    echo -e "\033[1;32m✓ README.md 已更新 / README.md updated\033[0m"
fi

# ============================================================
# 完成 / Completion
# ============================================================
echo ""
echo -e "\033[1;32m========================================\033[0m"
echo -e "\033[1;32m  安裝完成！ / Installation complete!\033[0m"
echo -e "\033[1;32m========================================\033[0m"
echo ""
if $USE_NGINX; then
    echo -e "訪問地址 / Access URL: \033[1;36mhttp://<your-server-ip>/\033[0m"
else
    echo -e "訪問地址 / Access URL: \033[1;36mhttp://<your-server-ip>:${PORT}/\033[0m"
fi
echo ""
echo -e "管理命令 / Admin commands:"
echo -e "  查看狀態 / Check status: \033[1;33msystemctl status ${SERVICE_NAME}\033[0m"
echo -e "  重啟服務 / Restart: \033[1;33msystemctl restart ${SERVICE_NAME}\033[0m"
echo -e "  查看日誌 / View logs: \033[1;33mjournalctl -u ${SERVICE_NAME} -f\033[0m"
echo ""
echo -e "注意 / Note:"
echo -e "  配置文件 / Config: \033[1;33m${INSTALL_DIR}/.env\033[0m"
echo -e "  下載目錄 / Downloads: \033[1;33m${INSTALL_DIR}/downloads\033[0m"
echo -e "  修改配置後請重啟服務 / Restart after changes: \033[1;33msystemctl restart ${SERVICE_NAME}\033[0m"
echo ""
echo -e "\033[1;32m✓ 配置已保存 / Configuration saved: port=${PORT}, max_files=${MAX_FILES}, dir=${INSTALL_DIR}\033[0m"
echo ""
