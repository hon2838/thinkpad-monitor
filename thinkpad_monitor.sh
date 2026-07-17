#!/bin/bash
# ThinkPad Hardware Monitor Launcher

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
SCRIPT_PATH="$SCRIPT_DIR/thinkpad_monitor.py"

# Execute the curses TUI script
python3 "$SCRIPT_PATH"
