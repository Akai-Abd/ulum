#!/usr/bin/env bash
set -e
export WEBKIT_DISABLE_DMABUF_RENDERER=1
export WEBKIT_DISABLE_COMPOSITING_MODE=1
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
exec "$DIR/.venv/bin/python" -c "from ulum.gui.window import run_gui; run_gui()"
