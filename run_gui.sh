#!/usr/bin/env bash
set -e
export WEBKIT_DISABLE_DMABUF_RENDERER=1
export WEBKIT_DISABLE_COMPOSITING_MODE=1
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# Run as root via pkexec if invoked as non-root
if [ "$(id -u)" -ne 0 ]; then
    command -v xhost >/dev/null 2>&1 && xhost +SI:localuser:root >/dev/null 2>&1
    if command -v pkexec >/dev/null 2>&1; then
        exec pkexec "$DIR/run_gui.sh" "$@"
    fi
fi

exec "$DIR/.venv/bin/python" -c "from ulum.gui.window import run_gui; run_gui()" "$@"
