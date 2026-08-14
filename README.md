# ThinkPad Hardware Monitor (TUI)

A terminal-based hardware monitoring dashboard written in Python and Curses, specifically tailored for **Lenovo ThinkPad (e.g., L15 Gen 1)** running Linux. It visualizes CPU, GPU, memory, battery status, NVMe temperature, active network speeds, and charger statistics in real-time.

![Preview](preview.png) *(Placeholder or screenshot can be placed here)*

## Features

- **System Load & Memory**: Live load averages, CPU scaling driver + AMD pstate mode, RAM usage bar, Swap usage bar.
- **Storage & NVMe SSD**: Disk utilization, dynamic read/write I/O speeds, and NVMe controller temperature with sysfs-derived critical threshold margin.
- **Network Stats**: Active interface detection, live download/upload speeds (MB/s), and total traffic counters.
- **Battery & Power Delivery**: Battery status (charging, discharging, full) with capacity level, current capacity bar, health percentage, cycle count, active charge type, start/stop charging thresholds, and live power draw in Watts.
- **APU Power & GPU**: Package power draw, GPU utilization, VRAM/GTT usage, DPM clock levels (GFX/MEM/FCLK), GPU performance level, and GPU temperature/voltage telemetry.
- **CPU Core Telemetry**: Independent frequency (GHz) and load (%) display for all 12 threads.
- **Thermals & Cooling**: Real-time CPU core temp, fan speed (RPM), fan PWM level (auto/manual), and auxiliary sensors (ThinkPad board / Wi-Fi).
- **USB-C Telemetry**: Charger power contract details (Voltage, Current, live Wattage) on both USB-C ports.

## Prerequisites

- **OS**: Linux
- **Python**: 3.x
- **Dependencies**: `psutil` (read below for system file access requirements)

### Hardware-specific Paths
This script reads from standard Linux `sysfs` and `/proc` systems. Some paths may need adjustment depending on your exact ThinkPad model or kernel configuration (e.g., hwmon index numbers for CPU/GPU/fan).

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/hon2838/thinkpad-monitor.git
   cd thinkpad-monitor
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Make the launcher script executable:
   ```bash
   chmod +x thinkpad_monitor.sh
   ```

## Usage

Run the launcher script:
```bash
./thinkpad_monitor.sh
```

Or run the python script directly:
```bash
python3 thinkpad_monitor.py
```

Press `q` at any time to exit the dashboard.
