#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# x-download 一鍵安裝腳本
# One-click installer for yt-dlp Web API
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/.env"
README_FILE="${SCRIPT_DIR}/README.md"

# 默認值 / Defaults
DEFAULT_PORT=8080
DEFAULT_MAX_FILES=50
DEFAULT_INSTALL_DIR="/opt/x-download"
DEFAULT_LANG="zh"

# ============================================================
# 語言設置 / Language Selection
# ============================================================
echo "========================================"
echo "  x-download 安裝向導"
echo "  x-download Installer"
echo "========================================"
echo ""
echo "請選擇語言 / Please select language:"
echo "  1) 简体中文"
echo "  2) English"
echo ""
read -p "輸入選擇 / Enter choice [1-2, 默認/default: 1]: " lang_choice
lang_choice="${lang_choice:-1}"

if [[ "$lang_choice" == "2" ]]; then
    LANG="en"
else
    LANG="zh"
fi

# 語言包 / i18n strings
if [[ "$LANG" == "zh" ]]; then
    MSG_DETECTING="正在檢測系統環境..."
    MSG_OS_DETECTED="檢測到操作系統:"
    MSG_INSTALL_DEPS="正在安裝依賴包..."
    MSG_ASK_PORT="請輸入服務端口 (默認: $DEFAULT_PORT):"
    MSG_ASK_MAX="請輸入最大保留文件數 (默認: $DEFAULT_MAX_FILES):"
    MSG_ASK_DIR="請輸入安裝目錄 (默認: $DEFAULT_INSTALL_DIR):"
    MSG_ASK_NGINX="是否安裝 Nginx 反向代理? (y/N, 默認 N):"
    MSG_CREATE_DIR="正在創建目錄..."
    MSG_GEN_SERVICE="正在生成 systemd 服務文件..."
    MSG_ENABLE_SVC="正在啟用並啟動服務..."
    MSG_UPDATE_README="正在更新 README.md..."
    MSG_UPDATE_ENV="正在生成 .env 文件..."
    MSG_DONE="安裝完成！"
    MSG_ACCESS="訪問地址:"
    MSG_ADMIN="管理命令:"
    MSG_NOTE="注意:"
    MSG_PORT="端口"
    MSG_FILES="最大保留文件數"
    MSG_DIR="安裝目錄"
    MSG_NGINX="Nginx 反向代理"
    MSG_SKIP_NGINX="跳過 Nginx"
    MSG_YES="是"
    MSG_NO="否"
    MSG_CONFIG_SAVED="配置已保存"
    MSG_PRESS_ENTER="按 Enter 繼續..."
    MSG_INVALID_INPUT="輸入無效，請重新輸入"
    MSG_DIR_EXISTS="目錄已存在，將使用現有目錄"
    MSG_SVC_ACTIVE="服務已啟動並運行"
    MSG_SVC_FAILED="服務啟動失敗，請檢查日誌"
else
    MSG_DETECTING="Detecting system environment..."
    MSG_OS_DETECTED="Detected OS:"
    MSG_INSTALL_DEPS="Installing dependencies..."
    MSG_ASK_PORT="Enter service port (default: $DEFAULT_PORT):"
    MSG_ASK_MAX="Enter max files to keep (default: $DEFAULT_MAX_FILES):"
    MSG_ASK_DIR="Enter install directory (default: $DEFAULT_INSTALL_DIR):"
    MSG_ASK_NGINX="Install Nginx reverse proxy? (y/N, default N):"
    MSG_CREATE_DIR="Creating directories..."
    MSG_GEN_SERVICE="Generating systemd service file..."
    MSG_ENABLE_SVC="Enabling and starting service..."
    MSG_UPDATE_README="Updating README.md..."
    MSG_UPDATE_ENV="Generating .env file..."
    MSG_DONE="Installation complete!"
    MSG_ACCESS="Access URL:"
    MSG_ADMIN="Admin commands:"
    MSG_NOTE="Note:"
    MSG_PORT="Port"
    MSG_FILES="Max files"
    MSG_DIR="Install dir"
    MSG_NGINX="Nginx reverse proxy"
    MSG_SKIP_NGINX="Skip Nginx"
    MSG_YES="Yes"
    MSG_NO="No"
    MSG_CONFIG_SAVED="Configuration saved"
    MSG_PRESS_ENTER="Press Enter to continue..."
    MSG_INVALID_INPUT="Invalid input, please retry"
    MSG_DIR_EXISTS="Directory exists, will use existing directory"
    MSG_SVC_ACTIVE="Service started and running"
    MSG_SVC_FAILED="Service failed to start, check logs"
fi

# ============================================================
# 系統檢測 / System Detection
# ============================================================
echo ""
echo -e "\033[1;34m${MSG_DETECTING}\033[0m"

if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    OS="${ID:-unknown}"
    VER="${VERSION_ID:-unknown}"
    echo -e "\033[1;32m${MSG_OS_DETECTED} ${PRETTY_NAME:-$OS $VER}\033[0m"
else
    echo -e "\033[1;33mWarning: Cannot detect OS. Assuming Debian/Ubuntu.\033[0m"
    OS="debian"
fi

# ============================================================
# 收集用戶輸入 / Collect User Input
# ============================================================
echo ""
echo -e "\033[1;36m--- Configuration / 配置 ---\033[0m"

# Port
while true; do
    read -p "$MSG_ASK_PORT " input_port
    if [[ -z "$input_port" ]]; then
        PORT=$DEFAULT_PORT
        break
    elif [[ "$input_port" =~ ^[0-9]+$ ]] && (( input_port >= 1 && input_port <= 65535 )); then
        PORT=$input_port
        break
    else
        echo -e "\033[1;31m${MSG_INVALID_INPUT}\033[0m"
    fi
done
echo "  ${MSG_PORT}: $PORT"

# Max files
while true; do
    read -p "$MSG_ASK_MAX " input_max
    if [[ -z "$input_max" ]]; then
        MAX_FILES=$DEFAULT_MAX_FILES
        break
    elif [[ "$input_max" =~ ^[0-9]+$ ]] && (( input_max >= 1 )); then
        MAX_FILES=$input_max
        break
    else
        echo -e "\033[1;31m${MSG_INVALID_INPUT}\033[0m"
    fi
done
echo "  ${MSG_FILES}: $MAX_FILES"

# Install directory
while true; do
    read -p "$MSG_ASK_DIR " input_dir
    if [[ -z "$input_dir" ]]; then
        INSTALL_DIR=$DEFAULT_INSTALL_DIR
        break
    elif [[ -d "$input_dir" ]]; then
        echo -e "\033[1;33m${MSG_DIR_EXISTS}\033[0m"
        INSTALL_DIR="$input_dir"
        break
    elif [[ -w "$(dirname "$input_dir")" ]] || [[ "$(dirname "$input_dir")" == "/" ]]; then
        INSTALL_DIR="$input_dir"
        break
    else
        echo -e "\033[1;31m${MSG_INVALID_INPUT}\033[0m"
    fi
done
echo "  ${MSG_DIR}: $INSTALL_DIR"

# Nginx
while true; do
    read -p "$MSG_ASK_NGINX " input_nginx
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
    echo "  ${MSG_NGINX}: ${MSG_YES}"
else
    echo "  ${MSG_NGINX}: ${MSG_SKIP_NGINX}"
fi

echo ""
read -p "${MSG_PRESS_ENTER}"

# ============================================================
# 安裝依賴 / Install Dependencies
# ============================================================
echo ""
echo -e "\033[1;34m${MSG_INSTALL_DEPS}\033[0m"

if [[ "$OS" =~ ^(ubuntu|debian)$ ]] || [[ "$OS" == "linuxmint" ]] || [[ "$OS" == "pop" ]]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-flask ffmpeg yt-dlp nginx curl > /dev/null 2>&1 || {
        # 個別安裝以防某個已存在
        apt-get install -y python3 python3-pip python3-flask ffmpeg yt-dlp nginx curl
    }
    echo -e "\033[1;32m✓ Dependencies installed\033[0m"
elif [[ "$OS" =~ ^(centos|rhel|fedora)$ ]]; then
    if command -v dnf &>/dev/null; then
        dnf install -y python3 python3-pip python3-flask ffmpeg yt-dlp nginx curl
    else
        yum install -y python3 python3-pip python3-flask ffmpeg yt-dlp nginx curl
    fi
    echo -e "\033[1;32m✓ Dependencies installed\033[0m"
else
    echo -e "\033[1;33mUnsupported OS: $OS. Please install python3, flask, yt-dlp, ffmpeg, nginx manually.\033[0m"
fi

# ============================================================
# 部署應用 / Deploy Application
# ============================================================
echo ""
echo -e "\033[1;34m${MSG_CREATE_DIR}\033[0m"

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
echo -e "\033[1;34m${MSG_UPDATE_ENV}\033[0m"

cat > "${INSTALL_DIR}/.env" <<EOF
# x-download Configuration
# 自動生成於 $(date)
LANG=${LANG}
PORT=${PORT}
MAX_FILES=${MAX_FILES}
DOWNLOAD_DIR=${INSTALL_DIR}/downloads
EOF

chmod 644 "${INSTALL_DIR}/.env"
echo -e "\033[1;32m✓ .env created at ${INSTALL_DIR}/.env\033[0m"

# ============================================================
# Systemd Service
# ============================================================
echo ""
echo -e "\033[1;34m${MSG_GEN_SERVICE}\033[0m"

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
    echo -e "\033[1;31m${MSG_SVC_FAILED}\033[0m"
    journalctl -u "${SERVICE_NAME}.service" -n 20 --no-pager || true
    exit 1
}

sleep 2
if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
    echo -e "\033[1;32m✓ ${MSG_SVC_ACTIVE}\033[0m"
else
    echo -e "\033[1;33m⚠ Service may still be starting...\033[0m"
fi

# ============================================================
# Nginx Reverse Proxy
# ============================================================
if $USE_NGINX; then
    echo ""
    echo -e "\033[1;34mConfiguring Nginx reverse proxy...\033[0m"
    
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
    echo -e "\033[1;32m✓ Nginx configured on port 80 -> ${PORT}\033[0m"
fi

# ============================================================
# 更新 README / Update README
# ============================================================
echo ""
echo -e "\033[1;34m${MSG_UPDATE_README}\033[0m"

if [[ -f "$README_FILE" ]]; then
    # 使用 sed 更新配置值 / Use sed to update config values inside markers
    if [[ "$LANG" == "zh" ]]; then
        sed -i.bak "/INSTALL_CONFIG_START/,/INSTALL_CONFIG_END/{
            s|端口 / Port: .*|端口 / Port: ${PORT}  |
            s|最大保留文件數 / Max Files: .*|最大保留文件數 / Max Files: ${MAX_FILES}  |
            s|安裝目錄 / Install Dir: .*|安裝目錄 / Install Dir: ${INSTALL_DIR}  |
            s|Nginx 反向代理 / Nginx Reverse Proxy: .*|Nginx 反向代理 / Nginx Reverse Proxy: ${USE_NGINX}  |
        }" "$README_FILE" || true
    else
        sed -i.bak "/INSTALL_CONFIG_START/,/INSTALL_CONFIG_END/{
            s|Port: .*|Port: ${PORT}  |
            s|Max Files: .*|Max Files: ${MAX_FILES}  |
            s|Install Dir: .*|Install Dir: ${INSTALL_DIR}  |
            s|Nginx Reverse Proxy: .*|Nginx Reverse Proxy: ${USE_NGINX}  |
        }" "$README_FILE" || true
    fi
    rm -f "${README_FILE}.bak"
    echo -e "\033[1;32m✓ README.md updated\033[0m"
fi

# ============================================================
# 完成 / Completion
# ============================================================
echo ""
echo -e "\033[1;32m========================================\033[0m"
echo -e "\033[1;32m  ${MSG_DONE}\033[0m"
echo -e "\033[1;32m========================================\033[0m"
echo ""
if $USE_NGINX; then
    echo -e "${MSG_ACCESS}: \033[1;36mhttp://<your-server-ip>/\033[0m"
else
    echo -e "${MSG_ACCESS}: \033[1;36mhttp://<your-server-ip>:${PORT}/\033[0m"
fi
echo ""
echo -e "${MSG_ADMIN}:"
echo -e "  查看狀態: \033[1;33msystemctl status ${SERVICE_NAME}\033[0m"
echo -e "  重啟服務: \033[1;33msystemctl restart ${SERVICE_NAME}\033[0m"
echo -e "  查看日誌: \033[1;33mjournalctl -u ${SERVICE_NAME} -f\033[0m"
echo ""
echo -e "${MSG_NOTE}:"
echo -e "  配置文件: \033[1;33m${INSTALL_DIR}/.env\033[0m"
echo -e "  下載目錄: \033[1;33m${INSTALL_DIR}/downloads\033[0m"
echo -e "  修改配置後請重啟服務: \033[1;33msystemctl restart ${SERVICE_NAME}\033[0m"
echo ""
echo -e "\033[1;32m✓ ${MSG_CONFIG_SAVED}: port=${PORT}, max_files=${MAX_FILES}, dir=${INSTALL_DIR}\033[0m"
echo ""
