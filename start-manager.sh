#!/usr/bin/env bash
# DCC MCP Manager — Unix one-click dev launcher.
#
# Sources Rust's cargo env (if needed) and runs `npm run tauri dev` from
# tauri-manager/. Ctrl+C to stop.
#
# macOS / Linux. Windows users: use start-manager.bat.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/tauri-manager"

# Source cargo env if cargo isn't already on PATH.
if ! command -v cargo > /dev/null 2>&1; then
    if [ -f "$HOME/.cargo/env" ]; then
        # shellcheck disable=SC1091
        . "$HOME/.cargo/env"
    else
        echo "[start-manager] cargo not found. Install Rust via:"
        echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
        exit 1
    fi
fi

exec npm run tauri dev
