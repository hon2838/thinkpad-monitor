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

## Desktop UI continuation

The overview uses system palette roles and inherited system fonts, with a sidebar
on wide windows and a page selector on compact windows. Status moves below the
title on compact windows. Cards choose columns from their font-dependent minimum
sizes; descriptions wrap and pages scroll vertically. Wide device tables retain
horizontal scrolling when all device columns cannot fit.

Keyboard shortcuts: Ctrl+R refreshes, Ctrl+P pauses/resumes, Ctrl+F focuses the
current detail filter, Ctrl+C copies visible selected table rows (or all visible
rows when none are selected), Alt+Left/Right changes pages and Ctrl+W closes.
The graph has a native keyboard focus indicator and a textual accessibility
summary. Graph time uses a monotonic clock and labels the latest stored reading,
not the current time; missing readings, failures and pause/resume break traces.
Early subsecond spans remain visible. Actual unavailable values remain explicit;
empty placeholder columns stay blank.

Refresh interval precedence is explicit CLI option, saved setting, then 2 seconds.
Both `--interval 5` and `--interval=5` override saved values. Terminal mode still
defaults to 2 seconds. Table updates preserve multiple selected unique displayed
names through reordering; duplicate names use occurrence order rather than a
persistent hardware identifier.

Guidance reviewed for these decisions:

- [KDE navigation and layout](https://develop.kde.org/hig/layout_and_nav/)
- [KDE accessibility](https://develop.kde.org/hig/accessibility/): system colors,
  visible keyboard focus, enlarged fonts.
- [GNOME adaptive layouts](https://developer.gnome.org/hig/guidelines/adaptive.html)
- [GNOME windows](https://developer.gnome.org/hig/patterns/containers/windows.html)
- [W3C visible focus](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible)
- [W3C status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html)

These principles inform the implementation; they do not imply formal WCAG or
screen-reader certification. See [validation](VALIDATION.md) for the headless
checks and remaining desktop-session coverage.

The kernel documents that hwmon attributes are optional and sensor meanings can
vary by board. This app displays exported chip labels, avoiding assumptions that
an arbitrary sensor is always the CPU. Direct sysfs access also cannot apply all
libsensors board-specific configuration: specialized thermistor/voltage channels
may require a future libsensors provider. Intel/NVIDIA load/VRAM are not invented
when drivers expose no standard equivalent to AMD files.

## Modern desktop styling (2.1)

The desktop uses consistent rounded surfaces, system-relative type sizes,
monochrome vector icons and native palette colours. The toolbar moves beside the
title when its actual content fits and stacks when it does not. Device identity
and metadata are separated from activity cards; hidden usage bars retain their
layout space so cards align without showing invented readings. The graph uses
subtle grid lines, an area gradient and a latest-reading marker, with native
keyboard focus and timestamp-based axes.

Runtime theme changes repolish stylesheet surfaces and refresh card colours after
Qt propagates the palette. Muted text is composed against the real surface and
falls back to a readable native-derived colour. Icons supplied to labels include
physical pixels and device ratios for scaled displays. Compact status labels
reserve enough height for wrapped text, including enlarged fonts.

Further primary guidance:

- [GNOME typography](https://developer.gnome.org/hig/guidelines/typography.html):
  system fonts, relative sizes and a restrained hierarchy.
- [GNOME UI styling](https://developer.gnome.org/hig/guidelines/ui-styling.html):
  system light/dark styles, palette-based custom elements and high-contrast checks.

## Subagent work

EVOT/free Luna was deployed for hardware/desktop/architecture research and an
initial desktop implementation. The initial desktop failed an independent smoke
check and was stopped. OpenCode/free Muse Contributor implemented the collector
and replacement desktop in disjoint files with unittest coverage. Additional
read-only reviews were requested. AGY's research attempt was unavailable because
its headless tool permission configuration denied execution. Primary-agent review
and local runtime checks determine acceptance, not subagent reports alone.
