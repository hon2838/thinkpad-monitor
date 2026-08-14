# ThinkPad & ThinkBook Hardware Monitor (TUI)

A lightweight, terminal-based hardware monitoring dashboard written in Python and Curses, specifically tailored for **Lenovo ThinkPad & ThinkBook laptops** (as well as modern AMD Ryzen / Intel Linux systems). It provides a real-time, compact telemetry overview of CPU, GPU, memory, battery power, NVMe temperatures, and network activity.

---

## ✨ Features

- **System Load & Memory**: Real-time load averages (1/5/15m), CPU scaling driver, AMD P-State mode, live RAM usage bar with cache breakdown, and Swap utilization.
- **Storage & Dual NVMe SSD**: Root filesystem usage bar, dynamic I/O read/write throughput (MB/s), NVMe drive models, and controller vs. flash NAND temperatures with critical threshold warning limits.
- **Network Telemetry**: Active network interface auto-detection, IP address, real-time download/upload transfer rates (MB/s), Wi-Fi 6 SSID/signal/link rate, and total session data counters.
- **Battery & Power Delivery**: Charge status (Charging / Discharging / Full), capacity level, health percentage, cycle count, battery chemistry type, charging threshold limits, live voltage, and power draw in Watts (+charge / -draw).
- **APU & GPU Telemetry**: APU package power draw (W) vs PPT limit, GPU busy %, VRAM and GTT memory usage bars, GPU core clock (MHz), GPU core temperature, operating voltage (GFX/NB), and active DPM performance levels (GFX/MEM/FCLK).
- **CPU Core Telemetry**: Real-time independent per-core frequency (GHz/MHz) and load percentage bar graph for all cores/threads.
- **Thermals & Cooling**: CPU package temp with thermal junction headroom margin (+°C to TjMax), fan speed RPM (or EC Autonomous mode on ThinkBooks), fan PWM level, and auxiliary sensors (motherboard / Wi-Fi).
- **USB-C Power Delivery Ports**: Live USB-C PD contract negotiation status (Voltage, Current, live Wattage) across ports.
- **Warm Aesthetic Curses Theme**: Custom 256-color palette (warm khaki, peach, cyan, and emerald green) with responsive single/dual-column layout.

---

## 🚀 Quick Setup & Installation

### Option 1: One-Line Quick Install (Recommended)
Run this single command in your terminal to automatically configure dependencies, install the `thinkpad-monitor` command, and add a Desktop application menu shortcut:

```bash
curl -sSL https://raw.githubusercontent.com/hon2838/thinkpad-monitor/main/install.sh | bash
```

---

### Option 2: Via Pip / Pipx
```bash
pipx install git+https://github.com/hon2838/thinkpad-monitor.git
# Or standard pip:
pip install git+https://github.com/hon2838/thinkpad-monitor.git
```

---

### Option 3: Manual Clone
```bash
git clone https://github.com/hon2838/thinkpad-monitor.git
cd thinkpad-monitor
./install.sh
```

---

## 🖥️ Usage

Once installed, simply run from anywhere in your terminal:
```bash
thinkpad-monitor
```

*(You can also launch **ThinkPad Hardware Monitor** directly from your desktop applications / start menu).*

### Controls
* Press **`q`** at any time to exit the dashboard.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
