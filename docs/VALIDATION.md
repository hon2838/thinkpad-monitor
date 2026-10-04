# Validation — 4 October 2026

## Verified locally

- Python 3.14.7, PySide6 6.11.2, Fedora KDE session, Intel x86-64 ThinkPad.
- Public CLI help/version, JSON telemetry, terminal launch and quit through a PTY.
- Qt native **Wayland** (`platformName=wayland`) and **X11/XWayland**
  (`platformName=xcb`) window launch, repeated live collection and clean shutdown
  inside the current KDE session. This is not a standalone X11 desktop-session test.
- Live collector: 12 CPU threads, one battery, one Intel DRM GPU, 34 temperature
  entries and three fan sensors. Intel GPU load/VRAM and restricted RAPL files
  correctly stay unavailable. These counts describe this laptop, not a guarantee
  for every machine.
- **43 automated tests passed.** Fixtures and desktop tests cover multiple arbitrary battery names,
  absent packs, charge/current/energy units, battery states, ARM device-tree model,
  NVIDIA/AMD/Intel/generic DRM discovery, dynamic CPUs, missing/denied/malformed
  sensors, distinct identical-drive sensors, thermal critical trips, counter
  baseline/reset, interface switching, RAPL wrapping and constraint exclusion.
- GUI tests verify collection off the UI thread, persistent worker, automatic
  first refresh, rapid-click queue deduplication, pause/resume, interval control,
  multiple packs, more than 64 sensors, bounded history, small-window reflow and
  shutdown during a slow read.
- Fresh isolated base-only install: CLI version and JSON passed without Qt;
  desktop launch returned the documented installation hint.
- Freedesktop entry validation and shell syntax checks.
- Installer exercised in a temporary HOME and XDG directory containing spaces;
  generated launcher, quoted menu Exec and offscreen desktop smoke passed.
- Local source and wheel builds. Local x86-64 PyInstaller directory bundle:
  version, JSON and offscreen desktop smoke passed. This bundle uses the local
  Fedora system libraries; it is not a portable Ubuntu-based release artifact.
- Installed the app in the current user's local environment with system-provided
  Qt/psutil and registered the **Laptop Monitor** applications-menu entry.

## Remaining release validation

CI workflows are configured for x86-64 / ARM64 and Python 3.10 / 3.13, but have
not been pushed or run remotely during this task. GNOME, Xfce, Cinnamon, MATE,
LXQt, physical ARM64 hardware, AMD/NVIDIA hardware and other laptop brands have
not been physically tested. Qt/backend compatibility and injected fixtures support
the design, but do not substitute for those live release checks.

Use source installation on systems with incompatible bundle glibc/graphics
libraries. Qt platform plugin availability is distribution-dependent. No claim
is made that arbitrary Linux distributions or 32-bit desktop wheels are supported.
The GUI waits for an in-flight local read before shutdown; there is no unsafe thread
termination. Kernel-stalled file reads can delay final process exit.
