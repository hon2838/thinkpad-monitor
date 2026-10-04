"""Unittest suite for thinkpad_monitor.telemetry.Collector.

Uses injected fake sysfs/procfs trees, a fake psutil module and a fake
clock. No real hardware access.
"""

import json
import os
import stat
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from thinkpad_monitor.telemetry import Collector


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, dt):
        self.now += dt


def make_psutil(**over):
    """Minimal fake psutil with sane defaults; override per-test."""
    fake = SimpleNamespace()
    fake.cpu_percent = lambda interval=None, percpu=False: 12.5 if not percpu else [10.0, 20.0]
    fake.cpu_freq = lambda percpu=True: [
        SimpleNamespace(current=2400.0), SimpleNamespace(current=2500.0)]
    fake.virtual_memory = lambda: SimpleNamespace(
        total=16 * 1024**3, used=8 * 1024**3,
        available=8 * 1024**3, percent=50.0)
    fake.swap_memory = lambda: SimpleNamespace(
        total=2 * 1024**3, used=0, percent=0.0)
    fake.disk_usage = lambda path: SimpleNamespace(
        total=500 * 1024**3, used=100 * 1024**3, percent=20.0)
    fake.disk_io_counters = lambda: SimpleNamespace(
        read_bytes=1000, write_bytes=2000)
    fake.net_if_addrs = lambda: {}
    fake.net_if_stats = lambda: {}
    fake.net_io_counters = lambda pernic=True: {}
    for k, v in over.items():
        setattr(fake, k, v)
    return fake


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


class CollectorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sys = os.path.join(self.tmp.name, "sys")
        self.proc = os.path.join(self.tmp.name, "proc")
        os.makedirs(self.sys)
        os.makedirs(self.proc)

    def tearDown(self):
        self.tmp.cleanup()

    def collector(self, psutil=None, clock=None):
        return Collector(sys_root=self.sys, proc_root=self.proc,
                         psutil_module=psutil or make_psutil(),
                         clock=clock or FakeClock())

    # -- batteries -------------------------------------------------------
    def test_multiple_batteries_arbitrary_names_and_units(self):
        for name in ("BAT0", "BAT1", "CustomPack-2"):
            d = os.path.join(self.sys, "class/power_supply", name)
            os.makedirs(d)
            write(os.path.join(d, "type"), "Battery\n")
        # BAT0: energy-based
        b0 = os.path.join(self.sys, "class/power_supply/BAT0")
        write(os.path.join(b0, "status"), "Discharging\n")
        write(os.path.join(b0, "capacity"), "80\n")
        write(os.path.join(b0, "voltage_now"), "12000000\n")  # 12 V
        write(os.path.join(b0, "power_now"), "24000000\n")  # 24 W
        write(os.path.join(b0, "energy_now"), "48000000\n")  # 48 Wh
        write(os.path.join(b0, "energy_full"), "60000000\n")
        write(os.path.join(b0, "energy_full_design"), "75000000\n")
        write(os.path.join(b0, "cycle_count"), "123\n")
        # BAT1: charge/current based, charging
        b1 = os.path.join(self.sys, "class/power_supply/BAT1")
        write(os.path.join(b1, "status"), "Charging\n")
        write(os.path.join(b1, "voltage_now"), "11000000\n")  # 11 V
        write(os.path.join(b1, "current_now"), "2000000\n")  # 2 A -> 22 W
        write(os.path.join(b1, "charge_now"), "2000000\n")  # 2 Ah * 11V = 22 Wh
        write(os.path.join(b1, "charge_full"), "4000000\n")
        write(os.path.join(b1, "charge_full_design"), "5000000\n")
        # CustomPack-2: minimal (status only)
        b2 = os.path.join(self.sys, "class/power_supply/CustomPack-2")
        write(os.path.join(b2, "status"), "Full\n")
        # non-battery must be ignored
        ac = os.path.join(self.sys, "class/power_supply/AC")
        os.makedirs(ac)
        write(os.path.join(ac, "type"), "Mains\n")

        c = self.collector()
        sample = c.sample()
        bats = {b["name"]: b for b in sample["batteries"]}
        self.assertEqual(set(bats), {"BAT0", "BAT1", "CustomPack-2"})

        bat0 = bats["BAT0"]
        self.assertAlmostEqual(bat0["voltage_volts"], 12.0)
        self.assertAlmostEqual(bat0["power_watts"], 24.0)
        self.assertAlmostEqual(bat0["energy_wh"], 48.0)
        self.assertAlmostEqual(bat0["full_energy_wh"], 60.0)
        self.assertAlmostEqual(bat0["health_percent"], 80.0)
        self.assertEqual(bat0["cycles"], 123)
        self.assertEqual(bat0["percent"], 80)
        # 48Wh / 24W = 2h = 7200s
        self.assertEqual(bat0["time_remaining_seconds"], 7200)

        bat1 = bats["BAT1"]
        self.assertAlmostEqual(bat1["voltage_volts"], 11.0)
        self.assertAlmostEqual(bat1["power_watts"], 22.0)
        self.assertAlmostEqual(bat1["energy_wh"], 22.0)
        self.assertAlmostEqual(bat1["health_percent"], 80.0)
        # charging: (44-22)/22 = 1h = 3600s
        self.assertEqual(bat1["time_remaining_seconds"], 3600)

        bat2 = bats["CustomPack-2"]
        self.assertIsNone(bat2["voltage_volts"])
        self.assertIsNone(bat2["power_watts"])
        self.assertIsNone(bat2["percent"])
        self.assertIsNone(bat2["health_percent"])
        self.assertIsNone(bat2["time_remaining_seconds"])

    def test_battery_percent_fallback_from_energy(self):
        d = os.path.join(self.sys, "class/power_supply/BAT9")
        os.makedirs(d)
        write(os.path.join(d, "type"), "Battery\n")
        write(os.path.join(d, "status"), "Discharging\n")
        write(os.path.join(d, "energy_now"), "25000000\n")
        write(os.path.join(d, "energy_full"), "50000000\n")
        sample = self.collector().sample()
        self.assertAlmostEqual(sample["batteries"][0]["percent"], 50.0)

    # -- missing / bad data ----------------------------------------------
    def test_missing_sysfs_gives_nulls_not_crash(self):
        # completely empty sys/proc
        c = self.collector()
        sample = c.sample()
        json.dumps(sample)  # must be serializable
        self.assertEqual(sample["batteries"], [])
        self.assertEqual(sample["gpus"], [])
        self.assertEqual(sample["power"], [])
        self.assertEqual(sample["fans"], [])
        self.assertIsNone(sample["system"]["model"])
        self.assertIsNone(sample["system"]["uptime_seconds"])
        self.assertIsNone(sample["system"]["platform_profile"])
        # numeric nulls, never fabricated zeroes for missing singletons
        self.assertEqual(sample["memory"]["total_bytes"], 16 * 1024**3)

    def test_bad_file_contents_tolerated(self):
        d = os.path.join(self.sys, "class/power_supply/BAT0")
        os.makedirs(d)
        write(os.path.join(d, "type"), "Battery\n")
        write(os.path.join(d, "capacity"), "not-a-number\n")
        write(os.path.join(d, "voltage_now"), "garbage\n")
        write(os.path.join(d, "status"), "Discharging\n")
        hw = os.path.join(self.sys, "class/hwmon/hwmon0")
        os.makedirs(hw)
        write(os.path.join(hw, "name"), "k10temp\n")
        write(os.path.join(hw, "temp1_input"), "oops\n")
        sample = self.collector().sample()
        json.dumps(sample)
        bat = sample["batteries"][0]
        self.assertIsNone(bat["percent"])
        self.assertIsNone(bat["voltage_volts"])
        self.assertEqual(sample["temperatures"], [])

    def test_permission_error_tolerated_with_warning(self):
        from unittest import mock
        d = os.path.join(self.sys, "class/power_supply/BAT0")
        os.makedirs(d)
        write(os.path.join(d, "type"), "Battery\n")
        write(os.path.join(d, "status"), "Discharging\n")
        write(os.path.join(d, "voltage_now"), "12000000\n")
        write(os.path.join(d, "capacity"), "50\n")
        c = self.collector()
        real_read_float = c._read_float

        def flaky(path):
            if path.endswith("voltage_now"):
                raise PermissionError("denied")
            return real_read_float(path)

        with mock.patch.object(c, "_read_float", side_effect=flaky):
            sample = c.sample()
        json.dumps(sample)
        self.assertEqual(len(sample["batteries"]), 1)
        bat = sample["batteries"][0]
        self.assertIsNone(bat["voltage_volts"])
        self.assertEqual(bat["percent"], 50)
        self.assertTrue(any("permission" in w.lower() for w in sample["warnings"]))

    def test_psutil_failure_gives_nulls(self):
        def boom(*a, **k):
            raise RuntimeError("no psutil")
        psu = make_psutil()
        psu.virtual_memory = boom
        psu.swap_memory = boom
        psu.disk_usage = boom
        sample = self.collector(psutil=psu).sample()
        json.dumps(sample)
        self.assertIsNone(sample["memory"]["total_bytes"])
        self.assertIsNone(sample["storage"]["total_bytes"])
        self.assertTrue(any("memory" in w or "storage" in w for w in sample["warnings"]))

    # -- gpus -------------------------------------------------------------
    def test_intel_amd_generic_gpus(self):
        # AMD card
        amd = os.path.join(self.sys, "class/drm/card0/device")
        os.makedirs(amd)
        write(os.path.join(amd, "vendor"), "0x1002\n")
        os.symlink("/tmp/fake-drivers/amdgpu", os.path.join(amd, "driver"))
        write(os.path.join(amd, "gpu_busy_percent"), "42\n")
        write(os.path.join(amd, "mem_info_vram_used"), "1073741824\n")
        write(os.path.join(amd, "mem_info_vram_total"), "4294967296\n")
        # Intel card (no busy file -> null)
        intel = os.path.join(self.sys, "class/drm/card1/device")
        os.makedirs(intel)
        write(os.path.join(intel, "vendor"), "0x8086\n")
        os.symlink("/tmp/fake-drivers/i915", os.path.join(intel, "driver"))
        # generic card (nothing known)
        gen = os.path.join(self.sys, "class/drm/card2/device")
        os.makedirs(gen)
        # non-card entry must be ignored
        os.makedirs(os.path.join(self.sys, "class/drm/card0-HDMI-A-1"))

        sample = self.collector().sample()
        gpus = {g["name"]: g for g in sample["gpus"]}
        self.assertEqual(set(gpus), {"card0", "card1", "card2"})
        self.assertEqual(gpus["card0"]["vendor"], "AMD")
        self.assertEqual(gpus["card0"]["driver"], "amdgpu")
        self.assertEqual(gpus["card0"]["busy_percent"], 42)
        self.assertEqual(gpus["card0"]["memory_used_bytes"], 1073741824)
        self.assertEqual(gpus["card0"]["memory_total_bytes"], 4294967296)
        self.assertEqual(gpus["card1"]["vendor"], "Intel")
        self.assertEqual(gpus["card1"]["driver"], "i915")
        self.assertIsNone(gpus["card1"]["busy_percent"])
        self.assertIsNone(gpus["card1"]["memory_used_bytes"])
        self.assertIsNone(gpus["card2"]["temperature_celsius"])
        self.assertIsNone(gpus["card2"]["busy_percent"])

    def test_gpu_temp_via_associated_hwmon(self):
        dev = os.path.join(self.sys, "class/drm/card0/device")
        os.makedirs(dev)
        write(os.path.join(dev, "vendor"), "0x10de\n")
        hw = os.path.join(self.sys, "class/hwmon/hwmon5")
        os.makedirs(hw)
        write(os.path.join(hw, "name"), "nvidia\n")
        write(os.path.join(hw, "temp1_input"), "55000\n")
        os.symlink(dev, os.path.join(hw, "device"))
        sample = self.collector().sample()
        self.assertAlmostEqual(
            sample["gpus"][0]["temperature_celsius"], 55.0)

    # -- cpu --------------------------------------------------------------
    def test_dynamic_core_counts(self):
        psu2 = make_psutil(
            cpu_percent=lambda interval=None, percpu=False: 30.0 if not percpu else [10.0, 20.0],
            cpu_freq=lambda percpu=True: [SimpleNamespace(current=2000.0)] * 2,
        )
        s2 = self.collector(psutil=psu2).sample()
        self.assertEqual(len(s2["cpu"]["per_core_percent"]), 2)
        self.assertEqual(len(s2["cpu"]["frequencies_mhz"]), 2)

        psu8 = make_psutil(
            cpu_percent=lambda interval=None, percpu=False: 30.0 if not percpu else [5.0] * 8,
            cpu_freq=lambda percpu=True: [SimpleNamespace(current=3000.0)] * 8,
        )
        s8 = self.collector(psutil=psu8).sample()
        self.assertEqual(len(s8["cpu"]["per_core_percent"]), 8)
        self.assertEqual(len(s8["cpu"]["frequencies_mhz"]), 8)

    def test_cpu_freq_sysfs_fallback(self):
        psu = make_psutil()
        psu.cpu_freq = lambda percpu=True: (_ for _ in ()).throw(RuntimeError("x"))
        for i in range(3):
            d = os.path.join(self.sys, f"devices/system/cpu/cpu{i}/cpufreq")
            os.makedirs(d)
            write(os.path.join(d, "scaling_cur_freq"), f"{2000000 + i * 100000}\n")
        sample = self.collector(psutil=psu).sample()
        self.assertEqual(sample["cpu"]["frequencies_mhz"], [2000.0, 2100.0, 2200.0])

    # -- thermals -----------------------------------------------------------
    def test_thermal_sensors_fixed_units(self):
        hw = os.path.join(self.sys, "class/hwmon/hwmon0")
        os.makedirs(hw)
        write(os.path.join(hw, "name"), "k10temp\n")
        write(os.path.join(hw, "temp1_input"), "45000\n")
        write(os.path.join(hw, "temp1_label"), "Tctl\n")
        write(os.path.join(hw, "temp1_crit"), "100000\n")
        tz = os.path.join(self.sys, "class/thermal/thermal_zone0")
        os.makedirs(tz)
        write(os.path.join(tz, "type"), "x86_pkg_temp\n")
        write(os.path.join(tz, "temp"), "47000\n")
        sample = self.collector().sample()
        by_name = {t["name"]: t for t in sample["temperatures"]}
        self.assertAlmostEqual(by_name["k10temp/hwmon0-temp1"]["celsius"], 45.0)
        self.assertEqual(by_name["k10temp/hwmon0-temp1"]["label"], "Tctl")
        self.assertAlmostEqual(by_name["k10temp/hwmon0-temp1"]["critical_celsius"], 100.0)
        self.assertAlmostEqual(
            by_name["thermal_zone0:x86_pkg_temp"]["celsius"], 47.0)

    def test_fans(self):
        hw = os.path.join(self.sys, "class/hwmon/hwmon1")
        os.makedirs(hw)
        write(os.path.join(hw, "name"), "thinkpad\n")
        write(os.path.join(hw, "fan1_input"), "3200\n")
        write(os.path.join(hw, "fan1_label"), "fan1\n")
        sample = self.collector().sample()
        self.assertEqual(len(sample["fans"]), 1)
        self.assertAlmostEqual(sample["fans"][0]["rpm"], 3200.0)

    # -- counters ------------------------------------------------------------
    def test_storage_counters_baseline_and_reset(self):
        clock = FakeClock()
        state = {"r": 10000, "w": 20000}
        psu = make_psutil()
        psu.disk_io_counters = lambda: SimpleNamespace(
            read_bytes=state["r"], write_bytes=state["w"])
        c = self.collector(psutil=psu, clock=clock)
        first = c.sample()
        self.assertEqual(first["storage"]["read_bytes_per_second"], 0.0)
        clock.advance(2.0)
        state["r"] += 4000
        state["w"] += 8000
        second = c.sample()
        self.assertAlmostEqual(second["storage"]["read_bytes_per_second"], 2000.0)
        self.assertAlmostEqual(second["storage"]["write_bytes_per_second"], 4000.0)
        # counter reset -> clamp to zero, never negative
        clock.advance(1.0)
        state["r"] = 100
        state["w"] = 100
        third = c.sample()
        self.assertEqual(third["storage"]["read_bytes_per_second"], 0.0)
        self.assertEqual(third["storage"]["write_bytes_per_second"], 0.0)

    def test_network_interface_switching_and_reset(self):
        clock = FakeClock()
        counters = {"eth0": (1000, 2000)}
        psu = make_psutil()
        psu.net_if_addrs = lambda: {
            k: [SimpleNamespace(address="10.0.0.1", family=2)] for k in counters}
        psu.net_if_stats = lambda: {
            k: SimpleNamespace(isup=True) for k in counters}
        psu.net_io_counters = lambda pernic=True: {
            k: SimpleNamespace(bytes_recv=v[0], bytes_sent=v[1])
            for k, v in counters.items()}
        c = self.collector(psutil=psu, clock=clock)
        first = c.sample()
        self.assertEqual(first["networks"][0]["rx_bytes_per_second"], 0.0)
        clock.advance(1.0)
        counters["eth0"] = (3000, 5000)
        counters["wlan0"] = (500, 500)  # brand-new interface
        second = c.sample()
        by_name = {n["name"]: n for n in second["networks"]}
        self.assertAlmostEqual(by_name["eth0"]["rx_bytes_per_second"], 2000.0)
        self.assertEqual(by_name["wlan0"]["rx_bytes_per_second"], 0.0)
        self.assertEqual(by_name["wlan0"]["received_bytes"], 500)
        # reset on eth0 -> clamp zero
        clock.advance(1.0)
        counters["eth0"] = (10, 10)
        third = c.sample()
        by_name = {n["name"]: n for n in third["networks"]}
        self.assertEqual(by_name["eth0"]["rx_bytes_per_second"], 0.0)

    # -- power / rapl ---------------------------------------------------------
    def test_rapl_power_and_wraparound(self):
        clock = FakeClock()
        dom = os.path.join(self.sys, "class/powercap/intel-rapl:0")
        os.makedirs(dom)
        write(os.path.join(dom, "name"), "package-0\n")
        write(os.path.join(dom, "energy_uj"), "1000000\n")
        write(os.path.join(dom, "max_energy_range_uj"), "10000000\n")
        # constraint limit must be ignored
        write(os.path.join(dom, "constraint_0_power_limit_uw"), "999999999999\n")
        c = self.collector(clock=clock)
        first = c.sample()
        pkg = [p for p in first["power"] if p["name"] == "package-0"]
        self.assertEqual(len(pkg), 1)
        self.assertEqual(pkg[0]["watts"], 0.0)  # baseline
        for p in first["power"]:
            self.assertNotIn("constraint", p["name"])

        clock.advance(2.0)
        write(os.path.join(dom, "energy_uj"), "5000000\n")
        second = c.sample()
        pkg = [p for p in second["power"] if p["name"] == "package-0"][0]
        # (5J - 1J) / 2s = 2W
        self.assertAlmostEqual(pkg["watts"], 2.0)

        # wraparound: counter wraps past max 10J -> small value
        clock.advance(1.0)
        write(os.path.join(dom, "energy_uj"), "1000000\n")
        third = c.sample()
        pkg = [p for p in third["power"] if p["name"] == "package-0"][0]
        # (10J - 5J) + 1J = 6J / 1s = 6W
        self.assertAlmostEqual(pkg["watts"], 6.0)

    def test_hwmon_power_measured_not_constraints(self):
        hw = os.path.join(self.sys, "class/hwmon/hwmon2")
        os.makedirs(hw)
        write(os.path.join(hw, "name"), "amdgpu\n")
        write(os.path.join(hw, "power1_input"), "15000000\n")  # 15 W
        write(os.path.join(hw, "power1_cap"), "30000000\n")  # limit, must not appear
        sample = self.collector().sample()
        watts = [p["watts"] for p in sample["power"] if p["name"] == "amdgpu/hwmon2-power1"]
        self.assertEqual(len(watts), 1)
        self.assertAlmostEqual(watts[0], 15.0)
        for p in sample["power"]:
            self.assertNotIn("cap", p["name"])
            self.assertNotIn("constraint", p["name"])

    def test_json_serializable_end_to_end(self):
        sample = self.collector().sample()
        text = json.dumps(sample)
        back = json.loads(text)
        for key in ("system", "cpu", "memory", "storage", "networks",
                    "batteries", "temperatures", "fans", "gpus",
                    "power", "warnings"):
            self.assertIn(key, back)


if __name__ == "__main__":
    unittest.main()
