#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY_URL="https://github.com/Angasky/x-download.git"
USER_HOME="${HOME:-}"
if [[ -z "$USER_HOME" ]] && command -v getent >/dev/null 2>&1; then
  USER_HOME="$(getent passwd "$(id -u)" 2>/dev/null | cut -d: -f6 || true)"
fi
if [[ -z "$USER_HOME" && -r /etc/passwd ]]; then
  USER_HOME="$(awk -F: -v uid="$(id -u)" '$3 == uid {print $6; exit}' /etc/passwd)"
fi
if [[ -z "$USER_HOME" && "${EUID}" -eq 0 ]]; then
  USER_HOME="/root"
fi
if [[ -z "$USER_HOME" ]]; then
  printf '[error] 无法确定当前用户主目录，请先设置 HOME 环境变量。\n' >&2
  exit 1
fi
DEFAULT_INSTALL_DIR="${USER_HOME}/x-download"
INSTALL_DIR="${XDOWNLOAD_INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
START_ARGS=("--no-browser" "--update-vendor")
ACCESS_MODE=""
NO_START=0

say() {
  printf '\n\033[1;36m[x-download]\033[0m %s\n' "$*"
}

warn() {
  printf '\033[1;33m[warning]\033[0m %s\n' "$*" >&2
}

fail() {
  printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

run_as_root() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  elif command_exists sudo; then
    sudo "$@"
  else
    fail "安装系统依赖需要 root 权限，请安装 sudo 或使用 root 用户运行。"
  fi
}

install_package() {
  local package="$1"
  if command_exists apt-get; then
    run_as_root apt-get update
    run_as_root apt-get install -y "$package"
  elif command_exists dnf; then
    run_as_root dnf install -y "$package"
  elif command_exists yum; then
    run_as_root yum install -y "$package"
  elif command_exists pacman; then
    run_as_root pacman -Sy --noconfirm "$package"
  elif command_exists apk; then
    run_as_root apk add --no-cache "$package"
  elif command_exists zypper; then
    run_as_root zypper --non-interactive install "$package"
  else
    fail "无法识别系统包管理器，请先手动安装 $package。"
  fi
}

python_is_compatible() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1
}

find_python() {
  local candidate
  for candidate in \
    "$INSTALL_DIR/.venv/bin/python" \
    python3.13 \
    python3.12 \
    python3 \
    python; do
    if [[ "$candidate" == */* ]]; then
      [[ -x "$candidate" ]] || continue
    elif ! command_exists "$candidate"; then
      continue
    fi
    if python_is_compatible "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

install_python() {
  command_exists curl || install_package curl
  local uv_bin="${USER_HOME}/.local/bin/uv"
  if ! command_exists uv && [[ ! -x "$uv_bin" ]]; then
    say "未检测到 Python 3.12+，正在安装独立 Python 运行环境" >&2
    local installer_dir
    installer_dir="$(mktemp -d)"
    curl -LsSf https://astral.sh/uv/install.sh -o "$installer_dir/uv-install.sh"
    env UV_NO_MODIFY_PATH=1 sh "$installer_dir/uv-install.sh" >&2
    rm -rf -- "$installer_dir"
  fi
  if command_exists uv; then
    uv_bin="$(command -v uv)"
  fi
  [[ -x "$uv_bin" ]] || fail "uv 安装失败，无法自动准备 Python 3.12。"
  "$uv_bin" python install 3.12 >&2
  "$uv_bin" python find 3.12
}

usage() {
  cat <<'EOF'
x-download Linux 管理器

用法：
  xd
  install.sh
  install.sh [--install-dir 路径] [--public|--local] [--no-start] [--reconfigure]

选项：
  --menu              打开交互管理菜单
  --install-dir PATH  指定安装目录，默认 ~/x-download
  --public            开启公网监听并安装 systemd 常驻服务
  --local             仅监听本机（默认非交互模式）
  --no-start          只安装，不立即启动服务
  --reconfigure       重新配置 Cookie
  -h, --help          显示帮助
EOF
}

ACTION="menu"
if [[ $# -gt 0 ]]; then
  ACTION="install"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --menu)
      ACTION="menu"
      shift
      ;;
    --install-dir)
      [[ $# -ge 2 ]] || fail "--install-dir 缺少路径"
      INSTALL_DIR="$2"
      shift 2
      ;;
    --public)
      ACCESS_MODE="public"
      shift
      ;;
    --local)
      ACCESS_MODE="local"
      shift
      ;;
    --no-start)
      NO_START=1
      START_ARGS+=("$1")
      shift
      ;;
    --reconfigure)
      START_ARGS+=("$1")
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "未知参数：$1"
      ;;
  esac
done

[[ "$(uname -s)" == "Linux" ]] || fail "此安装器仅用于 Linux。macOS 请克隆仓库后运行 ./start.sh。"
[[ -n "$INSTALL_DIR" && "$INSTALL_DIR" != "/" && "$INSTALL_DIR" != "$USER_HOME" ]] \
  || fail "安装目录不安全：$INSTALL_DIR"

HAS_TTY=0
if [[ -t 1 ]] && { exec 3</dev/tty; } 2>/dev/null; then
  HAS_TTY=1
fi

read_tty() {
  local variable_name="$1"
  local prompt="$2"
  local value=""
  [[ "$HAS_TTY" -eq 1 ]] || return 1
  printf '%s' "$prompt"
  IFS= read -r -u 3 value || value=""
  printf -v "$variable_name" '%s' "$value"
}

pause_menu() {
  local ignored=""
  read_tty ignored $'\n按 Enter 返回菜单...' || true
}

require_installation() {
  [[ -d "$INSTALL_DIR/.git" && -x "$INSTALL_DIR/.venv/bin/python" ]] \
    || fail "尚未安装 x-download，请先在菜单中选择 1。"
}

prepare_project() {
  say "检查系统依赖"
  command_exists git || install_package git
  if ! command_exists ffmpeg; then
    warn "未检测到 ffmpeg，正在尝试安装（用于合并音视频）"
    install_package ffmpeg || warn "ffmpeg 自动安装失败，可稍后手动安装。"
  fi

  say "安装或更新项目：$INSTALL_DIR"
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    git -C "$INSTALL_DIR" pull --ff-only
  elif [[ -e "$INSTALL_DIR" ]] && [[ -n "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    fail "安装目录已存在且不是 x-download Git 仓库：$INSTALL_DIR"
  else
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --depth 1 "$REPOSITORY_URL" "$INSTALL_DIR"
  fi

  python_cmd="$(find_python || true)"
  if [[ -z "$python_cmd" ]]; then
    python_cmd="$(install_python)"
  fi
  python_is_compatible "$python_cmd" || fail "未找到可用的 Python 3.12+。"
  cd "$INSTALL_DIR"
  chmod +x start.sh install.sh
}

run_bootstrap() {
  if [[ "$HAS_TTY" -eq 1 ]]; then
    "$python_cmd" scripts/bootstrap.py "$@" <&3
  else
    "$python_cmd" scripts/bootstrap.py "$@" </dev/null
  fi
}

config_value() {
  local key="$1"
  local fallback="$2"
  local value=""
  if [[ -r "$INSTALL_DIR/config/app.yaml" ]]; then
    value="$(awk -F: -v key="$key" '$1 == key {sub(/^[[:space:]]+/, "", $2); print $2; exit}' "$INSTALL_DIR/config/app.yaml")"
  fi
  printf '%s\n' "${value:-$fallback}"
}

install_xd_command() {
  local shortcut="/usr/local/bin/xd"
  local target="$INSTALL_DIR/install.sh"
  if [[ -e "$shortcut" && ! -L "$shortcut" ]]; then
    warn "$shortcut 已存在且不是符号链接，未覆盖；可继续使用 $target 打开菜单。"
    return
  fi
  run_as_root ln -sfn "$target" "$shortcut"
}

allow_firewall_port() {
  local port="$1"
  if command_exists ufw && run_as_root ufw status 2>/dev/null | grep -q '^Status: active'; then
    run_as_root ufw allow "$port/tcp"
  fi
}

install_managed_service() {
  command_exists systemctl || fail "当前系统不支持 systemd，无法安装后台常驻服务。"
  [[ "$INSTALL_DIR" != *[[:space:]]* && "$INSTALL_DIR" != *'"'* ]] \
    || fail "公网服务安装目录不能包含空白字符或双引号。"

  local service_file
  service_file="$(mktemp)"
  printf '%s\n' \
    '[Unit]' \
    'Description=x-download web service' \
    'After=network-online.target' \
    'Wants=network-online.target' \
    '' \
    '[Service]' \
    'Type=simple' \
    "User=$(id -un)" \
    "WorkingDirectory=$INSTALL_DIR" \
    "Environment=\"PYTHONPATH=$INSTALL_DIR\"" \
    "ExecStart=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/scripts/bootstrap.py --skip-install --no-browser --skip-cookie-prompt" \
    'Restart=on-failure' \
    'RestartSec=3' \
    '' \
    '[Install]' \
    'WantedBy=multi-user.target' > "$service_file"
  run_as_root install -o root -g root -m 0644 "$service_file" /etc/systemd/system/x-download.service
  rm -f -- "$service_file"

  allow_firewall_port "$(config_value port 18111)"
  run_as_root systemctl daemon-reload
  run_as_root systemctl enable x-download.service
  run_as_root systemctl restart x-download.service
}

choose_access_mode() {
  local choice=""
  if [[ -n "$ACCESS_MODE" ]]; then
    return
  fi
  if [[ "$HAS_TTY" -eq 1 ]]; then
    printf '\n  1) 公网访问（0.0.0.0，systemd 常驻）\n'
    printf '  2) 仅本机访问（127.0.0.1）\n'
    read_tty choice '请选择访问模式 [1/2，默认 2]: ' || true
  fi
  [[ "$choice" == "1" ]] && ACCESS_MODE="public" || ACCESS_MODE="local"
}

install_project() {
  prepare_project
  install_xd_command
  say "准备依赖与服务"
  printf '安装目录：%s\n' "$INSTALL_DIR"
  choose_access_mode

  if [[ "$ACCESS_MODE" == "public" ]]; then
    printf '访问模式：公网（0.0.0.0:18111）\n'
    local public_args=("${START_ARGS[@]}" "--host" "0.0.0.0" "--port" "18111")
    if [[ "$NO_START" -eq 0 ]]; then
      public_args+=("--no-start")
    fi
    run_bootstrap "${public_args[@]}"
    if [[ "$NO_START" -eq 0 ]]; then
      install_managed_service
      printf '\n\033[1;32m[完成]\033[0m 公网服务已启动并设置为开机自启。\n'
      printf '访问地址：http://<服务器公网IP>:18111/\n'
      printf '云服务器安全组需放行 TCP 18111；允许所有来源时设为 0.0.0.0/0。\n'
    else
      printf '已保存公网配置；根据 --no-start 要求未启动服务。\n'
    fi
  else
    printf '访问模式：仅本机（127.0.0.1:18111）\n'
    local local_args=("${START_ARGS[@]}" "--host" "127.0.0.1")
    run_bootstrap "${local_args[@]}"
  fi

  printf '\n\033[1;33m以后只需输入 xd，即可再次打开 Mxioc 管理菜单。\033[0m\n'
}

change_port() {
  require_installation
  python_cmd="$INSTALL_DIR/.venv/bin/python"
  local old_port new_port
  old_port="$(config_value port 18111)"
  read_tty new_port "请输入新端口 [当前 $old_port]: " || fail "修改端口需要交互终端。"
  [[ "$new_port" =~ ^[0-9]+$ && "$new_port" -ge 1 && "$new_port" -le 65535 ]] \
    || fail "端口必须是 1 到 65535 的整数。"
  cd "$INSTALL_DIR"
  run_bootstrap --skip-install --no-start --skip-cookie-prompt --port "$new_port"
  allow_firewall_port "$new_port"
  if command_exists systemctl && systemctl cat x-download.service >/dev/null 2>&1; then
    run_as_root systemctl restart x-download.service
  fi
  printf '\n[完成] 端口已修改为 %s。\n' "$new_port"
  printf '公网访问：http://<服务器公网IP>:%s/\n' "$new_port"
  printf '云服务器安全组也需要放行新的 TCP 端口。\n'
}

restart_service() {
  require_installation
  command_exists systemctl || fail "当前系统不支持 systemd。"
  systemctl cat x-download.service >/dev/null 2>&1 || fail "尚未安装后台服务，请先选择安装或修改访问模式。"
  run_as_root systemctl restart x-download.service
  run_as_root systemctl --no-pager --full status x-download.service
}

configure_cookies() {
  require_installation
  python_cmd="$INSTALL_DIR/.venv/bin/python"
  cd "$INSTALL_DIR"
  run_bootstrap --skip-install --no-start --reconfigure
  if command_exists systemctl && systemctl is-active --quiet x-download.service; then
    run_as_root systemctl restart x-download.service
  fi
  printf '\n[完成] Cookie 已保存，服务已重新加载。\n'
}

change_access_mode() {
  require_installation
  python_cmd="$INSTALL_DIR/.venv/bin/python"
  local choice host label
  printf '\n  1) 公网访问（0.0.0.0）\n  2) 仅本机访问（127.0.0.1）\n'
  read_tty choice '请选择 [1/2]: ' || fail "修改访问模式需要交互终端。"
  case "$choice" in
    1) host="0.0.0.0"; label="公网" ;;
    2) host="127.0.0.1"; label="仅本机" ;;
    *) fail "无效选择。" ;;
  esac
  cd "$INSTALL_DIR"
  run_bootstrap --skip-install --no-start --skip-cookie-prompt --host "$host"
  install_managed_service
  printf '\n[完成] 已切换为%s访问，服务已重启。\n' "$label"
}

show_status() {
  require_installation
  printf '\n安装目录：%s\n' "$INSTALL_DIR"
  printf '监听配置：%s:%s\n' "$(config_value host 127.0.0.1)" "$(config_value port 18111)"
  if command_exists systemctl && systemctl cat x-download.service >/dev/null 2>&1; then
    systemctl --no-pager --full status x-download.service || true
  else
    printf '后台服务：未安装\n'
  fi
}

show_logs() {
  require_installation
  command_exists journalctl || fail "当前系统没有 journalctl。"
  journalctl -u x-download.service -n 80 --no-pager || true
}

uninstall_project() {
  [[ -d "$INSTALL_DIR/.git" ]] || fail "未找到安装目录：$INSTALL_DIR"
  local confirmation="" resolved_install resolved_home remote_url shortcut_target=""
  printf '\n\033[1;31m此操作会停止服务并删除整个目录：%s\033[0m\n' "$INSTALL_DIR"
  read_tty confirmation '请输入 UNINSTALL 确认卸载: ' || fail "卸载需要交互终端。"
  [[ "$confirmation" == "UNINSTALL" ]] || { printf '已取消卸载。\n'; return; }

  resolved_install="$(readlink -f -- "$INSTALL_DIR")"
  resolved_home="$(readlink -f -- "$USER_HOME")"
  [[ -n "$resolved_install" && "$resolved_install" != "/" && "$resolved_install" != "$resolved_home" ]] \
    || fail "拒绝删除不安全路径：$resolved_install"
  remote_url="$(git -C "$resolved_install" remote get-url origin 2>/dev/null || true)"
  [[ "$remote_url" == "$REPOSITORY_URL" ]] || fail "安装目录的 Git 来源不匹配，拒绝自动删除。"

  if command_exists systemctl && systemctl cat x-download.service >/dev/null 2>&1; then
    run_as_root systemctl disable --now x-download.service || true
    run_as_root rm -f -- /etc/systemd/system/x-download.service
    run_as_root systemctl daemon-reload
  fi
  if [[ -L /usr/local/bin/xd ]]; then
    shortcut_target="$(readlink -f /usr/local/bin/xd 2>/dev/null || true)"
    if [[ "$shortcut_target" == "$resolved_install/install.sh" ]]; then
      run_as_root rm -f -- /usr/local/bin/xd
    fi
  fi
  cd "$resolved_home"
  rm -rf -- "$resolved_install"
  printf '\n[完成] x-download 已卸载，配置和虚拟环境已一并删除。\n'
  exit 0
}

show_menu() {
  command_exists clear && clear || true
  printf '\033[1;36m'
  cat <<'EOF'
███╗   ███╗██╗  ██╗██╗ ██████╗  ██████╗
████╗ ████║╚██╗██╔╝██║██╔═══██╗██╔════╝
██╔████╔██║ ╚███╔╝ ██║██║   ██║██║
██║╚██╔╝██║ ██╔██╗ ██║██║   ██║██║
██║ ╚═╝ ██║██╔╝ ██╗██║╚██████╔╝╚██████╗
╚═╝     ╚═╝╚═╝  ╚═╝╚═╝ ╚═════╝  ╚═════╝
EOF
  printf '\033[0m'
  printf '        x-download · Mxioc 管理控制台\n'
  printf '  ─────────────────────────────────────\n'
  printf '   1.  安装 / 更新       2.  卸载\n'
  printf '   3.  修改访问端口      4.  重启服务\n'
  printf '   5.  修改 Cookie       6.  修改访问模式\n'
  printf '   7.  查看服务状态      8.  查看最近日志\n'
  printf '   0.  退出\n'
  printf '  ─────────────────────────────────────\n'
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    printf '  状态：\033[1;32m已安装\033[0m  目录：%s\n' "$INSTALL_DIR"
  else
    printf '  状态：\033[1;33m未安装\033[0m\n'
  fi
  printf '  提示：安装后随时输入 \033[1;33mxd\033[0m 返回此菜单。\n\n'
}

menu_loop() {
  [[ "$HAS_TTY" -eq 1 ]] || fail "菜单需要交互终端。无人值守安装请使用 --public 或 --local。"
  local choice=""
  while true; do
    show_menu
    read_tty choice '请选择操作 [0-8]: ' || exit 0
    case "$choice" in
      1)
        ACCESS_MODE=""
        NO_START=0
        START_ARGS=("--no-browser" "--update-vendor")
        install_project
        pause_menu
        ;;
      2) uninstall_project; pause_menu ;;
      3) change_port; pause_menu ;;
      4) restart_service; pause_menu ;;
      5) configure_cookies; pause_menu ;;
      6) change_access_mode; pause_menu ;;
      7) show_status; pause_menu ;;
      8) show_logs; pause_menu ;;
      0) printf '再见。\n'; exit 0 ;;
      *) printf '\n无效选项，请输入 0 到 8。\n'; pause_menu ;;
    esac
  done
}

if [[ "$ACTION" == "menu" ]]; then
  menu_loop
else
  install_project
fi
