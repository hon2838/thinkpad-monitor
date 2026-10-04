"""Generic Linux laptop telemetry collector.

Read-only. Never writes to sysfs/procfs, never spawns subprocesses.
All sysfs/procfs locations are rooted at ``sys_root``/``proc_root`` so tests
can inject fake trees. A fake psutil module and a fake clock can also be
injected for deterministic unit tests.

Fixed unit conversions (no heuristics):
  temp*_input / thermal temp : millidegree C  -> C  (/1000)
  voltage_now               : microvolt      -> V  (/1e6)
  power_now / power*_input  : microwatt      -> W  (/1e6)
  energy_*                  : microwatt-hour -> Wh (/1e6)
  current_now               : microamp       -> A  (/1e6)
  charge_*                  : microamp-hour  -> Ah (/1e6)
  scaling_cur_freq          : kilohertz      -> MHz (/1000)
  RAPL energy_uj            : microjoule     -> J  (/1e6)
"""

import math
import os
import platform
import re
import socket
import time


_CARD_RE = re.compile(r"^card(\d+)$")
_TEMP_INPUT_RE = re.compile(r"^(temp\d+)_input$")
_FAN_INPUT_RE = re.compile(r"^(fan\d+)_input$")
_POWER_INPUT_RE = re.compile(r"^(power\d+)_input$")
_POWER_AVG_RE = re.compile(r"^(power\d+)_average$")
_CPU_DIR_RE = re.compile(r"^cpu(\d+)$")

_PCI_VENDORS = {
    "0x1002": "AMD",
    "0x8086": "Intel",
    "0x10de": "NVIDIA",
}

_DRIVER_VENDORS = {
    "amdgpu": "AMD",
    "radeon": "AMD",
    "i915": "Intel",
    "xe": "Intel",
    "nvidia": "NVIDIA",
    "nouveau": "NVIDIA",
}


def _clean_num(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int,)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    return value


class Collector:
    """Collect a JSON-serializable snapshot of laptop telemetry."""

    def __init__(self, sys_root="/sys", proc_root="/proc",
                 psutil_module=None, clock=None):
        self.sys_root = sys_root
        self.proc_root = proc_root
        if psutil_module is None:
            import psutil as _psutil
            self._psutil = _psutil
        else:
            self._psutil = psutil_module
        self._clock = clock if clock is not None else time.monotonic
        self._prev_disk = None       # (read_bytes, write_bytes, t)
        self._prev_net = {}          # iface -> (rx, tx, t)
        self._prev_rapl = {}         # energy_path -> (energy_uj, t)

    # -- low level helpers -------------------------------------------------
    def _p(self, *parts):
        return os.path.join(*parts)

    def _read_text(self, path):
        try:
            with open(path, "r") as f:
                return f.read().strip()
        except FileNotFoundError:
            return None
        except (PermissionError, OSError):
            raise
        except Exception:
            return None

    def _read_float(self, path):
        try:
            with open(path, "r") as f:
                return _clean_num(float(f.read().strip()))
        except FileNotFoundError:
            return None
        except (PermissionError, OSError):
            raise
        except (ValueError, Exception):
            return None

    def _read_int(self, path):
        try:
            with open(path, "r") as f:
                return int(float(f.read().strip()))
        except FileNotFoundError:
            return None
        except (PermissionError, OSError):
            raise
        except (ValueError, Exception):
            return None

    def _listdir(self, path):
        try:
            return sorted(os.listdir(path))
        except (FileNotFoundError, NotADirectoryError):
            return []
        except (PermissionError, OSError):
            raise
        except Exception:
            return []

    # -- public ------------------------------------------------------------
    def sample(self):
        now = self._clock()
        warnings = []
        data = {}
        data["system"] = self._sample_system(warnings)
        data["cpu"] = self._sample_cpu(warnings)
        data["memory"] = self._sample_memory(warnings)
        data["storage"] = self._sample_storage(now, warnings)
        data["networks"] = self._sample_networks(now, warnings)
        data["batteries"] = self._sample_batteries(warnings)
        data["temperatures"] = self._sample_temperatures(warnings)
        data["fans"] = self._sample_fans(warnings)
        data["gpus"] = self._sample_gpus(warnings)
        data["power"] = self._sample_power(now, warnings)
        data["warnings"] = warnings
        return data

    # -- system ------------------------------------------------------------
    def _sample_system(self, warnings):
        hostname = None
        try:
            hostname = socket.gethostname()
        except Exception as e:
            warnings.append(f"system: hostname unavailable: {e}")
            hostname = None
        model = None
        try:
            raw = self._read_text(self._p(self.sys_root, "class/dmi/id/product_name"))
            version = self._read_text(self._p(self.sys_root, "class/dmi/id/product_version"))
            if version and version.lower() not in ("none", "default string", "to be filled by o.e.m."):
                raw = version
            if not raw:
                raw = self._read_text(self._p(self.sys_root, "firmware/devicetree/base/model"))
                if raw:
                    raw = raw.rstrip("\x00")
            if raw:
                model = raw
        except (PermissionError, OSError) as e:
            warnings.append(f"system: model unreadable: {e}")
        try:
            arch = platform.machine() or None
        except Exception:
            arch = None
        try:
            kernel = platform.release() or None
        except Exception:
            kernel = None
        uptime = None
        try:
            txt = self._read_text(self._p(self.proc_root, "uptime"))
            if txt:
                uptime = float(txt.split()[0])
                uptime = _clean_num(uptime)
            else:
                # missing file is normal in minimal containers; no warning
                uptime = None
        except (PermissionError, OSError) as e:
            warnings.append(f"system: uptime unreadable: {e}")
            uptime = None
        except (ValueError, IndexError):
            warnings.append("system: uptime malformed")
            uptime = None
        profile = None
        try:
            # Absent on ARM / non-ACPI machines: not a warning.
            profile = self._read_text(
                self._p(self.sys_root, "firmware/acpi/platform_profile"))
            if profile == "":
                profile = None
        except (PermissionError, OSError) as e:
            warnings.append(f"system: platform_profile unreadable: {e}")
            profile = None
        return {
            "hostname": hostname,
            "model": model,
            "architecture": arch,
            "kernel": kernel,
            "uptime_seconds": uptime,
            "platform_profile": profile,
        }

    # -- cpu ---------------------------------------------------------------
    def _sample_cpu(self, warnings):
        percent = None
        per_core = []
        try:
            percent = self._psutil.cpu_percent(interval=None)
            percent = _clean_num(float(percent))
        except Exception as e:
            warnings.append(f"cpu: percent unavailable: {e}")
            percent = None
        try:
            raw = self._psutil.cpu_percent(interval=None, percpu=True)
            per_core = [_clean_num(float(v)) for v in list(raw)]
        except TypeError:
            # fake psutil without percpu kw or other signature; try again
            try:
                raw = self._psutil.cpu_percent(percpu=True)
                per_core = [_clean_num(float(v)) for v in list(raw)]
            except Exception as e:
                warnings.append(f"cpu: per-core percent unavailable: {e}")
                per_core = []
        except Exception as e:
            warnings.append(f"cpu: per-core percent unavailable: {e}")
            per_core = []

        freqs = []
        try:
            raw = self._psutil.cpu_freq(percpu=True)
            if raw:
                for entry in raw:
                    cur = getattr(entry, "current", None)
                    freqs.append(_clean_num(float(cur)) if cur is not None else None)
            else:
                freqs = []
        except Exception:
            freqs = []
        if not freqs:
            # sysfs fallback (kHz -> MHz), dynamic core discovery
            freqs = self._cpu_freqs_sysfs(warnings)

        load = [None, None, None]
        try:
            import os as _os
            la = _os.getloadavg()
            load = [_clean_num(float(v)) for v in la]
        except Exception as e:
            warnings.append(f"cpu: load average unavailable: {e}")
            load = [None, None, None]

        governor = None
        driver = None
        try:
            governor = self._read_text(self._p(
                self.sys_root, "devices/system/cpu/cpu0/cpufreq/scaling_governor"))
        except (PermissionError, OSError) as e:
            warnings.append(f"cpu: governor unreadable: {e}")
        try:
            driver = self._read_text(self._p(
                self.sys_root, "devices/system/cpu/cpu0/cpufreq/scaling_driver"))
        except (PermissionError, OSError) as e:
            warnings.append(f"cpu: driver unreadable: {e}")
        return {
            "percent": percent,
            "per_core_percent": per_core,
            "frequencies_mhz": freqs,
            "load_average": load,
            "governor": governor,
            "driver": driver,
        }

    def _cpu_freqs_sysfs(self, warnings):
        base = self._p(self.sys_root, "devices/system/cpu")
        out = []
        try:
            entries = self._listdir(base)
        except (PermissionError, OSError) as e:
            warnings.append(f"cpu: cpufreq scan unreadable: {e}")
            return []
        cpus = sorted([d for d in entries if _CPU_DIR_RE.match(d)],
                      key=lambda d: int(d[3:]))
        for cpu in cpus:
            path = self._p(base, cpu, "cpufreq/scaling_cur_freq")
            try:
                raw = self._read_float(path)
            except (PermissionError, OSError):
                warnings.append(f"cpu: {cpu} frequency unreadable (permission)")
                out.append(None)
                continue
            if raw is None:
                out.append(None)
            else:
                out.append(_clean_num(raw / 1000.0))
        return out

    # -- memory ------------------------------------------------------------
    def _sample_memory(self, warnings):
        total = used = avail = pct = None
        stotal = sused = spct = None
        try:
            vm = self._psutil.virtual_memory()
            total = _clean_num(int(vm.total)) if getattr(vm, "total", None) is not None else None
            used = _clean_num(int(vm.used)) if getattr(vm, "used", None) is not None else None
            avail = _clean_num(int(vm.available)) if getattr(vm, "available", None) is not None else None
            pct = _clean_num(float(vm.percent)) if getattr(vm, "percent", None) is not None else None
        except Exception as e:
            warnings.append(f"memory: virtual memory unavailable: {e}")
        try:
            sw = self._psutil.swap_memory()
            stotal = _clean_num(int(sw.total)) if getattr(sw, "total", None) is not None else None
            sused = _clean_num(int(sw.used)) if getattr(sw, "used", None) is not None else None
            spct = _clean_num(float(sw.percent)) if getattr(sw, "percent", None) is not None else None
        except Exception as e:
            warnings.append(f"memory: swap unavailable: {e}")
        return {
            "total_bytes": total,
            "used_bytes": used,
            "available_bytes": avail,
            "percent": pct,
            "swap_total_bytes": stotal,
            "swap_used_bytes": sused,
            "swap_percent": spct,
        }

    # -- storage -----------------------------------------------------------
    def _sample_storage(self, now, warnings):
        total = used = pct = None
        try:
            du = self._psutil.disk_usage("/")
            total = _clean_num(int(du.total))
            used = _clean_num(int(du.used))
            pct = _clean_num(float(du.percent))
        except Exception as e:
            warnings.append(f"storage: disk usage unavailable: {e}")
        read_ps = None
        write_ps = None
        try:
            dio = self._psutil.disk_io_counters()
        except Exception as e:
            warnings.append(f"storage: disk counters unavailable: {e}")
            dio = None
        if dio is None:
            read_ps = None
            write_ps = None
        else:
            try:
                r = int(dio.read_bytes)
                w = int(dio.write_bytes)
            except Exception as e:
                warnings.append(f"storage: disk counters malformed: {e}")
                read_ps = write_ps = None
            else:
                if self._prev_disk is None:
                    read_ps = 0.0
                    write_ps = 0.0
                else:
                    pr, pw, pt = self._prev_disk
                    dt = now - pt
                    if dt <= 0:
                        read_ps = 0.0
                        write_ps = 0.0
                    else:
                        dr = r - pr
                        dw = w - pw
                        # clamp resets / wraparound to zero (monotonic)
                        read_ps = 0.0 if dr < 0 else dr / dt
                        write_ps = 0.0 if dw < 0 else dw / dt
                self._prev_disk = (r, w, now)
        return {
            "total_bytes": total,
            "used_bytes": used,
            "percent": pct,
            "read_bytes_per_second": read_ps,
            "write_bytes_per_second": write_ps,
        }

    # -- networks ----------------------------------------------------------
    def _sample_networks(self, now, warnings):
        try:
            addrs = self._psutil.net_if_addrs()
        except Exception as e:
            warnings.append(f"networks: addresses unavailable: {e}")
            addrs = {}
        try:
            stats = self._psutil.net_if_stats()
        except Exception as e:
            warnings.append(f"networks: link stats unavailable: {e}")
            stats = {}
        try:
            counters = self._psutil.net_io_counters(pernic=True)
        except Exception as e:
            warnings.append(f"networks: counters unavailable: {e}")
            counters = {}
        if addrs is None:
            addrs = {}
        if stats is None:
            stats = {}
        if counters is None:
            counters = {}

        ifaces = sorted(set(list(addrs.keys()) + list(stats.keys()) + list(counters.keys())))
        out = []
        new_prev = {}
        for iface in ifaces:
            addr_list = []
            try:
                for a in (addrs.get(iface) or []):
                    if hasattr(a, "address"):
                        if a.address:
                            addr_list.append(str(a.address))
                    elif isinstance(a, (list, tuple)) and len(a) >= 2:
                        addr_list.append(str(a[1]))
                    elif isinstance(a, str):
                        addr_list.append(a)
            except Exception:
                addr_list = []
            is_up = None
            try:
                st = stats.get(iface)
                if st is not None and getattr(st, "isup", None) is not None:
                    is_up = bool(st.isup)
            except Exception:
                is_up = None
            cnt = counters.get(iface)
            rx = tx = None
            rx_ps = tx_ps = None
            if cnt is not None:
                try:
                    rx = int(cnt.bytes_recv)
                    tx = int(cnt.bytes_sent)
                except Exception:
                    warnings.append(f"networks: {iface} counters malformed")
                    rx = tx = None
                    rx_ps = tx_ps = None
                else:
                    prev = self._prev_net.get(iface)
                    if prev is None:
                        rx_ps = 0.0
                        tx_ps = 0.0
                    else:
                        prx, ptx, pt = prev
                        dt = now - pt
                        if dt <= 0:
                            rx_ps = 0.0
                            tx_ps = 0.0
                        else:
                            drx = rx - prx
                            dtx = tx - ptx
                            rx_ps = 0.0 if drx < 0 else drx / dt
                            tx_ps = 0.0 if dtx < 0 else dtx / dt
                    new_prev[iface] = (rx, tx, now)
            else:
                rx_ps = None
                tx_ps = None
            out.append({
                "name": iface,
                "addresses": addr_list,
                "is_up": is_up,
                "rx_bytes_per_second": rx_ps,
                "tx_bytes_per_second": tx_ps,
                "received_bytes": rx,
                "sent_bytes": tx,
            })
        self._prev_net = new_prev
        return out

    # -- batteries ---------------------------------------------------------
    def _sample_batteries(self, warnings):
        base = self._p(self.sys_root, "class/power_supply")
        out = []
        try:
            entries = self._listdir(base)
        except (PermissionError, OSError) as e:
            warnings.append(f"batteries: power_supply scan unreadable: {e}")
            return []
        for name in entries:
            bdir = self._p(base, name)
            try:
                typ = self._read_text(self._p(bdir, "type"))
            except (PermissionError, OSError):
                warnings.append(f"batteries: {name} type unreadable (permission)")
                continue
            if typ != "Battery":
                continue
            try:
                present = self._read_int(self._p(bdir, "present"))
            except (PermissionError, OSError):
                warnings.append(f"batteries: {name} presence unreadable (permission)")
                present = None
            if present == 0:
                continue
            try:
                out.append(self._read_battery(name, bdir, warnings))
            except (PermissionError, OSError) as e:
                warnings.append(f"batteries: {name} unreadable: {e}")
                continue
        return out

    def _read_battery(self, name, bdir, warnings):
        def get(fname):
            try:
                return self._read_text(self._p(bdir, fname))
            except (PermissionError, OSError):
                warnings.append(f"batteries: {name}/{fname} unreadable (permission)")
                return None
            except Exception:
                return None

        def getf(fname):
            try:
                return self._read_float(self._p(bdir, fname))
            except (PermissionError, OSError):
                warnings.append(f"batteries: {name}/{fname} unreadable (permission)")
                return None
            except Exception:
                return None

        def geti(fname):
            try:
                return self._read_int(self._p(bdir, fname))
            except (PermissionError, OSError):
                warnings.append(f"batteries: {name}/{fname} unreadable (permission)")
                return None
            except Exception:
                return None

        status = get("status")
        capacity = geti("capacity")
        if capacity is None:
            # fallback from energy or charge ratios
            e_now = getf("energy_now")
            e_full = getf("energy_full")
            if e_now is not None and e_full not in (None, 0):
                capacity = _clean_num(e_now / e_full * 100.0)
            else:
                c_now = getf("charge_now")
                c_full = getf("charge_full")
                if c_now is not None and c_full not in (None, 0):
                    capacity = _clean_num(c_now / c_full * 100.0)

        # health from full/design (energy preferred, else charge)
        health = None
        full_e = getf("energy_full")
        design_e = getf("energy_full_design")
        if full_e is not None and design_e not in (None, 0) and design_e > 0:
            health = _clean_num(full_e / design_e * 100.0)
        else:
            full_c = getf("charge_full")
            design_c = getf("charge_full_design")
            if full_c is not None and design_c not in (None, 0) and design_c > 0:
                health = _clean_num(full_c / design_c * 100.0)

        cycles = geti("cycle_count")

        voltage_raw = getf("voltage_now")
        voltage = _clean_num(voltage_raw / 1e6) if voltage_raw is not None else None
        design_voltage_raw = getf("voltage_min_design")
        design_voltage = design_voltage_raw / 1e6 if design_voltage_raw is not None else voltage

        power = None
        power_raw = getf("power_now")
        if power_raw is not None:
            power = _clean_num(power_raw / 1e6)
        else:
            cur_raw = getf("current_now")
            if cur_raw is not None and voltage is not None:
                power = _clean_num(abs(cur_raw / 1e6) * voltage)

        energy_wh = None
        e_now = getf("energy_now")
        if e_now is not None:
            energy_wh = _clean_num(e_now / 1e6)
        else:
            c_now = getf("charge_now")
            if c_now is not None and design_voltage is not None:
                energy_wh = _clean_num((c_now / 1e6) * design_voltage)

        full_wh = None
        if full_e is not None:
            full_wh = _clean_num(full_e / 1e6)
        else:
            full_c = getf("charge_full")
            if full_c is not None and design_voltage is not None:
                full_wh = _clean_num((full_c / 1e6) * design_voltage)

        remaining = None
        try:
            st = (status or "").lower()
            if power is not None and power > 0 and energy_wh is not None:
                if st == "discharging":
                    remaining = int(energy_wh * 3600.0 / power)
                elif st == "charging" and full_wh is not None and full_wh > energy_wh:
                    remaining = int((full_wh - energy_wh) * 3600.0 / power)
        except Exception:
            remaining = None

        return {
            "name": name,
            "status": status,
            "percent": capacity,
            "health_percent": health,
            "cycles": cycles,
            "voltage_volts": voltage,
            "power_watts": power,
            "energy_wh": energy_wh,
            "full_energy_wh": full_wh,
            "time_remaining_seconds": remaining,
        }

    # -- temperatures ------------------------------------------------------
    def _sample_temperatures(self, warnings):
        out = []
        seen = set()
        hwmon_base = self._p(self.sys_root, "class/hwmon")
        try:
            hwmons = self._listdir(hwmon_base)
        except (PermissionError, OSError) as e:
            warnings.append(f"temperatures: hwmon scan unreadable: {e}")
            hwmons = []
        for hw in hwmons:
            hdir = self._p(hwmon_base, hw)
            try:
                chip = self._read_text(self._p(hdir, "name")) or hw
            except (PermissionError, OSError):
                warnings.append(f"temperatures: {hw} name unreadable (permission)")
                continue
            try:
                files = self._listdir(hdir)
            except (PermissionError, OSError):
                warnings.append(f"temperatures: {hw} scan unreadable (permission)")
                continue
            for f in files:
                m = _TEMP_INPUT_RE.match(f)
                if not m:
                    continue
                sensor = m.group(1)
                ipath = self._p(hdir, f)
                try:
                    raw = self._read_float(ipath)
                except (PermissionError, OSError):
                    warnings.append(f"temperatures: {chip}/{sensor} unreadable (permission)")
                    continue
                if raw is None:
                    continue
                celsius = _clean_num(raw / 1000.0)
                label = None
                crit = None
                try:
                    label = self._read_text(self._p(hdir, f"{sensor}_label"))
                except (PermissionError, OSError):
                    pass
                if not label:
                    label = sensor
                try:
                    c_raw = self._read_float(self._p(hdir, f"{sensor}_crit"))
                except (PermissionError, OSError):
                    c_raw = None
                if c_raw is not None:
                    crit = _clean_num(c_raw / 1000.0)
                entry_name = f"{chip}/{hw}-{sensor}"
                key = (entry_name, label, celsius, crit)
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "name": entry_name,
                    "label": label,
                    "celsius": celsius,
                    "critical_celsius": crit,
                })
        # thermal zones
        tz_base = self._p(self.sys_root, "class/thermal")
        try:
            zones = self._listdir(tz_base)
        except (PermissionError, OSError) as e:
            warnings.append(f"temperatures: thermal scan unreadable: {e}")
            zones = []
        for z in zones:
            if not z.startswith("thermal_zone"):
                continue
            zdir = self._p(tz_base, z)
            try:
                ztype = self._read_text(self._p(zdir, "type")) or z
            except (PermissionError, OSError):
                warnings.append(f"temperatures: {z} type unreadable (permission)")
                continue
            try:
                raw = self._read_float(self._p(zdir, "temp"))
            except (PermissionError, OSError):
                warnings.append(f"temperatures: {z} unreadable (permission)")
                continue
            if raw is None:
                continue
            celsius = _clean_num(raw / 1000.0)
            crit = None
            try:
                for filename in self._listdir(zdir):
                    if re.match(r"^trip_point_\d+_type$", filename):
                        if self._read_text(self._p(zdir, filename)) == "critical":
                            c_raw = self._read_float(self._p(zdir, filename.replace("_type", "_temp")))
                            if c_raw is not None:
                                crit = c_raw / 1000.0
                                break
            except (PermissionError, OSError):
                pass
            entry_name = f"{z}:{ztype}"
            key = (entry_name, ztype, celsius, crit)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "name": entry_name,
                "label": ztype,
                "celsius": celsius,
                "critical_celsius": crit,
            })
        return out

    # -- fans --------------------------------------------------------------
    def _sample_fans(self, warnings):
        out = []
        hwmon_base = self._p(self.sys_root, "class/hwmon")
        try:
            hwmons = self._listdir(hwmon_base)
        except (PermissionError, OSError) as e:
            warnings.append(f"fans: hwmon scan unreadable: {e}")
            return []
        for hw in hwmons:
            hdir = self._p(hwmon_base, hw)
            try:
                chip = self._read_text(self._p(hdir, "name")) or hw
            except (PermissionError, OSError):
                continue
            try:
                files = self._listdir(hdir)
            except (PermissionError, OSError):
                continue
            for f in files:
                m = _FAN_INPUT_RE.match(f)
                if not m:
                    continue
                sensor = m.group(1)
                try:
                    raw = self._read_float(self._p(hdir, f))
                except (PermissionError, OSError):
                    warnings.append(f"fans: {chip}/{sensor} unreadable (permission)")
                    continue
                if raw is None:
                    continue
                label = None
                try:
                    label = self._read_text(self._p(hdir, f"{sensor}_label"))
                except (PermissionError, OSError):
                    pass
                if not label:
                    label = sensor
                out.append({
                    "name": f"{chip}/{hw}-{sensor}",
                    "label": label,
                    "rpm": _clean_num(raw),
                })
        return out

    # -- gpus --------------------------------------------------------------
    def _sample_gpus(self, warnings):
        out = []
        drm_base = self._p(self.sys_root, "class/drm")
        try:
            entries = self._listdir(drm_base)
        except (PermissionError, OSError) as e:
            warnings.append(f"gpus: drm scan unreadable: {e}")
            return []
        cards = sorted([e for e in entries if _CARD_RE.match(e)],
                       key=lambda c: int(c[4:]))
        for card in cards:
            devdir = self._p(drm_base, card, "device")
            name = card
            driver = None
            vendor = None
            try:
                link = os.readlink(self._p(devdir, "driver"))
                driver = os.path.basename(link.rstrip("/")) or None
            except (FileNotFoundError, NotADirectoryError):
                driver = None
            except (PermissionError, OSError) as e:
                warnings.append(f"gpus: {card} driver unreadable: {e}")
                driver = None
            except Exception:
                driver = None
            try:
                vraw = self._read_text(self._p(devdir, "vendor"))
            except (PermissionError, OSError) as e:
                warnings.append(f"gpus: {card} vendor unreadable: {e}")
                vraw = None
            if vraw:
                key = vraw.strip().lower()
                vendor = _PCI_VENDORS.get(key, "Other")
            elif driver:
                vendor = _DRIVER_VENDORS.get(driver, "Other" if driver else None)
            else:
                vendor = None

            busy = None
            try:
                braw = self._read_float(self._p(devdir, "gpu_busy_percent"))
            except (PermissionError, OSError) as e:
                warnings.append(f"gpus: {card} busy_percent unreadable: {e}")
                braw = None
            if braw is not None:
                busy = _clean_num(braw)

            temp = self._gpu_temp(devdir, warnings, card)

            mem_used = None
            mem_total = None
            try:
                u = self._read_float(self._p(devdir, "mem_info_vram_used"))
                if u is not None:
                    mem_used = _clean_num(u)
            except (PermissionError, OSError) as e:
                warnings.append(f"gpus: {card} vram unreadable: {e}")
            try:
                t = self._read_float(self._p(devdir, "mem_info_vram_total"))
                if t is not None:
                    mem_total = _clean_num(t)
            except (PermissionError, OSError) as e:
                warnings.append(f"gpus: {card} vram unreadable: {e}")

            out.append({
                "name": name,
                "vendor": vendor,
                "driver": driver,
                "busy_percent": busy,
                "temperature_celsius": temp,
                "memory_used_bytes": mem_used,
                "memory_total_bytes": mem_total,
            })
        return out

    def _gpu_temp(self, devdir, warnings, card):
        # 1. nested hwmon under the drm device
        for sub in ("hwmon",):
            hbase = self._p(devdir, sub)
            try:
                subs = self._listdir(hbase)
            except (PermissionError, OSError):
                subs = []
            for s in subs:
                cand = self._p(hbase, s, "temp1_input")
                try:
                    raw = self._read_float(cand)
                except (PermissionError, OSError):
                    continue
                if raw is not None:
                    return _clean_num(raw / 1000.0)
        # 2. hwmon whose device symlink resolves to this drm device
        try:
            want = os.path.realpath(devdir)
        except Exception:
            want = devdir
        hwmon_base = self._p(self.sys_root, "class/hwmon")
        try:
            hwmons = self._listdir(hwmon_base)
        except (PermissionError, OSError):
            return None
        for hw in hwmons:
            hdir = self._p(hwmon_base, hw)
            dev_link = self._p(hdir, "device")
            try:
                if os.path.realpath(dev_link) != want:
                    continue
            except Exception:
                continue
            try:
                raw = self._read_float(self._p(hdir, "temp1_input"))
            except (PermissionError, OSError):
                continue
            if raw is not None:
                return _clean_num(raw / 1000.0)
        return None

    # -- power -------------------------------------------------------------
    def _sample_power(self, now, warnings):
        out = []
        # hwmon measured power (microwatt -> watt); never constraint limits.
        hwmon_base = self._p(self.sys_root, "class/hwmon")
        try:
            hwmons = self._listdir(hwmon_base)
        except (PermissionError, OSError) as e:
            warnings.append(f"power: hwmon scan unreadable: {e}")
            hwmons = []
        for hw in hwmons:
            hdir = self._p(hwmon_base, hw)
            try:
                chip = self._read_text(self._p(hdir, "name")) or hw
            except (PermissionError, OSError):
                continue
            if "bat" in chip.lower():
                continue
            try:
                files = self._listdir(hdir)
            except (PermissionError, OSError):
                continue
            inputs = {}
            avgs = {}
            for f in files:
                mi = _POWER_INPUT_RE.match(f)
                if mi:
                    inputs[mi.group(1)] = f
                    continue
                ma = _POWER_AVG_RE.match(f)
                if ma:
                    avgs[ma.group(1)] = f
            for sensor in sorted(set(list(inputs.keys()) + list(avgs.keys()))):
                fname = inputs.get(sensor, avgs.get(sensor))
                try:
                    raw = self._read_float(self._p(hdir, fname))
                except (PermissionError, OSError):
                    warnings.append(f"power: {chip}/{sensor} unreadable (permission)")
                    continue
                if raw is None:
                    continue
                out.append({
                    "name": f"{chip}/{hw}-{sensor}",
                    "watts": _clean_num(raw / 1e6),
                })
        # RAPL measured energy deltas (microjoule -> watt via dt)
        pcap = self._p(self.sys_root, "class/powercap")
        try:
            domains = self._listdir(pcap)
        except (PermissionError, OSError) as e:
            warnings.append(f"power: powercap scan unreadable: {e}")
            domains = []
        new_prev = {}
        for dom in sorted(domains):
            if "rapl" not in dom.lower():
                continue
            ddir = self._p(pcap, dom)
            epath = self._p(ddir, "energy_uj")
            try:
                cur = self._read_float(epath)
            except (PermissionError, OSError):
                warnings.append(f"power: {dom} energy unreadable (permission)")
                continue
            if cur is None:
                # no energy_uj (e.g. constraint-only entry): skip silently,
                # never fall back to constraint limits.
                continue
            cur_uj = cur
            try:
                dname = self._read_text(self._p(ddir, "name")) or dom
            except (PermissionError, OSError):
                dname = dom
            max_range = None
            try:
                max_range = self._read_float(self._p(ddir, "max_energy_range_uj"))
            except (PermissionError, OSError):
                max_range = None
            prev = self._prev_rapl.get(epath)
            if prev is None:
                watts = 0.0
            else:
                puj, pt = prev
                dt = now - pt
                if dt <= 0:
                    watts = 0.0
                elif cur_uj >= puj:
                    watts = (cur_uj - puj) / 1e6 / dt
                else:
                    # counter wrapped
                    if max_range and max_range > 0:
                        watts = ((max_range - puj) + cur_uj) / 1e6 / dt
                    else:
                        watts = 0.0
                watts = _clean_num(watts)
                if watts is None:
                    watts = 0.0
            new_prev[epath] = (cur_uj, now)
            out.append({"name": dname, "watts": watts})
        self._prev_rapl = new_prev
        return out
