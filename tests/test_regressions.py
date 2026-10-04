"""Independent tests for review findings and public launch behavior."""
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_telemetry as fixtures
from test_telemetry import write, make_psutil
from thinkpad_monitor import cli
from thinkpad_monitor.tui import lines


class HardwareRegressions(unittest.TestCase):
    setUp = fixtures.CollectorTest.setUp
    tearDown = fixtures.CollectorTest.tearDown
    collector = fixtures.CollectorTest.collector

    def test_absent_battery_is_not_a_pack(self):
        base = os.path.join(self.sys, 'class/power_supply/AbsentPack')
        write(os.path.join(base, 'type'), 'Battery')
        write(os.path.join(base, 'present'), '0')
        self.assertEqual(self.collector().sample()['batteries'], [])

    def test_not_charging_has_no_charge_eta(self):
        base = os.path.join(self.sys, 'class/power_supply/Pack')
        for key, val in {'type': 'Battery', 'status': 'Not charging',
                         'energy_now': '10000000', 'energy_full': '50000000',
                         'power_now': '1000000'}.items():
            write(os.path.join(base, key), val)
        self.assertIsNone(self.collector().sample()['batteries'][0]['time_remaining_seconds'])

    def test_identical_drives_keep_distinct_sensors(self):
        for index in range(2):
            base = os.path.join(self.sys, f'class/hwmon/hwmon{index}')
            write(os.path.join(base, 'name'), 'nvme')
            write(os.path.join(base, 'temp1_input'), '42000')
            write(os.path.join(base, 'temp1_label'), 'Composite')
        temperatures = self.collector().sample()['temperatures']
        self.assertEqual(len(temperatures), 2)
        self.assertNotEqual(temperatures[0]['name'], temperatures[1]['name'])

    def test_nonfinite_sensor_values_are_null(self):
        base = os.path.join(self.sys, 'class/power_supply/Pack')
        for key, val in {'type': 'Battery', 'energy_now': 'nan',
                         'energy_full': 'inf', 'voltage_now': '-inf'}.items():
            write(os.path.join(base, key), val)
        snapshot = self.collector().sample()
        json.dumps(snapshot, allow_nan=False)
        self.assertIsNone(snapshot['batteries'][0]['energy_wh'])

    def test_thermal_critical_trip_point(self):
        base = os.path.join(self.sys, 'class/thermal/thermal_zone0')
        for key, val in {'type': 'soc', 'temp': '70000',
                         'trip_point_0_type': 'passive', 'trip_point_0_temp': '80000',
                         'trip_point_1_type': 'critical', 'trip_point_1_temp': '100000'}.items():
            write(os.path.join(base, key), val)
        self.assertEqual(self.collector().sample()['temperatures'][0]['critical_celsius'], 100)


class PublicEntryTests(unittest.TestCase):
    def test_help_and_version_do_not_import_optional_gui(self):
        for arg in ['--help', '--version']:
            code = ('import sys; from thinkpad_monitor.cli import main; '
                    f'\ntry: main([{arg!r}])\nexcept SystemExit as e: assert e.code == 0\n'
                    'assert "PySide6" not in sys.modules\n'
                    'assert "thinkpad_monitor.monitor" not in sys.modules\n')
            result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_interval_is_rejected(self):
        for value in ['nan', 'inf', '-1', '0', '100', 'invalid']:
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    cli.main(['--json', '--interval', value])
                self.assertEqual(error.exception.code, 2)

    def test_desktop_without_display_is_actionable(self):
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(io.StringIO()) as output:
            with self.assertRaises(SystemExit):
                cli.main(['--desktop'])
        self.assertIn('--tui or --json', output.getvalue())

    def test_terminal_missing_values_and_zero_differ(self):
        output = '\n'.join(lines({'cpu': {'percent': None}, 'memory': {'percent': 0}}))
        self.assertIn('CPU Unavailable', output)
        self.assertIn('RAM 0.0%', output)

class PlatformRegressions(unittest.TestCase):
    setUp = fixtures.CollectorTest.setUp
    tearDown = fixtures.CollectorTest.tearDown
    collector = fixtures.CollectorTest.collector

    def test_arm_device_tree_model_without_dmi(self):
        write(os.path.join(self.sys, 'firmware/devicetree/base/model'), 'ARM Laptop\x00')
        with patch('thinkpad_monitor.telemetry.platform.machine', return_value='aarch64'):
            system = self.collector().sample()['system']
        self.assertEqual(system['model'], 'ARM Laptop')
        self.assertEqual(system['architecture'], 'aarch64')

    def test_nvidia_discovery_without_optional_tools(self):
        write(os.path.join(self.sys, 'class/drm/card7/device/vendor'), '0x10de')
        gpu = self.collector().sample()['gpus'][0]
        self.assertEqual(gpu['vendor'], 'NVIDIA')
        self.assertIsNone(gpu['busy_percent'])
