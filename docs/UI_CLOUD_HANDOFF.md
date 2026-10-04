# UI continuation handoff

Prepared 2026-10-04 at the user's request to transfer remaining work to a cloud agent.

## Scope and repository

Repository: https://github.com/hon2838/thinkpad-monitor

The original Linux laptop compatibility and native desktop implementation is on
`main` at `9e10dac072983338f6d4669408595495b25acf8f` (version 2.0.0).
Continue the unfinished UI improvement work from `handoff/ui-design-cloud`.
This snapshot is work in progress, not a completed release.

**Historical cloud continuation:** the review findings below have been addressed in the
working continuation, with 67 passing tests and refreshed synthetic previews.
See `docs/VALIDATION.md` for current evidence and the GitHub authentication
blocker. This document preserves the original handoff context; publication and
remote CI are still required before the complete task can be called finished.

User requirements: make the app useful across laptop vendors, x86-64 and ARM64,
and major Linux desktop environments; use research and implementation subagents;
improve the UI using current industry guidance; commit and push completed work
to GitHub each time. Independently review delegated implementation and run
relevant tests. Do not claim physical hardware or desktop environment coverage
from headless tests alone.

**Local continuation:** the unpublished cloud source patch from commit
`d81016da8b4abfba1fac5aa4fb28136862090bb0` was recovered and verified using SHA256
`848924f2f28da217b2b3692be8146623b01044ca2db11acc2700eb5cfdf8dcaa`. Its fixes were
revalidated before the further modern styling pass. See current validation and
design documentation; this file preserves the original handoff history.

## Work included in the snapshot

- `src/thinkpad_monitor/desktop.py`: adaptive sidebar and compact navigation,
  responsive metric cards, native palette styling, filterable detail panels,
  copy actions, keyboard shortcuts, per-core CPU rows, freshness/error/paused
  status, graph gaps, plain text labels and optional window/page/interval settings.
- `src/thinkpad_monitor/ui_components.py`: extracted metric cards, usage bars,
  timestamped CPU graph, and accessible/filterable/copyable detail table.
- `tests/test_ui_components.py` and `tests/test_ui_design.py`: component and
  interaction regressions.
- `.github/workflows/test.yml` and `release.yml`: install Qt runtime libraries
  before running headless desktop tests/builds.

Research used primary KDE HIG, GNOME HIG and W3C accessibility guidance:

- https://develop.kde.org/hig/layout_and_nav/
- https://develop.kde.org/hig/accessibility/
- https://developer.gnome.org/hig/guidelines/adaptive.html
- https://developer.gnome.org/hig/patterns/containers/windows.html
- https://www.w3.org/WAI/WCAG22/Understanding/focus-visible
- https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html

Principles: native theme and font respect, clear hierarchy, adaptive navigation,
keyboard access, readable unavailable states, truthful status and chart time.
No formal accessibility conformance or screen-reader certification is claimed.

## Verified and unverified

Latest local run passed all 61 tests on Fedora with Python 3.14.7 and PySide6 6.11.2:

```sh
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

`git diff --check` also passed. The original v2.0.0 desktop was installed and
opened locally, including Wayland and XWayland smoke checks. The new UI snapshot
has NOT been installed into the user's launcher. Cloud agents cannot validate
the user's hardware or local desktop session directly.

Original main CI failed because Ubuntu lacked `libEGL.so.1`:
https://github.com/hon2838/thinkpad-monitor/actions/runs/37166101630
The workflow dependency changes in this snapshot are a proposed fix and require
remote matrix verification. Follow the existing project matrix and build checks.

An early UI screenshot was inspected before the latest styling adjustments.
The final snapshot still needs visual checks in light/dark themes, narrow laptop
windows, enlarged fonts and scaling. `docs/desktop-preview.png` still shows the
original UI and must be refreshed once the new design is verified.

## Concrete remaining review and implementation

Review the complete diff first. Independently confirm the following concerns;
they are observations or hypotheses, not all proven bugs:

1. CPU graph rounds short durations to `last 0s` and `-0s`; show truthful useful
   time labels during early sampling. Its default timestamp uses `time.time()`
   while normal desktop callers provide monotonic time; standardize time handling.
   Consider whether `now` is accurate when paused or stale.
2. CPU graph accepts keyboard focus but its custom paint currently lacks an
   obvious focus indicator. Draw native focus or choose an appropriate accessible
   read-only interaction model. Test keyboard focus and usable textual summaries.
3. Detail table selection restoration may collapse multiple selected rows;
   add a discriminating multi-row update/copy test. Check font-aware row sizing
   instead of the fixed 32-pixel height, and avoid losing iterable headers by
   repeatedly converting the same generator to a list.
4. Clean up the dead boolean expression in `_coerce_percent`. Review empty row
   placeholder cells so missing values are useful rather than repetitive.
5. Verify CLI interval defaults do not override persisted interval settings
   unintentionally. Cover explicit command-line interval precedence.
6. Verify narrow layout, 14-point system font, high DPI, light/dark palette,
   error/paused/stale status and filtering/copy shortcuts visually. Preserve the
   background telemetry worker shutdown and collection guards.
7. Update design/validation documentation and the screenshot to reflect final
   behavior, then validate CLI, desktop smoke, tests, packaging and remote CI.
   Read the repository's existing documentation for build commands and limits.
8. Commit and push finished work. A reviewable PR is useful for this unfinished
   branch; do not silently claim a release/deployment or hardware certification.
   If cloud GitHub write access is unavailable, report that limitation explicitly
   and leave the completed patch available for publication.

Use available subagents with disjoint file ownership for implementation and an
independent review. The original local external subagents are finished; no agent
process or local temporary file is required to continue from this branch.
