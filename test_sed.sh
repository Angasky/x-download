#!/bin/bash
README_FILE=/root/x-download/README.md
PORT=9090
MAX_FILES=99
INSTALL_DIR=/tmp/test
USE_NGINX=true

sed -i.bak "/INSTALL_CONFIG_START/,/INSTALL_CONFIG_END/{
    s|端口 / Port: .*|端口 / Port: ${PORT}  |
    s|最大保留文件數 / Max Files: .*|最大保留文件數 / Max Files: ${MAX_FILES}  |
    s|安裝目錄 / Install Dir: .*|安裝目錄 / Install Dir: ${INSTALL_DIR}  |
    s|Nginx 反向代理 / Nginx Reverse Proxy: .*|Nginx 反向代理 / Nginx Reverse Proxy: ${USE_NGINX}  |
}" "$README_FILE"

grep -A 5 INSTALL_CONFIG_START "$README_FILE"
rm -f "${README_FILE}.bak"
