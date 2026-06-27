#!/bin/bash
set -e

# ============================================
# x-download 一键安装脚本
# ============================================

echo "=============================="
echo "   x-download 安装程序"
echo "=============================="
echo ""

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检查 root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用 root 权限运行此脚本${NC}"
    echo "请使用: sudo bash install.sh"
    exit 1
fi

# 询问安装目录
read -p "请输入安装目录 [默认: /opt/x-download]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-/opt/x-download}

# 询问端口
read -p "请输入服务端口 [默认: 8080]: " PORT
PORT=${PORT:-8080}

# 询问最大保留视频数
read -p "请输入最大保留视频数量 [默认: 50]: " MAX_FILES
MAX_FILES=${MAX_FILES:-50}

# 询问是否安装 Nginx 反向代理
read -p "是否安装 Nginx 反向代理？(y/n) [默认: n]: " USE_NGINX
USE_NGINX=${USE_NGINX:-n}

echo ""
echo "安装配置:"
echo "  安装目录: $INSTALL_DIR"
echo "  服务端口: $PORT"
echo "  最大保留视频数: $MAX_FILES"
echo "  Nginx反向代理: $USE_NGINX"
echo ""

read -p "确认安装？(y/n): " CONFIRM
if [ "$CONFIRM" != "y" ]; then
    echo "安装已取消"
    exit 0
fi

echo ""
echo -e "${YELLOW}[1/5] 更新软件包列表...${NC}"
apt-get update -qq

echo -e "${YELLOW}[2/5] 安装依赖软件...${NC}"
apt-get install -y -qq python3 python3-pip python3-venv ffmpeg > /dev/null 2>&1
echo -e "${GREEN}✓ 依赖软件安装完成${NC}"

echo -e "${YELLOW}[3/5] 创建安装目录...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/downloads"
mkdir -p "$INSTALL_DIR/static"
mkdir -p "$INSTALL_DIR/templates"
echo -e "${GREEN}✓ 目录创建完成${NC}"

echo -e "${YELLOW}[4/5] 部署程序文件...${NC}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 复制文件
cp "$SCRIPT_DIR/app.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/.env.example" "$INSTALL_DIR/.env"
cp -r "$SCRIPT_DIR/templates/"* "$INSTALL_DIR/templates/" 2>/dev/null || true
cp -r "$SCRIPT_DIR/static/"* "$INSTALL_DIR/static/" 2>/dev/null || true

# 创建 systemd 服务
cat > /etc/systemd/system/x-download.service << EOF
[Unit]
Description=x-download 视频下载服务
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 创建 .env 文件
cat > "$INSTALL_DIR/.env" << EOF
PORT=$PORT
MAX_FILES=$MAX_FILES
DOWNLOAD_DIR=$INSTALL_DIR/downloads
EOF

echo -e "${GREEN}✓ 程序文件部署完成${NC}"

echo -e "${YELLOW}[5/5] 配置服务...${NC}"
systemctl daemon-reload
systemctl enable x-download > /dev/null 2>&1
systemctl restart x-download
sleep 2

if systemctl is-active --quiet x-download; then
    echo -e "${GREEN}✓ 服务启动成功${NC}"
else
    echo -e "${RED}✗ 服务启动失败，请检查日志: journalctl -u x-download${NC}"
    exit 1
fi

# 配置 Nginx（可选）
if [ "$USE_NGINX" = "y" ] || [ "$USE_NGINX" = "Y" ]; then
    echo -e "${YELLOW}配置 Nginx 反向代理...${NC}"
    
    # 检查 Nginx 是否已安装
    if ! command -v nginx &> /dev/null; then
        apt-get install -y -qq nginx > /dev/null 2>&1
    fi
    
    # 创建 Nginx 配置
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

    # 启用站点
    ln -sf /etc/nginx/sites-available/x-download /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    
    # 测试并重载 Nginx
    nginx -t > /dev/null 2>&1 && systemctl reload nginx
    echo -e "${GREEN}✓ Nginx 配置完成${NC}"
    echo -e "  访问地址: http://$(hostname -I | awk '{print \$1}')"
else
    echo -e "${GREEN}✓ 安装完成${NC}"
    echo -e "  访问地址: http://$(hostname -I | awk '{print \$1}'):$PORT"
fi

echo ""
echo "=============================="
echo -e "${GREEN}   安装完成！${NC}"
echo "=============================="
echo "服务管理命令:"
echo "  启动: systemctl start x-download"
echo "  停止: systemctl stop x-download"
echo "  重启: systemctl restart x-download"
echo "  状态: systemctl status x-download"
echo "  日志: journalctl -u x-download -f"
echo ""
echo "配置文件: $INSTALL_DIR/.env"
echo "下载目录: $INSTALL_DIR/downloads"
echo ""

# 更新 README.md
README_FILE="$(dirname "$SCRIPT_DIR")/README.md"
if [ -f "$README_FILE" ]; then
    sed -i.bak "/INSTALL_CONFIG_START/,/INSTALL_CONFIG_END/{
        s|安装端口: .*|安装端口: $PORT  |
        s|最大保留视频数: .*|最大保留视频数: $MAX_FILES  |
        s|安装目录: .*|安装目录: $INSTALL_DIR  |
        s|Nginx反向代理: .*|Nginx反向代理: $USE_NGINX  |
    }" "$README_FILE" 2>/dev/null || true
    rm -f "${README_FILE}.bak" 2>/dev/null || true
    echo -e "${GREEN}✓ README.md 已更新${NC}"
fi
