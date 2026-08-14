#!/usr/bin/env bash
# ThinkPad Hardware Monitor - Quick Installer
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
DESKTOP_DIR="${HOME}/.local/share/applications"

echo "=================================================="
echo "  ThinkPad Hardware Monitor (TUI) Installer"
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

# 3. Install executable script to ~/.local/bin
mkdir -p "${BIN_DIR}"
cat << 'EOF' > "${BIN_DIR}/thinkpad-monitor"
#!/usr/bin/env bash
python3 -c "import sys; sys.path.insert(0, '$(dirname "$(readlink -f "$0")")/../share/thinkpad-monitor'); import thinkpad_monitor; thinkpad_monitor.main()" "$@" 2>/dev/null || python3 -m thinkpad_monitor "$@" 2>/dev/null || python3 "$(dirname "$(readlink -f "$0")")/thinkpad_monitor.py" "$@"
EOF

# Install the actual python script alongside
SHARE_DIR="${HOME}/.local/share/thinkpad-monitor"
mkdir -p "${SHARE_DIR}"
cp "${SCRIPT_DIR}/thinkpad_monitor.py" "${SHARE_DIR}/thinkpad_monitor.py"

cat << EOF > "${BIN_DIR}/thinkpad-monitor"
#!/usr/bin/env bash
python3 "${SHARE_DIR}/thinkpad_monitor.py" "\$@"
EOF
chmod +x "${BIN_DIR}/thinkpad-monitor"

# 4. Install Desktop Entry
mkdir -p "${DESKTOP_DIR}"
if [ -f "${SCRIPT_DIR}/thinkpad-monitor.desktop" ]; then
    cp "${SCRIPT_DIR}/thinkpad-monitor.desktop" "${DESKTOP_DIR}/thinkpad-monitor.desktop"
    sed -i "s|Exec=thinkpad-monitor|Exec=${BIN_DIR}/thinkpad-monitor|g" "${DESKTOP_DIR}/thinkpad-monitor.desktop"
    command -v update-desktop-database &>/dev/null && update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true
fi

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
