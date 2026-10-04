# Validation — 4 October 2026

## Earlier local validation of main / v2.0.0

The following checks were recorded before the cloud UI handoff. They describe
the original installed UI, not the new handoff UI or this cloud environment.

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

## Cloud UI continuation validation

Continued from `handoff/ui-design-cloud` at
`b1ae5062f622740751ecbaf9068a8db7a91efdf2` in a fresh cloud checkout.
Environment: Linux x86-64, Python 3.12.14, PySide6 6.11.2, Qt offscreen/Fusion.

- **67 automated tests passed**, including the original telemetry/worker suite
  and regressions for interval precedence, subsecond graph time, zero-duration
  graph placement, native focus rendering, generator headers, multirow copy,
  reordered/removed selection, font-aware rows, and narrow enlarged-font layout.
- Public CLI help/version/JSON, source desktop smoke, wheel/source distribution
  builds and x86-64 PyInstaller directory bundle CLI/JSON/desktop smoke passed.
  This is a cloud build, not a cross-distribution release certification.
- Synthetic visual previews inspected in light/dark palettes at 1100×800,
  1024×600 with 14-point font, and compact 480×640 / 360×600 windows with
  14-point font. Also rendered and inspected Qt 2× scale previews, detail
  filtering, native graph keyboard focus, and paused/error/stale states.
- The initial visual pass exposed horizontal overview overflow at enlarged
  fonts. Wrapped graph descriptions and font-dependent card column thresholds
  fixed it; regression checks require no overview horizontal scrolling at
  360px and 480px. Wide detail tables can scroll horizontally by design.
- The README screenshot is refreshed using synthetic telemetry. Additional
  [dark](desktop-preview-dark.png) and [compact enlarged-font](desktop-preview-narrow-large.png)
  previews are checked in. They are offscreen renders, not actual desktop sessions.

Reproduce source validation and fixture screenshots:

```sh
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m thinkpad_monitor --smoke-test
python -m build
python scripts/render_ui_previews.py build/ui-previews --refresh-readme
QT_SCALE_FACTOR=2 python scripts/render_ui_previews.py build/ui-previews-scaled
```

Independent research, implementation and review subagents had disjoint file
ownership. Their changes were reviewed and visually checked by the primary
agent. Worker guards and orderly shutdown remain covered by the regression suite.

## Historical cloud publication attempt

GitHub reads succeeded, but authenticated publication was unavailable in this
cloud workspace (`git push` reports that it cannot read a GitHub username).
The GitHub plugin was not connected. Consequently no new PR or remote CI result
for the continuation is claimed. Public API inspection of the
[handoff commit's CI](https://github.com/hon2838/thinkpad-monitor/actions/runs/37166499747)
confirmed that both x86-64 jobs passed, while ARM64/Python 3.10 aborted during
unit tests with exit 134 after dependency installation, and ARM64/Python 3.13 was
cancelled. Detailed job logs returned HTTP 403 without authentication.

The test harness now explicitly retains one QApplication wrapper for the whole
suite rather than relying on binding-specific ownership. This addresses a
reviewed lifetime risk but is **not a confirmed diagnosis of the ARM abort**.
CI now keeps all matrix jobs running, enables Python fatal-crash tracebacks and
uploads failed test output. The configured x86-64/ARM64 and Python 3.10/3.13
matrix must pass on the continuation before its CI can be considered verified.

## Local modern design continuation (2.1.0)

Recovered and checksum-verified the unpublished cloud source patch, then ran its
67 tests locally before applying further styling. Current local suite: **76 tests
passed** on Fedora, Python 3.14.7 and PySide6 6.11.2. Added meaningful regressions
for runtime theme switching, low-contrast secondary palette roles, physical-pixel
icon sources and enlarged-font status visibility. Primary review corrected an
icon pen-restoration defect, stale palette handling and clipped status labels.

Light/dark, compact enlarged-font and 2× scale synthetic previews were rendered.
The checked-in screenshots now show the current design using synthetic telemetry.
Source desktop smoke and source/wheel builds passed. The local PyInstaller bundle
passed desktop smoke and version checks. The user's launcher was upgraded to
2.1.0 and passed its offscreen smoke check. A live Wayland window collected four
CPU readings and closed cleanly on the current KDE/Intel laptop.

The first current GitHub run passed x86-64/Python 3.10 and 3.13 and ARM64/Python
3.13, but ARM64/Python 3.10 still aborted with PySide6 6.11.2. The desktop extra
now keeps Linux ARM64/Python below 3.12 on PySide6 below 6.11; this dependency
workaround is being verified in the unchanged test matrix. No Python reference
count manipulation or disabled accessibility is used.

Free external providers were used for design research, vector icon implementation,
component styling and independent review with separate file ownership. The primary
agent stopped the component implementation after its styling changes, completed
its verification and reconciled palette, DPI, spacing and status findings.

## Remaining physical release validation

GNOME, Xfce, Cinnamon, MATE,
LXQt, physical ARM64 hardware, AMD/NVIDIA hardware and other laptop brands have
not been physically tested for the new UI. The user's launcher has not been
updated by the cloud continuation. Qt/backend compatibility and injected fixtures support
the design, but do not substitute for those live release checks.

Use source installation on systems with incompatible bundle glibc/graphics
libraries. Qt platform plugin availability is distribution-dependent. No claim
is made that arbitrary Linux distributions or 32-bit desktop wheels are supported.
The GUI waits for an in-flight local read before shutdown; there is no unsafe thread
termination. Kernel-stalled file reads can delay final process exit.
