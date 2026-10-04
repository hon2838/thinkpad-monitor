"""Shared entry point with dependency-free diagnostics and explicit modes."""
import argparse
import json
import math
import os
import sys
import time

from . import __version__


def refresh_interval(value):
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("interval must be a number")
    if not math.isfinite(number) or not 0.5 <= number <= 60:
        raise argparse.ArgumentTypeError("interval must be between 0.5 and 60 seconds")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Linux laptop hardware monitor")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--desktop", action="store_true", help="open the native Qt desktop app")
    modes.add_argument("--tui", action="store_true", help="use the generic terminal dashboard")
    modes.add_argument("--legacy-tui", action="store_true", help="original specialist ThinkPad/AMD dashboard")
    modes.add_argument("--json", action="store_true", help="print a telemetry snapshot without a display")
    parser.add_argument("--interval", type=refresh_interval, default=None, help="refresh seconds (0.5–60; desktop remembers its last setting, terminal defaults to 2)")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--smoke-test", action="store_true", help="validate desktop offscreen and exit")
    parser.add_argument("--screenshot", metavar="PATH", help="capture desktop preview offscreen and exit")
    args = parser.parse_args(argv)
    if not sys.platform.startswith("linux"):
        parser.error("Laptop Monitor requires Linux")
    if args.json:
        from .telemetry import Collector
        collector = Collector()
        collector.sample()
        time.sleep(0.1)
        print(json.dumps(collector.sample(), indent=2, allow_nan=False))
        return 0
    if args.legacy_tui:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            parser.error("the terminal dashboard needs an interactive terminal; use --json")
        from .monitor import main as legacy
        legacy()
        return 0
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if args.desktop or args.smoke_test or args.screenshot or (has_display and not args.tui):
        if not has_display and not (args.smoke_test or args.screenshot):
            parser.error("no graphical session detected; use --tui or --json")
        try:
            import PySide6
        except ImportError:
            print("Desktop support is missing. Install with: pip install 'thinkpad-monitor[desktop]'\n"
                  "Or use thinkpad-monitor --tui / --json.", file=sys.stderr)
            return 2
        if sys.version_info < (3, 10):
            print("Desktop support needs Python 3.10 or newer.", file=sys.stderr)
            return 2
        from .desktop import main as desktop
        desktop_args = [] if args.interval is None else ["--interval", str(args.interval)]
        if args.smoke_test:
            desktop_args.append("--smoke-test")
        if args.screenshot:
            desktop_args += ["--screenshot", args.screenshot]
        return desktop(desktop_args) or 0
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("no interactive terminal detected; use --json")
    from .tui import main as terminal
    terminal(interval=2.0 if args.interval is None else args.interval)
    return 0


def desktop_main():
    return main(["--desktop", *sys.argv[1:]])
