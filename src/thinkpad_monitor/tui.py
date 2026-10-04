"""Generic terminal view of the same capability-aware desktop telemetry."""
import curses
import time
from .telemetry import Collector


def value(number, suffix="", digits=1):
    return "Unavailable" if number is None else f"{number:.{digits}f}{suffix}"


def lines(snapshot):
    system = snapshot.get("system", {})
    cpu = snapshot.get("cpu", {})
    memory = snapshot.get("memory", {})
    storage = snapshot.get("storage", {})
    result = ["LAPTOP MONITOR · q quit / Space pause / ↑↓ scroll", "",
              f"{system.get('model') or 'Linux computer'} | {system.get('architecture') or 'Unknown architecture'}",
              f"CPU {value(cpu.get('percent'), '%')} | RAM {value(memory.get('percent'), '%')} | Disk {value(storage.get('percent'), '%')}",
              "", "CPU cores"]
    freqs = cpu.get("frequencies_mhz", [])
    for i, load in enumerate(cpu.get("per_core_percent", [])):
        frequency = freqs[i] if i < len(freqs) else None
        result.append(f"  {i:3}: {value(load, '%'):>12} {value(frequency, ' MHz')}")
    groups = [
        ("Batteries", "batteries", lambda d: f"{d.get('name')}: {value(d.get('percent'), '%')} {d.get('status') or 'Unknown'} | {value(d.get('power_watts'), ' W')} | health {value(d.get('health_percent'), '%')}"),
        ("Network", "networks", lambda d: f"{d.get('name')}: ↓{value(None if d.get('rx_bytes_per_second') is None else d['rx_bytes_per_second']/1024, ' KiB/s')} ↑{value(None if d.get('tx_bytes_per_second') is None else d['tx_bytes_per_second']/1024, ' KiB/s')}"),
        ("Temperatures", "temperatures", lambda d: f"{d.get('name')} / {d.get('label')}: {value(d.get('celsius'), ' °C')}"),
        ("Fans", "fans", lambda d: f"{d.get('name')} / {d.get('label')}: {value(d.get('rpm'), ' RPM', 0)}"),
        ("Graphics", "gpus", lambda d: f"{d.get('name')} ({d.get('vendor')}): {value(d.get('busy_percent'), '%')} {value(d.get('temperature_celsius'), ' °C')}"),
        ("Measured power", "power", lambda d: f"{d.get('name')}: {value(d.get('watts'), ' W')}")]
    for title, key, render in groups:
        result += ["", title]
        result += ["  " + render(item) for item in snapshot.get(key, [])] or ["  Unavailable"]
    result += ["", *snapshot.get("warnings", [])]
    return result


def main(interval=2.0):
    def run(screen):
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        screen.timeout(100)
        screen.keypad(True)
        collector = Collector()
        snapshot, next_refresh, paused, offset = {}, 0.0, False, 0
        while True:
            now = time.monotonic()
            if not paused and now >= next_refresh:
                snapshot = collector.sample()
                next_refresh = now + interval
            content = lines(snapshot)
            height, width = screen.getmaxyx()
            offset = min(offset, max(0, len(content) - max(1, height - 1)))
            screen.erase()
            for y, line in enumerate(content[offset:offset + max(0, height - 1)]):
                try:
                    screen.addnstr(y, 0, line, max(0, width - 1))
                except curses.error:
                    pass
            screen.refresh()
            key = screen.getch()
            if key in (ord('q'), ord('Q'), 27):
                return
            if key == ord(' '):
                paused = not paused
                next_refresh = 0
            elif key == curses.KEY_DOWN:
                offset += 1
            elif key == curses.KEY_UP:
                offset = max(0, offset - 1)
    curses.wrapper(run)
