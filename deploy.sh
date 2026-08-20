#!/usr/bin/env bash
# x-download 一键部署脚本（视频解析服务）
# 用法：
#   chmod +x deploy.sh && sudo ./deploy.sh
# 脚本会交互式询问少量配置，随后生成 .env、nginx vhost、systemd 服务并替换前端里的硬编码域名。
# 适用于 Ubuntu/Debian + Nginx + 宝塔面板（也兼容任意标准 Nginx）。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$REPO_DIR/.env"
NGINX_AVAILABLE="/etc/nginx/sites-available"
NGINX_ENABLED="/etc/nginx/sites-enabled"
# 宝塔用户把下面两行改成：
# NGINX_AVAILABLE="/www/server/panel/vhost/nginx"
# NGINX_ENABLED="/www/server/panel/vhost/nginx"
BA_ROOT="/www/wwwroot/x-download"           # 站点根目录（可改）

echo "=================================================="
echo "  x-download 一键部署（视频解析）"
echo "=================================================="

read -rp "1) 站点域名（如 parse.example.com）: " DOMAIN
read -rp "2) 站点根目录 [默认 $BA_ROOT]: " INPUT_ROOT
BA_ROOT="${INPUT_ROOT:-$BA_ROOT}"
read -rp "3) 后端监听端口 [默认 18111]: " API_PORT
API_PORT="${API_PORT:-18111}"
read -rp "4) 抖音解析上游 /douyin/share + /douyin/detail 地址（KR_API_BASE，留空则解析抖音会报错）: " KR_API_BASE
read -rp "5) 运行用户 [默认 www-data]: " RUN_USER
RUN_USER="${RUN_USER:-www-data}"

# 写入 .env（不入库，已在 .gitignore）
cat > "$ENV_FILE" <<EOF
# 本文件由 deploy.sh 生成，含私密部署配置，请勿提交到仓库
DOMAIN=$DOMAIN
SITE_ROOT=$BA_ROOT
API_PORT=$API_PORT
KR_API_BASE=$KR_API_BASE
RUN_USER=$RUN_USER
EOF
echo "✔ 已写入 $ENV_FILE"

# 1) 复制前端到站点根目录
echo "→ 部署前端到 $BA_ROOT"
mkdir -p "$BA_ROOT"
cp "$REPO_DIR/www/index.html" "$BA_ROOT/index.html"
# 前端 index.html 通过相对/路径调用 /api/*，无需硬编码域名；这里以防万一做一次兜底替换
if grep -q "sg.mxvv.cn" "$BA_ROOT/index.html"; then
  sed -i "s#sg.mxvv.cn#$DOMAIN#g" "$BA_ROOT/index.html"
fi
chown -R "$RUN_USER":"$RUN_USER" "$BA_ROOT" 2>/dev/null || true

# 2) 生成 nginx vhost
VHOST="$NGINX_AVAILABLE/$DOMAIN.conf"
echo "→ 生成 nginx vhost: $VHOST"
cat > "$VHOST" <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name $DOMAIN;
    root $BA_ROOT;
    index index.html;

    # 把你的证书路径填到这里（可用 certbot 自动申请）
    ssl_certificate     /etc/nginx/ssl/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/$DOMAIN/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    # 视频解析 API：反代到后端（compat_sg 提供的 /api/info /api/tkinfo /api/ytdlp /api/stream）
    location /api/ {
        proxy_pass http://127.0.0.1:$API_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_max_temp_file_size 0;
        proxy_read_timeout 300s;
        proxy_connect_timeout 10s;
        proxy_send_timeout 30s;
    }

    # 证书校验目录
    location ~ /\.well-known {
        allow all;
    }
}
EOF
ln -sf "$VHOST" "$NGINX_ENABLED/$DOMAIN.conf" 2>/dev/null || true
echo "✔ nginx vhost 已生成（启用需 reload nginx）"

# 3) 生成 systemd 服务
UNIT="/etc/systemd/system/x-download-api.service"
echo "→ 生成 systemd 服务: $UNIT"
cat > "$UNIT" <<EOF
[Unit]
Description=x-download 视频解析后端 (compat_sg)
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$BA_ROOT
# 说明：compat_sg 需挂载进 Evil0ctal/Douyin_TikTok_Download_API 运行。
# 下面 Environment 注入私密配置（KR_API_BASE 来自 .env）。
Environment=KR_API_BASE=$KR_API_BASE
# 真正启动命令（请按你的 douyin-api 部署方式调整 ExecStart）：
ExecStart=/bin/bash -c 'cd /opt/douyin-api && KR_API_BASE=$KR_API_BASE venv/bin/python3 start.py'
Restart=always
RestartSec=3
TimeoutStartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
echo "✔ systemd 服务已生成"

# 4) 重载 nginx + 启用服务
if command -v nginx >/dev/null 2>&1; then
  nginx -t && systemctl reload nginx || echo "⚠ nginx 配置未生效，请手动检查证书路径后 reload"
fi
if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  systemctl enable x-download-api.service
  systemctl restart x-download-api.service || echo "⚠ 服务启动失败，请确认 /opt/douyin-api 已部署且 venv 存在"
fi

echo "=================================================="
echo "  部署脚本完成"
echo "  - 前端:  $BA_ROOT/index.html"
echo "  - 后端:  :$API_PORT (compat_sg, 需配合 douyin-api 主程序)"
echo "  - 上游:  KR_API_BASE=$KR_API_BASE"
echo "  - nginx: $VHOST  （请补全 ssl_certificate 路径）"
echo "  下一步：配置 HTTPS 证书后访问 https://$DOMAIN"
echo "=================================================="
