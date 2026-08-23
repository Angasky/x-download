#!/usr/bin/env bash
# 可选：在 Linux 上把已能本地运行的 x-download 接到 nginx + systemd。
# 日常请先用 ./start.sh 完成依赖与 Cookie；本脚本不再克隆上游。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$REPO_DIR/.env"
NGINX_AVAILABLE="/etc/nginx/sites-available"
NGINX_ENABLED="/etc/nginx/sites-enabled"
BA_ROOT="/var/www/x-download"
PYTHON="$REPO_DIR/.venv/bin/python"

echo "=================================================="
echo "  x-download 生产部署（nginx + systemd）"
echo "=================================================="

if [[ ! -x "$PYTHON" ]]; then
  echo "未找到 $PYTHON"
  echo "请先执行: ./start.sh --no-start"
  exit 1
fi

read -rp "1) 站点域名（如 parse.example.com）: " DOMAIN
read -rp "2) 站点根目录 [默认 $BA_ROOT]: " INPUT_ROOT
BA_ROOT="${INPUT_ROOT:-$BA_ROOT}"
read -rp "3) 后端监听端口 [默认 18111]: " API_PORT
API_PORT="${API_PORT:-18111}"
read -rp "4) 运行用户 [默认 www-data]: " RUN_USER
RUN_USER="${RUN_USER:-www-data}"

cat > "$ENV_FILE" <<EOF
DOMAIN=$DOMAIN
SITE_ROOT=$BA_ROOT
API_PORT=$API_PORT
RUN_USER=$RUN_USER
EOF
echo "✔ 已写入 $ENV_FILE"

mkdir -p "$BA_ROOT"
cp "$REPO_DIR/web/index.html" "$BA_ROOT/index.html"
chown -R "$RUN_USER":"$RUN_USER" "$BA_ROOT" 2>/dev/null || true

VHOST="$NGINX_AVAILABLE/$DOMAIN.conf"
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

    ssl_certificate     /etc/nginx/ssl/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/$DOMAIN/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

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

    location ~ /\.well-known {
        allow all;
    }
}
EOF
ln -sf "$VHOST" "$NGINX_ENABLED/$DOMAIN.conf" 2>/dev/null || true

UNIT="/etc/systemd/system/x-download-api.service"
cat > "$UNIT" <<EOF
[Unit]
Description=x-download
After=network.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$REPO_DIR
Environment=PYTHONPATH=$REPO_DIR
Environment=XDOWNLOAD_HOST=127.0.0.1
Environment=XDOWNLOAD_PORT=$API_PORT
ExecStart=$PYTHON -m uvicorn backend.server:app --host 127.0.0.1 --port $API_PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

if command -v nginx >/dev/null 2>&1; then
  nginx -t && systemctl reload nginx || echo "⚠ nginx 未生效，请检查证书路径"
fi
if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  systemctl enable x-download-api.service
  systemctl restart x-download-api.service
fi

echo "完成。请补全 HTTPS 证书后访问 https://$DOMAIN"
