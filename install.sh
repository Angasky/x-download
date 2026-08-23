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
x-download Linux 一键安装器

用法：
  install.sh [--install-dir 路径] [--no-start] [--reconfigure]

选项：
  --install-dir PATH  指定安装目录，默认 ~/x-download
  --no-start          只安装，不立即启动服务
  --reconfigure       重新配置 Cookie
  -h, --help          显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir)
      [[ $# -ge 2 ]] || fail "--install-dir 缺少路径"
      INSTALL_DIR="$2"
      shift 2
      ;;
    --no-start|--reconfigure)
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

say "检查系统依赖"
if ! command_exists git; then
  install_package git
fi
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

say "准备依赖并启动 x-download"
cd "$INSTALL_DIR"
chmod +x start.sh install.sh
printf '安装目录：%s\n' "$INSTALL_DIR"
printf '访问地址：http://127.0.0.1:18111/\n'

if { exec 3</dev/tty; } 2>/dev/null; then
  exec "$python_cmd" scripts/bootstrap.py "${START_ARGS[@]}" <&3
fi
exec "$python_cmd" scripts/bootstrap.py "${START_ARGS[@]}"
