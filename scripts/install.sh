#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${XDG_DATA_HOME:-${HOME}/.local/share}"
APP_DIR="${DATA_DIR}/thinkpad-monitor"
BIN_DIR="${HOME}/.local/bin"
MODE=desktop
SYSTEM_SITE=false
for arg in "$@"; do
    case "$arg" in
        --tui) MODE=tui ;;
        --system-site-packages) SYSTEM_SITE=true ;;
        --help) echo 'Usage: ./install.sh [--tui] [--system-site-packages]'; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done
command -v python3 >/dev/null || { echo 'Python 3 is required.' >&2; exit 1; }
python3 - "$MODE" <<'PY'
import sys
minimum = (3, 10) if sys.argv[1] == 'desktop' else (3, 9)
if sys.version_info < minimum:
    raise SystemExit('Python %s.%s or newer is required.' % minimum)
PY
mkdir -p "$APP_DIR" "$BIN_DIR"
if "$SYSTEM_SITE"; then
    python3 -m venv --system-site-packages "${APP_DIR}/venv"
else
    python3 -m venv "${APP_DIR}/venv"
fi
TARGET="$ROOT_DIR"
if [[ "$MODE" == desktop ]]; then TARGET="${ROOT_DIR}[desktop]"; fi
"${APP_DIR}/venv/bin/python" -m pip install "$TARGET"
"${APP_DIR}/venv/bin/thinkpad-monitor" --version
if [[ "$MODE" == desktop ]]; then
    "${APP_DIR}/venv/bin/python" -c 'from PySide6.QtWidgets import QApplication'
fi
# Install durable launchers and freedesktop menu entry with correctly quoted paths.
"${APP_DIR}/venv/bin/python" - "$ROOT_DIR" "$APP_DIR" "$BIN_DIR" "$DATA_DIR" "$MODE" <<'PY'
from pathlib import Path
import shlex
import shutil
import sys
root, app, bin_dir, data = map(Path, sys.argv[1:5])
mode = sys.argv[5]
exe = app / 'venv/bin/thinkpad-monitor'
launcher = bin_dir / 'thinkpad-monitor'
launcher.write_text('#!/bin/sh\nexec ' + shlex.quote(str(exe)) + ' "$@"\n')
launcher.chmod(0o755)
applications = data / 'applications'
applications.mkdir(parents=True, exist_ok=True)
entry = applications / 'thinkpad-monitor.desktop'
if mode == 'desktop':
    # Desktop Exec escaping involves command quoting AND string-value escaping.
    command = str(exe).replace('%', '%%')
    command = ''.join(('\\' + c) if c in '\\"`$' else c for c in command)
    command = command.replace('\\', '\\\\')
    content = (root / 'assets/thinkpad-monitor.desktop').read_text()
    content = content.replace('Exec=thinkpad-monitor --desktop', 'Exec="' + command + '" --desktop')
    content = content.replace('TryExec=thinkpad-monitor\n', '')
    entry.write_text(content)
    icon_dir = data / 'icons/hicolor/scalable/apps'
    icon_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / 'assets/thinkpad-monitor.svg', icon_dir)
else:
    entry.unlink(missing_ok=True)
print('Installed: ' + str(launcher))
PY
if command -v update-desktop-database >/dev/null; then
    update-desktop-database "${DATA_DIR}/applications" || true
fi
echo 'Installation complete. Open Laptop Monitor from your applications menu.'
echo "Command: ${BIN_DIR}/thinkpad-monitor (use --tui for terminal mode)"
