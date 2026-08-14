#!/usr/bin/env bash
# ThinkPad & ThinkBook Hardware Monitor - Installer
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BIN_DIR="${HOME}/.local/bin"
SHARE_DIR="${HOME}/.local/share/thinkpad-monitor"
DESKTOP_DIR="${HOME}/.local/share/applications"

echo "=================================================="
echo "  ThinkPad & ThinkBook Hardware Monitor Installer"
echo "=================================================="

# 1. Ensure Python3 is available
if ! command -v python3 &>/dev/null; then
    echo "[-] Error: python3 is not installed."
    exit 1
fi

# 2. Check/Install Python psutil dependency
echo "[*] Checking Python dependencies..."
if ! python3 -c "import psutil" 2>/dev/null; then
    echo "[+] Installing psutil..."
    if command -v pip3 &>/dev/null; then
        pip3 install --user psutil || pip3 install psutil --break-system-packages 2>/dev/null || true
    elif command -v pip &>/dev/null; then
        pip install --user psutil || pip install psutil --break-system-packages 2>/dev/null || true
    else
        echo "[!] pip not found. Attempting to install via system package manager..."
        if command -v dnf &>/dev/null; then
            sudo dnf install -y python3-psutil
        elif command -v apt &>/dev/null; then
            sudo apt update && sudo apt install -y python3-psutil
        elif command -v pacman &>/dev/null; then
            sudo pacman -S --noconfirm python-psutil
        fi
    fi
fi

# 3. Install Package into ~/.local/share/thinkpad-monitor
echo "[*] Installing application files..."
mkdir -p "${SHARE_DIR}/src/thinkpad_monitor"
if [ -d "${ROOT_DIR}/src/thinkpad_monitor" ]; then
    cp -r "${ROOT_DIR}/src/thinkpad_monitor/"* "${SHARE_DIR}/src/thinkpad_monitor/"
elif [ -d "${SCRIPT_DIR}/src/thinkpad_monitor" ]; then
    cp -r "${SCRIPT_DIR}/src/thinkpad_monitor/"* "${SHARE_DIR}/src/thinkpad_monitor/"
else
    # Direct raw curl download fallback
    echo "[*] Fetching latest source files from GitHub..."
    curl -sSL -o "${SHARE_DIR}/src/thinkpad_monitor/__init__.py" https://raw.githubusercontent.com/hon2838/thinkpad-monitor/main/src/thinkpad_monitor/__init__.py
    curl -sSL -o "${SHARE_DIR}/src/thinkpad_monitor/__main__.py" https://raw.githubusercontent.com/hon2838/thinkpad-monitor/main/src/thinkpad_monitor/__main__.py
    curl -sSL -o "${SHARE_DIR}/src/thinkpad_monitor/monitor.py" https://raw.githubusercontent.com/hon2838/thinkpad-monitor/main/src/thinkpad_monitor/monitor.py
fi

# 4. Create executable launcher in ~/.local/bin
mkdir -p "${BIN_DIR}"
cat << 'EOF' > "${BIN_DIR}/thinkpad-monitor"
#!/usr/bin/env bash
SHARE_DIR="${HOME}/.local/share/thinkpad-monitor"
export PYTHONPATH="${SHARE_DIR}/src:${PYTHONPATH}"
exec python3 -m thinkpad_monitor "$@"
EOF
chmod +x "${BIN_DIR}/thinkpad-monitor"

# 5. Install Desktop Entry
mkdir -p "${DESKTOP_DIR}"
DESKTOP_FILE="${ROOT_DIR}/assets/thinkpad-monitor.desktop"
[ ! -f "${DESKTOP_FILE}" ] && DESKTOP_FILE="${SCRIPT_DIR}/assets/thinkpad-monitor.desktop"

if [ -f "${DESKTOP_FILE}" ]; then
    cp "${DESKTOP_FILE}" "${DESKTOP_DIR}/thinkpad-monitor.desktop"
else
    cat << EOF > "${DESKTOP_DIR}/thinkpad-monitor.desktop"
[Desktop Entry]
Name=ThinkPad Hardware Monitor
Comment=Terminal-based Hardware Telemetry & Monitor Dashboard
Exec=${BIN_DIR}/thinkpad-monitor
Icon=utilities-system-monitor
Terminal=true
Type=Application
Categories=System;Monitor;HardwareSettings;
Keywords=thinkpad;thinkbook;hardware;monitor;sensors;fan;battery;gpu;cpu;
EOF
fi

sed -i "s|Exec=thinkpad-monitor|Exec=${BIN_DIR}/thinkpad-monitor|g" "${DESKTOP_DIR}/thinkpad-monitor.desktop" 2>/dev/null || true
command -v update-desktop-database &>/dev/null && update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true

echo "[+] Installation successful!"
echo ""
echo "You can now run:"
echo "  thinkpad-monitor"
echo ""
if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
    echo "[!] Notice: ${BIN_DIR} is not in your current PATH."
    echo "    Add it to your shell configuration (e.g. ~/.bashrc):"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
