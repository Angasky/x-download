#!/bin/bash
set -e

# ============================================
# x-download 一键安装脚本 / One-click Installer
# ============================================

echo "=============================="
echo "   x-download 安装程序 / Installer"
echo "=============================="
echo ""

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检查 root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用 root 权限运行此脚本 / Please run as root${NC}"
    echo "请使用: sudo bash install.sh"
    exit 1
fi

# 语言选择
echo "请选择语言 / Please select language:"
echo "1) 简体中文"
echo "2) English"
read -p "输入选项 / Enter choice [默认: 1]: " LANG_CHOICE
LANG_CHOICE=${LANG_CHOICE:-1}

if [ "$LANG_CHOICE" = "2" ]; then
    LANG="en"
else
    LANG="zh"
fi

# 中文提示
zh_prompt() {
    echo -e "${YELLOW}$1${NC}"
}
zh_success() {
    echo -e "${GREEN}✓ $1${NC}"
}
zh_error() {
    echo -e "${RED}✗ $1${NC}"
}

# English prompts
en_prompt() {
    echo -e "${YELLOW}$1${NC}"
}
en_success() {
    echo -e "${GREEN}✓ $1${NC}"
}
en_error() {
    echo -e "${RED}✗ $1${NC}"
}

prompt() {
    if [ "$LANG" = "en" ]; then
        en_prompt "$1"
    else
        zh_prompt "$1"
    fi
}

success() {
    if [ "$LANG" = "en" ]; then
        en_success "$1"
    else
        zh_success "$1"
    fi
}

error() {
    if [ "$LANG" = "en" ]; then
        en_error "$1"
    else
        zh_error "$1"
    fi
}

# 询问安装目录
if [ "$LANG" = "en" ]; then
    read -p "Enter install directory [default: /opt/x-download]: " INSTALL_DIR
else
    read -p "请输入安装目录 [默认: /opt/x-download]: " INSTALL_DIR
fi
INSTALL_DIR=${INSTALL_DIR:-/opt/x-download}

# 询问端口
if [ "$LANG" = "en" ]; then
    read -p "Enter service port [default: 8080]: " PORT
else
    read -p "请输入服务端口 [默认: 8080]: " PORT
fi
PORT=${PORT:-8080}

# 询问最大保留视频数
if [ "$LANG" = "en" ]; then
    read -p "Enter max files to keep [default: 50]: " MAX_FILES
else
    read -p "请输入最大保留视频数量 [默认: 50]: " MAX_FILES
fi
MAX_FILES=${MAX_FILES:-50}

# 询问是否安装 Nginx 反向代理
if [ "$LANG" = "en" ]; then
    read -p "Install Nginx reverse proxy? (y/n) [default: n]: " USE_NGINX
else
    read -p "是否安装 Nginx 反向代理？(y/n) [默认: n]: " USE_NGINX
fi
USE_NGINX=${USE_NGINX:-n}

echo ""
if [ "$LANG" = "en" ]; then
    echo "Installation configuration:"
    echo "  Install directory: $INSTALL_DIR"
    echo "  Service port: $PORT"
    echo "  Max files: $MAX_FILES"
    echo "  Nginx reverse proxy: $USE_NGINX"
else
    echo "安装配置:"
    echo "  安装目录: $INSTALL_DIR"
    echo "  服务端口: $PORT"
    echo "  最大保留视频数: $MAX_FILES"
    echo "  Nginx反向代理: $USE_NGINX"
fi
echo ""

if [ "$LANG" = "en" ]; then
    read -p "Confirm installation? (y/n): " CONFIRM
else
    read -p "确认安装？(y/n): " CONFIRM
fi
if [ "$CONFIRM" != "y" ]; then
    if [ "$LANG" = "en" ]; then
        echo "Installation cancelled"
    else
        echo "安装已取消"
    fi
    exit 0
fi

echo ""
if [ "$LANG" = "en" ]; then
    prompt "[1/5] Updating package list..."
else
    prompt "[1/5] 更新软件包列表..."
fi
apt-get update -qq

echo ""
if [ "$LANG" = "en" ]; then
    prompt "[2/5] Installing dependencies..."
else
    prompt "[2/5] 安装依赖软件..."
fi
apt-get install -y -qq python3 python3-pip python3-venv ffmpeg > /dev/null 2>&1
success "$(if [ "$LANG" = "en" ]; then echo 'Dependencies installed'; else echo '依赖软件安装完成'; fi)"

echo ""
if [ "$LANG" = "en" ]; then
    prompt "[3/5] Creating directories..."
else
    prompt "[3/5] 创建安装目录..."
fi
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/downloads"
mkdir -p "$INSTALL_DIR/static"
mkdir -p "$INSTALL_DIR/templates"
success "$(if [ "$LANG" = "en" ]; then echo 'Directories created'; else echo '目录创建完成'; fi)"

echo ""
if [ "$LANG" = "en" ]; then
    prompt "[4/5] Deploying application files..."
else
    prompt "[4/5] 部署程序文件..."
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 复制文件
cp "$SCRIPT_DIR/app.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/.env.example" "$INSTALL_DIR/.env"
cp -r "$SCRIPT_DIR/templates/"* "$INSTALL_DIR/templates/" 2>/dev/null || true
cp -r "$SCRIPT_DIR/static/"* "$INSTALL_DIR/static/" 2>/dev/null || true

# 创建 systemd 服务
cat > /etc/systemd/system/x-download.service << EOF
[Unit]
Description=x-download 视频下载服务 / Video Downloader
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/app.py
Restart=always
RestartSec=5
Environment="LANG=$LANG"

[Install]
WantedBy=multi-user.target
EOF

# 创建 .env 文件
cat > "$INSTALL_DIR/.env" << EOF
PORT=$PORT
MAX_FILES=$MAX_FILES
DOWNLOAD_DIR=$INSTALL_DIR/downloads
LANG=$LANG
EOF

success "$(if [ "$LANG" = "en" ]; then echo 'Files deployed'; else echo '程序文件部署完成'; fi)"

echo ""
if [ "$LANG" = "en" ]; then
    prompt "[5/5] Configuring service..."
else
    prompt "[5/5] 配置服务..."
fi
systemctl daemon-reload
systemctl enable x-download > /dev/null 2>&1
systemctl restart x-download
sleep 2

if systemctl is-active --quiet x-download; then
    success "$(if [ "$LANG" = "en" ]; then echo 'Service started successfully'; else echo '服务启动成功'; fi)"
else
    error "$(if [ "$LANG" = "en" ]; then echo 'Service failed to start, check logs: journalctl -u x-download'; else echo '服务启动失败，请检查日志: journalctl -u x-download'; fi)"
    exit 1
fi

# 配置 Nginx（可选）
if [ "$USE_NGINX" = "y" ] || [ "$USE_NGINX" = "Y" ]; then
    if [ "$LANG" = "en" ]; then
        prompt "Configuring Nginx reverse proxy..."
    else
        prompt "配置 Nginx 反向代理..."
    fi
    
    if ! command -v nginx &> /dev/null; then
        apt-get install -y -qq nginx > /dev/null 2>&1
    fi
    
    cat > /etc/nginx/sites-available/x-download << EOF
server {
    listen 80;
    server_name _;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

    ln -sf /etc/nginx/sites-available/x-download /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    
    nginx -t > /dev/null 2>&1 && systemctl reload nginx
    success "$(if [ "$LANG" = "en" ]; then echo 'Nginx configured'; else echo 'Nginx 配置完成'; fi)"
    echo -e "  $(if [ "$LANG" = "en" ]; then echo 'Access URL'; else echo '访问地址'; fi): http://$(hostname -I | awk '{print \$1}')"
else
    success "$(if [ "$LANG" = "en" ]; then echo 'Installation complete'; else echo '安装完成'; fi)"
    echo -e "  $(if [ "$LANG" = "en" ]; then echo 'Access URL'; else echo '访问地址'; fi): http://$(hostname -I | awk '{print \$1}'):$PORT"
fi

echo ""
echo "=============================="
echo -e "${GREEN}   $(if [ "$LANG" = "en" ]; then echo 'Installation Complete!'; else echo '安装完成！'; fi)${NC}"
echo "=============================="
if [ "$LANG" = "en" ]; then
    echo "Service management commands:"
    echo "  Start: systemctl start x-download"
    echo "  Stop: systemctl stop x-download"
    echo "  Restart: systemctl restart x-download"
    echo "  Status: systemctl status x-download"
    echo "  Logs: journalctl -u x-download -f"
else
    echo "服务管理命令:"
    echo "  启动: systemctl start x-download"
    echo "  停止: systemctl stop x-download"
    echo "  重启: systemctl restart x-download"
    echo "  状态: systemctl status x-download"
    echo "  日志: journalctl -u x-download -f"
fi
echo ""
echo "$(if [ "$LANG" = "en" ]; then echo 'Config file'; else echo '配置文件'; fi): $INSTALL_DIR/.env"
echo "$(if [ "$LANG" = "en" ]; then echo 'Download directory'; else echo '下载目录'; fi): $INSTALL_DIR/downloads"
echo ""

# 更新 README.md
README_FILE="$(dirname "$SCRIPT_DIR")/README.md"
if [ -f "$README_FILE" ]; then
    sed -i.bak "/INSTALL_CONFIG_START/,/INSTALL_CONFIG_END/{
        s|安装端口: .*|安装端口: $PORT  |
        s|最大保留视频数: .*|最大保留视频数: $MAX_FILES  |
        s|安装目录: .*|安装目录: $INSTALL_DIR  |
        s|Nginx反向代理: .*|Nginx反向代理: $USE_NGINX  |
        s|Installation Port: .*|Installation Port: $PORT  |
        s|Max Files: .*|Max Files: $MAX_FILES  |
        s|Install Dir: .*|Install Dir: $INSTALL_DIR  |
        s|Nginx Reverse Proxy: .*|Nginx Reverse Proxy: $USE_NGINX  |
    }" "$README_FILE" 2>/dev/null || true
    rm -f "${README_FILE}.bak" 2>/dev/null || true
    success "$(if [ "$LANG" = "en" ]; then echo 'README.md updated'; else echo 'README.md 已更新'; fi)"
fi
