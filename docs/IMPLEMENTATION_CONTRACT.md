# Linux Laptop Monitor implementation contract

Keep the distribution/import/command name `thinkpad-monitor` for compatibility;
use **Laptop Monitor** as the desktop display name. All telemetry is read-only.

## Collector

`thinkpad_monitor.telemetry.Collector(sys_root='/sys', proc_root='/proc', psutil_module=None, clock=None)` exposes `sample() -> dict` (JSON serializable), with null for missing numeric metrics, never fabricated zeroes. Public schema:

- `system`: hostname, model, architecture, kernel, uptime_seconds, platform_profile
- `cpu`: percent, per_core_percent (list), frequencies_mhz (list), load_average (list), governor, driver
- `memory`: total_bytes, used_bytes, available_bytes, percent, swap_total_bytes, swap_used_bytes, swap_percent
- `storage`: total_bytes, used_bytes, percent, read_bytes_per_second, write_bytes_per_second
- `networks`: list of name, addresses (list), is_up, rx_bytes_per_second, tx_bytes_per_second, received_bytes, sent_bytes
- `batteries`: list of name, status, percent, health_percent, cycles, voltage_volts, power_watts, energy_wh, full_energy_wh, time_remaining_seconds
- `temperatures`: list of name, label, celsius, critical_celsius (all discovered hwmon/thermal temperatures; deduplicate if useful)
- `fans`: list of name, label, rpm
- `gpus`: list of name, vendor, driver, busy_percent, temperature_celsius, memory_used_bytes, memory_total_bytes (discover DRM card[0-9]+, including Intel/AMD/NVIDIA/other; missing readings null)
- `power`: list of name, watts (measured hwmon or RAPL delta only; never constraint limits)
- `warnings`: list of human readable messages if collection partial/fails

Discover all batteries by `type=Battery` and present, including arbitrary names and multiple packs. Micro units have fixed conversion factors. Frequency/core count dynamic. Each section tolerant of missing sysfs, permission failure, bad/disappearing files. Counter rates monotonic, baseline first sample and new interfaces, clamp resets to zero. RAPL needs wraparound using max_energy_range_uj. No privileged writes, shell programs, or slow polling on GUI thread.

## Desktop

`thinkpad_monitor.desktop.main(argv=None)` and `MonitorWindow(collector=None, interval=2.0)` for PySide6 Qt Widgets; lazy import from CLI. Qt chooses native Wayland/X11 backend; no KDE/GNOME-specific APIs. Resizable scrollable dashboard showing summary, CPU, memory, disks, all batteries, networks, thermal/fan sensors, GPUs and power. Background collection with non-overlapping worker and clean shutdown. Native palette, accessible text/labels, refresh interval, pause/resume, bounded CPU history graph, missing values displayed 'Unavailable'. Headless `--smoke-test` runs offscreen, samples and exits nonzero on failure. Capture preview via `--screenshot PATH` if feasible. No dependency on tray icons.

## Entry points (integrator owns)

CLI `thinkpad-monitor` defaults desktop when a display is available, terminal otherwise; `--desktop`, `--tui`, `--json`, `--interval`, `--version`. Desktop dependencies optional extra `desktop` with PySide6; diagnostic on absent dependencies. Generic terminal consumes Collector, retain original terminal behind `--legacy-tui` for detailed ThinkPad/AMD metrics. `python -m` and console scripts same dispatcher.

## Ownership

Collector agent: only telemetry.py and tests/test_telemetry.py.
Desktop agent: only desktop.py and tests/test_desktop.py.
Integrator: other files, independent review, meaningful validation.

Python >=3.9 for base, >=3.10 for supported desktop wheels. Backend must work without PySide6. Use unittest, no additional test framework requirement. Report files, decisions, risks, tests.
