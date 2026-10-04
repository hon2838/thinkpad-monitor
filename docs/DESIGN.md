# Design and research

The original application couples a curses UI with brand-specific telemetry and
assumes a single battery, fixed core counts, AMD DRM attributes and a terminal
launcher. Its generic fallback treats a RAPL power constraint as measured draw,
which is not a valid measurement. The redesigned public desktop, terminal and
JSON views share a read-only collector and have no vendor or x86-only runtime
requirement. The original terminal remains explicitly optional for specialist use.

## Decisions

- **Qt Widgets / PySide6**: ordinary resizable windows, native theme and fonts,
  keyboard navigation, Wayland/X11 plugins and freedesktop application entries.
  No shell extension, web server, browser, OpenGL dashboard or tray requirement.
  Qt's official supported platform matrix includes Linux x86-64 and ARM64;
  compatibility still depends on host libraries and available Python wheels.
- **Common base**: psutil for CPU, memory, disk and network; generic power_supply,
  hwmon, thermal and DRM discovery for optional hardware. All packs/cards/sensors
  are rediscovered each sample. Dynamic lists have no fixed sensor/core limit.
- **Honest missing data**: unavailable fields are JSON null and human-readable
  unavailable labels. Zero fan RPM is retained. Malformed/nonfinite values are
  ignored, permission failures are reported, and each field can fail independently.
- **Power measurements**: fixed ABI units; hwmon power readings and RAPL energy
  deltas with counter wrapping. Constraints are never presented as measured power
  in the generic views. First rate readings establish baselines.
- **Portable installation**: dedicated user-local venv, XDG data directory,
  launcher with properly quoted paths and matching icon. No system-Python override
  or automatic privileged package installation. Desktop and base dependencies are
  separate. Native bundles are labelled by architecture and build platform.
- **Responsive sampling**: one persistent Qt worker thread; requests originate
  from a guarded UI signal. Automatic startup, refresh, pause and shutdown are
  tested. A pending read finishes before closing the window; no thread termination.

## Primary references

- [Qt supported platforms](https://doc.qt.io/qt-6/supported-platforms.html)
- [Qt for Python platform support](https://doc.qt.io/qtforpython-6/overviews/qtdoc-supported-platforms.html)
- [Wayland and Qt](https://doc.qt.io/qt-6/wayland-and-qt.html)
- [Kernel power_supply ABI and units](https://docs.kernel.org/power/power_supply_class.html)
- [Kernel hwmon optional attributes and units](https://docs.kernel.org/hwmon/sysfs-interface.html)
- [Desktop Exec quoting](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html)
- [psutil CPU measurements](https://psutil.readthedocs.io/en/latest/#psutil.cpu_percent)

The kernel documents that hwmon attributes are optional and sensor meanings can
vary by board. This app displays exported chip labels, avoiding assumptions that
an arbitrary sensor is always the CPU. Direct sysfs access also cannot apply all
libsensors board-specific configuration: specialized thermistor/voltage channels
may require a future libsensors provider. Intel/NVIDIA load/VRAM are not invented
when drivers expose no standard equivalent to AMD files.

## Subagent work

EVOT/free Luna was deployed for hardware/desktop/architecture research and an
initial desktop implementation. The initial desktop failed an independent smoke
check and was stopped. OpenCode/free Muse Contributor implemented the collector
and replacement desktop in disjoint files with unittest coverage. Additional
read-only reviews were requested. AGY's research attempt was unavailable because
its headless tool permission configuration denied execution. Primary-agent review
and local runtime checks determine acceptance, not subagent reports alone.
