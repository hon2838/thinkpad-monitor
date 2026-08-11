import curses
import time
import os
import psutil

# --- Sensor Retrieval Functions ---

# --- Dynamic Sensor Helper Functions ---

def find_hwmon_dir(name):
    if not os.path.exists("/sys/class/hwmon"):
        return None
    for d in os.listdir("/sys/class/hwmon"):
        path = os.path.join("/sys/class/hwmon", d)
        name_file = os.path.join(path, "name")
        if os.path.exists(name_file):
            try:
                with open(name_file, "r") as f:
                    if name.lower() in f.read().strip().lower():
                        return path
            except Exception:
                pass
    return None

def find_battery_dir():
    for bat in ["BAT1", "BAT0", "BAT"]:
        p = f"/sys/class/power_supply/{bat}"
        if os.path.exists(p):
            return p
    return None

def find_drm_device_dir():
    if not os.path.exists("/sys/class/drm"):
        return None
    for card in ["card1", "card0", "card2"]:
        p = f"/sys/class/drm/{card}/device"
        if os.path.exists(os.path.join(p, "gpu_busy_percent")):
            return p
    return None

# --- Sensor Retrieval Functions ---

def get_cpu_temp():
    k10 = find_hwmon_dir("k10temp") or find_hwmon_dir("thinkpad")
    if k10:
        for t in ["temp1_input", "temp2_input"]:
            p = os.path.join(k10, t)
            if os.path.exists(p):
                try:
                    with open(p, "r") as f:
                        val = float(f.read().strip())
                        return val / 1000.0 if val > 1000 else val
                except Exception:
                    pass
    paths = [
        "/sys/class/thermal/thermal_zone0/temp"
    ]
    for p in paths:
        try:
            with open(p, "r") as f:
                val = float(f.read().strip())
                return val / 1000.0 if val > 1000 else val
        except Exception:
            continue
    return 0.0

def get_power_usage():
    """
    Retrieves APU / CPU Package Power Draw in Watts.
    Checks CPU/APU hwmon sensors (amdgpu, k10temp, zenpower, coretemp) and powercap interfaces,
    excluding battery power supply directories.
    """
    if os.path.exists("/sys/class/hwmon"):
        for d in os.listdir("/sys/class/hwmon"):
            p_dir = os.path.join("/sys/class/hwmon", d)
            name_f = os.path.join(p_dir, "name")
            if os.path.exists(name_f):
                try:
                    with open(name_f, "r") as f:
                        h_name = f.read().strip().lower()
                    if any(b in h_name for b in ["bat", "acad", "ac_"]):
                        continue
                    for pf in ["power1_input", "power1_average", "power2_input", "power2_average"]:
                        p_path = os.path.join(p_dir, pf)
                        if os.path.exists(p_path):
                            with open(p_path, "r") as pf_f:
                                val = float(pf_f.read().strip())
                            return val / 1000000.0 if val > 1000 else val
                except Exception:
                    pass

    for pc_path in ["/sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw",
                    "/sys/class/powercap/amd-rapl:0/constraint_0_power_limit_uw"]:
        if os.path.exists(pc_path):
            try:
                with open(pc_path, "r") as f:
                    val = float(f.read().strip())
                if val > 0:
                    return val / 1000000.0
            except Exception:
                pass

    return 0.0

def get_fan_speed():
    tp = find_hwmon_dir("thinkpad")
    if tp:
        p = os.path.join(tp, "fan1_input")
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    return float(f.read().strip())
            except Exception:
                pass
    try:
        with open("/proc/acpi/ibm/fan", "r") as f:
            for line in f:
                if line.startswith("speed:"):
                    return float(line.split(":")[1].strip())
    except Exception:
        pass
    return 0.0

def get_fan_pwm():
    try:
        with open("/proc/acpi/ibm/fan", "r") as f:
            for line in f:
                if line.startswith("level:"):
                    return line.split(":")[1].strip()
    except Exception:
        pass
    return "auto"


def get_cpu_freqs():
    try:
        freqs = [f.current for f in psutil.cpu_freq(percpu=True)]
        if freqs:
            return freqs
    except Exception:
        pass
    freqs = []
    for i in range(12):
        path = f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_cur_freq"
        try:
            with open(path, "r") as f:
                freqs.append(float(f.read().strip()) / 1000.0)
        except Exception:
            freqs.append(0.0)
    return freqs

def get_cpu_governor():
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor", "r") as f:
            return f.read().strip()
    except Exception:
        return "Unknown"

def get_battery_info():
    info = {"status": "Unknown", "capacity": 0, "voltage": 0.0, "power": 0.0, "tech": "Unknown"}
    bat = find_battery_dir()
    if bat and os.path.exists(bat):
        try:
            if os.path.exists(os.path.join(bat, "status")):
                with open(os.path.join(bat, "status"), "r") as f:
                    info["status"] = f.read().strip()
            if os.path.exists(os.path.join(bat, "capacity")):
                with open(os.path.join(bat, "capacity"), "r") as f:
                    info["capacity"] = int(f.read().strip())
            if os.path.exists(os.path.join(bat, "voltage_now")):
                with open(os.path.join(bat, "voltage_now"), "r") as f:
                    info["voltage"] = float(f.read().strip()) / 1000000.0
            if os.path.exists(os.path.join(bat, "technology")):
                with open(os.path.join(bat, "technology"), "r") as f:
                    info["tech"] = f.read().strip()
            
            if os.path.exists(os.path.join(bat, "power_now")):
                with open(os.path.join(bat, "power_now"), "r") as f:
                    info["power"] = float(f.read().strip()) / 1000000.0
            elif os.path.exists(os.path.join(bat, "current_now")):
                with open(os.path.join(bat, "current_now"), "r") as f:
                    curr = float(f.read().strip()) / 1000000.0
                info["power"] = curr * info["voltage"]
        except Exception:
            pass
    return info

def get_battery_health():
    health_info = {"health": 0.0, "cycles": 0, "mfg": "Unknown", "model": "Unknown"}
    bat = find_battery_dir()
    if bat and os.path.exists(bat):
        try:
            full, design = 0.0, 0.0
            for full_file in ["energy_full", "charge_full"]:
                p = os.path.join(bat, full_file)
                if os.path.exists(p):
                    with open(p, "r") as f:
                        full = float(f.read().strip())
                    break
            for design_file in ["energy_full_design", "charge_full_design"]:
                p = os.path.join(bat, design_file)
                if os.path.exists(p):
                    with open(p, "r") as f:
                        design = float(f.read().strip())
                    break
            if os.path.exists(os.path.join(bat, "cycle_count")):
                with open(os.path.join(bat, "cycle_count"), "r") as f:
                    health_info["cycles"] = int(f.read().strip())
            if os.path.exists(os.path.join(bat, "manufacturer")):
                with open(os.path.join(bat, "manufacturer"), "r") as f:
                    health_info["mfg"] = f.read().strip()
            if os.path.exists(os.path.join(bat, "model_name")):
                with open(os.path.join(bat, "model_name"), "r") as f:
                    health_info["model"] = f.read().strip()
            
            health_info["health"] = (full / design) * 100.0 if design > 0 else 0.0
        except Exception:
            pass
    return health_info

def get_charge_thresholds():
    thresholds = {"start": 0, "stop": 100}
    bat = find_battery_dir()
    if bat:
        for p, key in [("charge_start_threshold", "start"), 
                       ("charge_control_start_threshold", "start"),
                       ("charge_stop_threshold", "stop"),
                       ("charge_control_end_threshold", "stop")]:
            path = os.path.join(bat, p)
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        thresholds[key] = int(f.read().strip())
                except:
                    pass
    return thresholds

def get_gpu_info():
    info = {"temp": 0.0, "sclk": 0.0, "vddgfx": 0.0, "vddnb": 0.0, "busy": 0, 
            "vram_used": 0.0, "vram_total": 0.0, "gtt_used": 0.0, "gtt_total": 0.0}
    gpu_hwmon = find_hwmon_dir("amdgpu")
    if gpu_hwmon:
        try:
            if os.path.exists(os.path.join(gpu_hwmon, "temp1_input")):
                with open(os.path.join(gpu_hwmon, "temp1_input"), "r") as f:
                    info["temp"] = float(f.read().strip()) / 1000.0
            if os.path.exists(os.path.join(gpu_hwmon, "freq1_input")):
                with open(os.path.join(gpu_hwmon, "freq1_input"), "r") as f:
                    info["sclk"] = float(f.read().strip()) / 1000000.0
            if os.path.exists(os.path.join(gpu_hwmon, "in0_input")):
                with open(os.path.join(gpu_hwmon, "in0_input"), "r") as f:
                    info["vddgfx"] = float(f.read().strip()) / 1000.0
            if os.path.exists(os.path.join(gpu_hwmon, "in1_input")):
                with open(os.path.join(gpu_hwmon, "in1_input"), "r") as f:
                    info["vddnb"] = float(f.read().strip()) / 1000.0
        except Exception:
            pass
    card_dir = find_drm_device_dir()
    if card_dir:
        try:
            if os.path.exists(os.path.join(card_dir, "gpu_busy_percent")):
                with open(os.path.join(card_dir, "gpu_busy_percent"), "r") as f:
                    info["busy"] = int(f.read().strip())
            if os.path.exists(os.path.join(card_dir, "mem_info_vram_used")):
                with open(os.path.join(card_dir, "mem_info_vram_used"), "r") as f:
                    info["vram_used"] = float(f.read().strip()) / (1024*1024)
            if os.path.exists(os.path.join(card_dir, "mem_info_vram_total")):
                with open(os.path.join(card_dir, "mem_info_vram_total"), "r") as f:
                    info["vram_total"] = float(f.read().strip()) / (1024*1024)
            if os.path.exists(os.path.join(card_dir, "mem_info_gtt_used")):
                with open(os.path.join(card_dir, "mem_info_gtt_used"), "r") as f:
                    info["gtt_used"] = float(f.read().strip()) / (1024*1024)
            if os.path.exists(os.path.join(card_dir, "mem_info_gtt_total")):
                with open(os.path.join(card_dir, "mem_info_gtt_total"), "r") as f:
                    info["gtt_total"] = float(f.read().strip()) / (1024*1024)
        except Exception:
            pass
    return info

def find_all_hwmon_dirs(name):
    res = []
    if not os.path.exists("/sys/class/hwmon"):
        return res
    for d in os.listdir("/sys/class/hwmon"):
        path = os.path.join("/sys/class/hwmon", d)
        name_file = os.path.join(path, "name")
        if os.path.exists(name_file):
            try:
                with open(name_file, "r") as f:
                    if name.lower() in f.read().strip().lower():
                        res.append(path)
            except Exception:
                pass
    return res

def get_nvme_details():
    nvme_list = []
    hwmons = find_all_hwmon_dirs("nvme")
    for hw in hwmons:
        dev_link = os.path.join(hw, "device")
        dev = "nvme"
        model = "NVMe SSD"
        if os.path.exists(dev_link):
            try:
                target = os.path.basename(os.readlink(dev_link))
                dev = target
                model_path = f"/sys/class/nvme/{target}/model"
                if os.path.exists(model_path):
                    with open(model_path, "r") as mf:
                        model = mf.read().strip()
            except Exception:
                pass

        info = {"name": dev, "model": model, "temp1": 0.0, "temp2": 0.0, "temp3": 0.0, "crit": 70.0}
        for t_idx in [1, 2, 3]:
            p = os.path.join(hw, f"temp{t_idx}_input")
            if os.path.exists(p):
                try:
                    with open(p, "r") as f:
                        info[f"temp{t_idx}"] = float(f.read().strip()) / 1000.0
                except:
                    pass
        crit_p = os.path.join(hw, "temp1_crit")
        if os.path.exists(crit_p):
            try:
                with open(crit_p, "r") as f:
                    info["crit"] = float(f.read().strip()) / 1000.0
            except:
                pass
        nvme_list.append(info)
    if not nvme_list:
        nvme_list.append({"name": "nvme0", "model": "NVMe Drive", "temp1": 0.0, "temp2": 0.0, "temp3": 0.0, "crit": 70.0})
    return nvme_list

def get_system_model():
    vendor, product, version, bios_ver, bios_date = "", "", "", "", ""
    try:
        if os.path.exists("/sys/class/dmi/id/sys_vendor"):
            with open("/sys/class/dmi/id/sys_vendor", "r") as f: vendor = f.read().strip()
        if os.path.exists("/sys/class/dmi/id/product_name"):
            with open("/sys/class/dmi/id/product_name", "r") as f: product = f.read().strip()
        if os.path.exists("/sys/class/dmi/id/product_version"):
            with open("/sys/class/dmi/id/product_version", "r") as f: version = f.read().strip()
        if os.path.exists("/sys/class/dmi/id/bios_version"):
            with open("/sys/class/dmi/id/bios_version", "r") as f: bios_ver = f.read().strip()
        if os.path.exists("/sys/class/dmi/id/bios_date"):
            with open("/sys/class/dmi/id/bios_date", "r") as f: bios_date = f.read().strip()
    except Exception:
        pass
    
    cpu_model = ""
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.startswith("model name"):
                    cpu_model = line.split(":")[1].strip()
                    break
    except Exception:
        pass

    name = version if (version and version.lower() not in ["none", "type1", "invalid", "unknown", ""]) else product
    if not name:
        name = "Lenovo Laptop"
    elif product and product.lower() not in name.lower() and len(product) <= 8:
        name = f"{name} ({product})"

    return {
        "vendor": vendor,
        "model": name,
        "bios": bios_ver,
        "bios_date": bios_date,
        "cpu_model": cpu_model
    }

def get_cpu_boost_and_epp():
    boost = "Disabled"
    epp = "Unknown"
    boost_path = "/sys/devices/system/cpu/cpufreq/boost"
    if os.path.exists(boost_path):
        try:
            with open(boost_path, "r") as f:
                boost = "Enabled" if f.read().strip() == "1" else "Disabled"
        except Exception:
            pass
    epp_path = "/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference"
    if os.path.exists(epp_path):
        try:
            with open(epp_path, "r") as f:
                epp = f.read().strip()
        except Exception:
            pass
    return boost, epp

def get_battery_time_and_wh():
    res = {"energy_now_wh": 0.0, "energy_full_wh": 0.0, "energy_design_wh": 0.0, "time_str": "N/A"}
    bat = None
    for b in ["BAT1", "BAT0"]:
        if os.path.exists(f"/sys/class/power_supply/{b}"):
            bat = f"/sys/class/power_supply/{b}"
            break
    if bat:
        try:
            status = "Unknown"
            if os.path.exists(f"{bat}/status"):
                status = open(f"{bat}/status").read().strip()
                
            e_now, e_full, e_design, p_now = 0.0, 0.0, 0.0, 0.0
            if os.path.exists(f"{bat}/energy_now"):
                e_now = float(open(f"{bat}/energy_now").read().strip()) / 1000000.0
            if os.path.exists(f"{bat}/energy_full"):
                e_full = float(open(f"{bat}/energy_full").read().strip()) / 1000000.0
            if os.path.exists(f"{bat}/energy_full_design"):
                e_design = float(open(f"{bat}/energy_full_design").read().strip()) / 1000000.0
            if os.path.exists(f"{bat}/power_now"):
                p_now = float(open(f"{bat}/power_now").read().strip()) / 1000000.0
                
            res["energy_now_wh"] = e_now
            res["energy_full_wh"] = e_full
            res["energy_design_wh"] = e_design
            
            if status == "Discharging" and p_now > 0.1:
                hrs = e_now / p_now
                h, m = int(hrs), int((hrs % 1) * 60)
                res["time_str"] = f"{h}h {m:02d}m left"
            elif status == "Charging" and p_now > 0.1 and e_full > e_now:
                hrs = (e_full - e_now) / p_now
                h, m = int(hrs), int((hrs % 1) * 60)
                res["time_str"] = f"{h}h {m:02d}m to full"
            elif status in ["Full", "Not charging"]:
                res["time_str"] = "Fully Charged"
        except Exception:
            pass
    return res

def get_wifi_details():
    import subprocess
    res = {"ssid": "Disconnected", "signal": 0, "freq": "", "rate": ""}
    try:
        out = subprocess.check_output(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL,FREQ,RATE", "dev", "wifi"], text=True, stderr=subprocess.DEVNULL)
        for line in out.strip().split("\n"):
            if line.startswith("yes:"):
                parts = line.split(":")
                if len(parts) >= 5:
                    res["ssid"] = parts[1]
                    res["signal"] = int(parts[2]) if parts[2].isdigit() else 0
                    res["freq"] = parts[3]
                    res["rate"] = parts[4]
                break
    except Exception:
        pass
    return res

def get_backlight_percent():
    try:
        import glob
        paths = glob.glob("/sys/class/backlight/*/brightness")
        if paths:
            base = os.path.dirname(paths[0])
            cur = float(open(os.path.join(base, "actual_brightness")).read().strip())
            mx = float(open(os.path.join(base, "max_brightness")).read().strip())
            return int((cur / mx) * 100.0)
    except Exception:
        pass
    return 0

def get_top_processes():
    procs = []
    try:
        for p in sorted(psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']), key=lambda x: x.info['cpu_percent'] or 0, reverse=True)[:3]:
            procs.append({
                "pid": p.info['pid'],
                "name": p.info['name'][:14],
                "cpu": p.info['cpu_percent'] or 0.0,
                "mem": p.info['memory_percent'] or 0.0
            })
    except Exception:
        pass
    return procs

def get_wifi_temp():
    wifi_hwmon = find_hwmon_dir("iwlwifi") or find_hwmon_dir("ath") or find_hwmon_dir("wlan")
    if wifi_hwmon:
        p = os.path.join(wifi_hwmon, "temp1_input")
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    return float(f.read().strip()) / 1000.0
            except Exception:
                pass
    return 0.0

def get_usbc_telemetry():
    ports = []
    for i in [1, 2]:
        p_dir = f"/sys/class/power_supply/ucsi-source-psy-USBC000:00{i}"
        p_info = {"online": 0, "status": "Offline", "v_max": 0.0, "c_max": 0.0, "v_now": 0.0, "c_now": 0.0}
        if os.path.exists(p_dir):
            try:
                with open(os.path.join(p_dir, "online"), "r") as f:
                    p_info["online"] = int(f.read().strip())
                if p_info["online"] == 1:
                    with open(os.path.join(p_dir, "status"), "r") as f:
                        p_info["status"] = f.read().strip()
                    with open(os.path.join(p_dir, "voltage_max"), "r") as f:
                        p_info["v_max"] = float(f.read().strip()) / 1000000.0
                    with open(os.path.join(p_dir, "current_max"), "r") as f:
                        p_info["c_max"] = float(f.read().strip()) / 1000000.0
                    with open(os.path.join(p_dir, "voltage_now"), "r") as f:
                        p_info["v_now"] = float(f.read().strip()) / 1000000.0
                    with open(os.path.join(p_dir, "current_now"), "r") as f:
                        p_info["c_now"] = float(f.read().strip()) / 1000000.0
            except Exception:
                pass
        ports.append(p_info)
    return ports

def get_active_interface():
    # Detect the first active network interface that has an IP and is not loopback
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    for iface, addr_list in addrs.items():
        if iface == "lo" or iface.startswith("docker"):
            continue
        is_up = stats.get(iface).isup if iface in stats else False
        if is_up:
            for addr in addr_list:
                if addr.family == 2: # AF_INET (IPv4)
                    return iface, addr.address
    return "None", "Offline"

def get_uptime():
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.read().split()[0])
        d = int(uptime_seconds // (24 * 3600))
        h = int((uptime_seconds % (24 * 3600)) // 3600)
        m = int((uptime_seconds % 3600) // 60)
        s = int(uptime_seconds % 60)
        if d > 0:
            return f"{d}d {h}h {m}m {s}s"
        else:
            return f"{h}h {m}m {s}s"
    except Exception:
        return "Unknown"

def get_platform_profile():
    try:
        with open("/sys/firmware/acpi/platform_profile", "r") as f:
            return f.read().strip()
    except Exception:
        return "Unknown"

def get_ac_status():
    for ac in ["ACAD", "AC", "ADP1", "AC0"]:
        p = f"/sys/class/power_supply/{ac}/online"
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    return "Online" if f.read().strip() == "1" else "Offline"
            except Exception:
                pass
    return "Unknown"

def get_backlight():
    try:
        import glob
        paths = glob.glob("/sys/class/backlight/*/brightness")
        if paths:
            base = os.path.dirname(paths[0])
            with open(os.path.join(base, "brightness"), "r") as f:
                b = float(f.read().strip())
            with open(os.path.join(base, "max_brightness"), "r") as f:
                m = float(f.read().strip())
            return (b / m) * 100.0 if m > 0 else 0.0
    except Exception:
        pass
    return 0.0

def get_bluetooth_status():
    try:
        with open("/proc/acpi/ibm/bluetooth", "r") as f:
            for line in f:
                if line.startswith("status:"):
                    return line.split(":")[1].strip()
    except Exception:
        pass
    return "Unknown"

def get_gpu_ppt_limit():
    gpu_hwmon = find_hwmon_dir("amdgpu")
    if gpu_hwmon:
        p = os.path.join(gpu_hwmon, "power1_cap")
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    return float(f.read().strip()) / 1000000.0
            except Exception:
                pass
    return 30.0

# --- State Class for Dynamic Rates ---
class MonitorState:
    def __init__(self):
        self.last_time = time.time()
        self.active_iface, self.ip = get_active_interface()
        
        # Initialize net bytes
        self.last_net_rx = 0
        self.last_net_tx = 0
        net_io = psutil.net_io_counters(pernic=True)
        if self.active_iface in net_io:
            self.last_net_rx = net_io[self.active_iface].bytes_recv
            self.last_net_tx = net_io[self.active_iface].bytes_sent
            
        # Initialize disk bytes
        self.last_disk_read = 0
        self.last_disk_write = 0
        disk_io = psutil.disk_io_counters()
        if disk_io:
            self.last_disk_read = disk_io.read_bytes
            self.last_disk_write = disk_io.write_bytes
            
        self.net_rx_rate = 0.0
        self.net_tx_rate = 0.0
        self.disk_read_rate = 0.0
        self.disk_write_rate = 0.0
        
        self.total_rx_mb = self.last_net_rx / (1024*1024)
        self.total_tx_mb = self.last_net_tx / (1024*1024)
        
        # Warmup CPU load metrics
        psutil.cpu_percent(percpu=True)

    def update(self):
        now = time.time()
        dt = now - self.last_time
        if dt <= 0: return
        
        self.active_iface, self.ip = get_active_interface()
        
        # Update Network rates
        net_io = psutil.net_io_counters(pernic=True)
        if self.active_iface in net_io:
            rx = net_io[self.active_iface].bytes_recv
            tx = net_io[self.active_iface].bytes_sent
            self.net_rx_rate = (rx - self.last_net_rx) / dt / (1024*1024)
            self.net_tx_rate = (tx - self.last_net_tx) / dt / (1024*1024)
            self.last_net_rx, self.last_net_tx = rx, tx
            self.total_rx_mb = rx / (1024*1024)
            self.total_tx_mb = tx / (1024*1024)
        else:
            self.net_rx_rate = 0.0
            self.net_tx_rate = 0.0
            
        # Update Disk rates
        disk_io = psutil.disk_io_counters()
        if disk_io:
            r = disk_io.read_bytes
            w = disk_io.write_bytes
            self.disk_read_rate = (r - self.last_disk_read) / dt / (1024*1024)
            self.disk_write_rate = (w - self.last_disk_write) / dt / (1024*1024)
            self.last_disk_read, self.last_disk_write = r, w
            
        self.last_time = now

# --- UI Helpers ---
def safe_addstr(stdscr, y, x, s, attr=0):
    max_y, max_x = stdscr.getmaxyx()
    if y >= max_y or x >= max_x:
        return
    if x + len(s) >= max_x:
        s = s[:max_x - x - 1]
    try:
        stdscr.addstr(y, x, s, attr)
    except Exception:
        pass

def draw_colored_bar(stdscr, y, x, val, max_val, width=12, has_colors=True, low_pair=2, med_pair=4, high_pair=3):
    if max_val <= 0:
        pct = 0.0
    else:
        pct = (val / max_val) * 100.0
        
    attr = curses.A_NORMAL
    if has_colors:
        if pct > 85:
            attr = curses.color_pair(high_pair)
        elif pct > 60:
            attr = curses.color_pair(med_pair)
        else:
            attr = curses.color_pair(low_pair)
            
    fill = int(min(val, max_val) / max_val * width) if max_val > 0 else 0
    safe_addstr(stdscr, y, x, "[")
    safe_addstr(stdscr, y, x + 1, "█" * fill, attr)
    safe_addstr(stdscr, y, x + 1 + fill, "░" * (width - fill))
    safe_addstr(stdscr, y, x + 1 + width, "]")

def draw_core_line(stdscr, y, x, core_id, freq, load, has_colors):
    safe_addstr(stdscr, y, x, f"C{core_id:02d}:", curses.color_pair(1) if has_colors else curses.A_NORMAL)
    
    freq_str = f"{freq/1000.0:.1f}G" if freq >= 1000 else f"{freq:.0f}M"
    safe_addstr(stdscr, y, x + 5, f"{freq_str:>5}")
    
    bar_width = 5
    fill = int(min(load, 100.0) / 100.0 * bar_width)
    bar_str = "█" * fill + "░" * (bar_width - fill)
    
    load_attr = curses.A_NORMAL
    if has_colors:
        if load > 85:
            load_attr = curses.color_pair(3)
        elif load > 60:
            load_attr = curses.color_pair(4)
        else:
            load_attr = curses.color_pair(2)
            
    safe_addstr(stdscr, y, x + 11, f" {bar_str} ")
    safe_addstr(stdscr, y, x + 18, f"{int(load):3d}%", load_attr)

# --- Main Dashboard Loop ---
def monitor(stdscr):
    stdscr.scrollok(False)
    stdscr.nodelay(True)
    stdscr.timeout(1000)
    try:
        curses.curs_set(0)
    except Exception:
        pass
    try:
        curses.mousemask(curses.ALL_MOUSE_EVENTS)
    except Exception:
        pass
    
    has_colors = curses.has_colors()
    if has_colors:
        try:
            curses.start_color()
            curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)   # System Info / Header / Borders
            curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Normal/OK states
            curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)    # Alert/Thermal states
            curses.init_pair(4, curses.COLOR_YELLOW, curses.COLOR_BLACK) # Power/Warning states
            curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)# GPU / Special states
        except Exception:
            has_colors = False
            
    c_cyan = curses.color_pair(1) if has_colors else curses.A_NORMAL
    c_green = curses.color_pair(2) if has_colors else curses.A_NORMAL
    c_red = curses.color_pair(3) if has_colors else curses.A_NORMAL
    c_yellow = curses.color_pair(4) if has_colors else curses.A_NORMAL
    c_magenta = curses.color_pair(5) if has_colors else curses.A_NORMAL
    c_bold = curses.A_BOLD
    
    state = MonitorState()
    
    while True:
        stdscr.clear()
        state.update()
        
        # Read stats
        uptime = get_uptime()
        governor = get_cpu_governor()
        cpu_boost, cpu_epp = get_cpu_boost_and_epp()
        load_1, load_5, load_15 = os.getloadavg()
        
        # Memory
        mem = psutil.virtual_memory()
        mem_used = mem.used / (1024**3)
        mem_total = mem.total / (1024**3)
        
        swap = psutil.swap_memory()
        swap_used = swap.used / (1024**3)
        swap_total = swap.total / (1024**3)
        
        # Disk Usage
        disk = psutil.disk_usage('/')
        disk_used = disk.used / (1024**3)
        disk_total = disk.total / (1024**3)
        
        # Network details
        active_iface, ip = state.active_iface, state.ip
        
        # Battery details
        bat = get_battery_info()
        bat_h = get_battery_health()
        thresholds = get_charge_thresholds()
        
        # APU Power & GPU
        pkg_power = get_power_usage()
        gpu = get_gpu_info()
        
        # CPU
        freqs = get_cpu_freqs()
        loads = psutil.cpu_percent(percpu=True)
        
        # Thermals & Cooling
        temp = get_cpu_temp()
        fan = get_fan_speed()
        fan_lvl = get_fan_pwm()
        nvme_list = get_nvme_details()
        wifi_temp = get_wifi_temp()
        
        # USBC charger
        usbc = get_usbc_telemetry()
        
        # New Sensors
        profile = get_platform_profile()
        ac_status = get_ac_status()
        backlight = get_backlight()
        bluetooth = get_bluetooth_status()
        ppt_limit = get_gpu_ppt_limit()
        top_procs = get_top_processes()
        
        max_y, max_x = stdscr.getmaxyx()
        
        is_single_col = max_x < 104
        
        # System & Laptop Model Info
        sys_model = get_system_model()

        # Header Box
        header_w = max_x - 4 if max_x > 4 else 98
        safe_addstr(stdscr, 0, 2, "┌" + "─" * (header_w - 2) + "┐", c_cyan)
        safe_addstr(stdscr, 1, 2, "│", c_cyan)
        
        title_str = f"{sys_model['model'].upper()}  |  Uptime: {uptime}  |  Profile: {profile}  |  AC: {ac_status}"
        if len(title_str) > header_w - 4:
            title_str = title_str[:max(0, header_w - 4)]
        safe_addstr(stdscr, 1, 4, title_str, c_cyan | c_bold)
        safe_addstr(stdscr, 1, header_w + 1, "│", c_cyan)
        safe_addstr(stdscr, 2, 2, "└" + "─" * (header_w - 2) + "┘", c_cyan)
        
        # ==================== LEFT COLUMN (col 2) ====================
        col_l = 2
        
        # System Load & Memory
        brightness_pct = get_backlight_percent()
        safe_addstr(stdscr, 4, col_l, "┌─ System Load & Memory ────────────────────────┐", c_cyan | c_bold)
        safe_addstr(stdscr, 5, col_l, f"│ Load Avg: ", c_cyan)
        safe_addstr(stdscr, 5, col_l + 12, f"{load_1:.2f}, {load_5:.2f}, {load_15:.2f} | Gov: {governor}")
        
        safe_addstr(stdscr, 6, col_l, f"│ CPU Mode: ", c_cyan)
        safe_addstr(stdscr, 6, col_l + 12, f"Boost: {cpu_boost} | EPP: {cpu_epp} | Screen: {brightness_pct}%", c_green if cpu_boost=="Enabled" else c_yellow)

        safe_addstr(stdscr, 7, col_l, f"│ RAM Use:  ", c_cyan)
        draw_colored_bar(stdscr, 7, col_l + 12, mem.used, mem.total, width=12, has_colors=has_colors)
        safe_addstr(stdscr, 7, col_l + 27, f"{mem_used:.1f}/{mem_total:.1f} GB ({mem.percent:.0f}%)")
        
        safe_addstr(stdscr, 8, col_l, f"│ Swap Use: ", c_cyan)
        draw_colored_bar(stdscr, 8, col_l + 12, swap.used, swap.total, width=12, has_colors=has_colors)
        safe_addstr(stdscr, 8, col_l + 27, f"{swap_used:.1f}/{swap_total:.1f} GB ({swap.percent:.0f}%)")

        # Storage & Dual NVMe SSD
        safe_addstr(stdscr, 10, col_l, "┌─ Storage & Dual NVMe SSD ─────────────────────┐", c_cyan | c_bold)
        safe_addstr(stdscr, 11, col_l, f"│ Disk Root:", c_cyan)
        draw_colored_bar(stdscr, 11, col_l + 12, disk.used, disk.total, width=12, has_colors=has_colors)
        safe_addstr(stdscr, 11, col_l + 27, f"{disk_used:.1f}/{disk_total:.1f} GB ({disk.percent:.0f}%)")
        
        safe_addstr(stdscr, 12, col_l, f"│ I/O Speed:", c_cyan)
        safe_addstr(stdscr, 12, col_l + 12, f"R: {state.disk_read_rate:5.2f} MB/s", c_green)
        safe_addstr(stdscr, 12, col_l + 28, f"W: {state.disk_write_rate:5.2f} MB/s", c_yellow)
        
        line_idx = 13
        for idx, nvme in enumerate(nvme_list):
            model_short = nvme.get('model', 'SSD')[:15]
            safe_addstr(stdscr, line_idx, col_l, f"│ {nvme['name'].upper()}:    ", c_cyan)
            safe_addstr(stdscr, line_idx, col_l + 12, f"{model_short:<15} | Temp: {nvme['temp1']:.0f}°C", c_green if nvme['temp1'] < 60 else c_red)
            line_idx += 1

        # Network
        wifi_info = get_wifi_details()
        safe_addstr(stdscr, 16, col_l, f"┌─ Network: {active_iface:<7} ({ip}) ──────────┐", c_cyan | c_bold)
        safe_addstr(stdscr, 17, col_l, f"│ Speed:    ", c_cyan)
        safe_addstr(stdscr, 17, col_l + 12, f"Down: {state.net_rx_rate:5.2f} MB/s | Up: {state.net_tx_rate:5.2f} MB/s", c_green)
        safe_addstr(stdscr, 18, col_l, f"│ Wi-Fi 6:  ", c_cyan)
        wifi_str = f"{wifi_info['ssid']} ({wifi_info['signal']}%) | {wifi_info['rate']}" if wifi_info['ssid'] != "Disconnected" else "Disconnected"
        safe_addstr(stdscr, 18, col_l + 12, f"{wifi_str}", c_magenta if wifi_info['ssid'] != "Disconnected" else c_yellow)
        safe_addstr(stdscr, 19, col_l, f"│ Traffic:  ", c_cyan)
        safe_addstr(stdscr, 19, col_l + 12, f"Down: {state.total_rx_mb/1024:.1f} GB | Up: {state.total_tx_mb/1024:.1f} GB")

        # Top Active Processes
        safe_addstr(stdscr, 21, col_l, "┌─ Top Active Processes ────────────────────────┐", c_cyan | c_bold)
        for idx, proc in enumerate(top_procs):
            safe_addstr(stdscr, 22 + idx, col_l, f"│ P{idx+1}: {proc['name']:<14}", c_cyan)
            safe_addstr(stdscr, 22 + idx, col_l + 20, f"CPU: {proc['cpu']:5.1f}% | RAM: {proc['mem']:4.1f}%")

        # Battery Status & Health
        bat_wh = get_battery_time_and_wh()
        safe_addstr(stdscr, 26, col_l, "┌─ Battery & Power Delivery ────────────────────┐", c_cyan | c_bold)
        safe_addstr(stdscr, 27, col_l, f"│ Status:   ", c_cyan)
        safe_addstr(stdscr, 27, col_l + 12, f"{bat['status']} (AC: {ac_status})")
        
        safe_addstr(stdscr, 28, col_l, f"│ Capacity: ", c_cyan)
        draw_colored_bar(stdscr, 28, col_l + 12, bat['capacity'], 100, width=12, has_colors=has_colors)
        safe_addstr(stdscr, 28, col_l + 27, f"{bat['capacity']}%", c_green if bat['capacity'] > 20 else c_red)
        
        safe_addstr(stdscr, 29, col_l, f"│ Health:   ", c_cyan)
        safe_addstr(stdscr, 29, col_l + 12, f"{bat_h['health']:.1f}% ", c_green if bat_h['health'] > 85 else c_yellow)
        safe_addstr(stdscr, 29, col_l + 21, f"(Cycles: {bat_h['cycles']})")
        
        safe_addstr(stdscr, 30, col_l, f"│ Limits:   ", c_cyan)
        safe_addstr(stdscr, 30, col_l + 12, f"Thresholds: Start {thresholds['start']}% / Stop {thresholds['stop']}%")
        
        safe_addstr(stdscr, 31, col_l, f"│ Power:    ", c_cyan)
        status_upper = bat['status'].upper()
        if "CHARGING" in status_upper and "DIS" not in status_upper:
            pwr_str = f"Charge: +{bat['power']:.2f} W"
            pwr_color = c_green
        elif "DISCHARGING" in status_upper:
            pwr_str = f"Draw: -{bat['power']:.2f} W" if bat['power'] > 0 else f"Draw: {bat['power']:.2f} W"
            pwr_color = c_yellow
        elif "FULL" in status_upper or "NOT CHARGING" in status_upper:
            pwr_str = f"Idle: {bat['power']:.2f} W"
            pwr_color = c_cyan
        else:
            pwr_str = f"Rate: {bat['power']:.2f} W"
            pwr_color = c_yellow

        safe_addstr(stdscr, 31, col_l + 12, f"{bat['voltage']:.2f} V | {pwr_str}", pwr_color)

        safe_addstr(stdscr, 32, col_l, f"│ Time/Cap: ", c_cyan)
        safe_addstr(stdscr, 32, col_l + 12, f"{bat_wh['time_str']} | {bat_wh['energy_now_wh']:.1f}/{bat_wh['energy_full_wh']:.1f} Wh", c_green)

        # ==================== RIGHT COLUMN ====================
        col_r = 2 if is_single_col else max(52, max_x // 2)
        ro = 28 if is_single_col else 0
        
        # APU Power & GPU
        safe_addstr(stdscr, 4 + ro, col_r, "┌─ APU Power & GPU Status ──────────────────────┐", c_cyan | c_bold)
        safe_addstr(stdscr, 5 + ro, col_r, f"│ APU Draw: ", c_cyan)
        draw_colored_bar(stdscr, 5 + ro, col_r + 12, pkg_power, ppt_limit, width=12, has_colors=has_colors)
        safe_addstr(stdscr, 5 + ro, col_r + 27, f"{pkg_power:.1f} W / {ppt_limit:.0f}W", c_yellow)
        
        safe_addstr(stdscr, 6 + ro, col_r, f"│ GPU Busy: ", c_cyan)
        draw_colored_bar(stdscr, 6 + ro, col_r + 12, gpu['busy'], 100, width=12, has_colors=has_colors)
        safe_addstr(stdscr, 6 + ro, col_r + 27, f"{gpu['busy']}%", c_magenta)
        
        safe_addstr(stdscr, 7 + ro, col_r, f"│ VRAM Use: ", c_cyan)
        draw_colored_bar(stdscr, 7 + ro, col_r + 12, gpu['vram_used'], max(gpu['vram_total'], 1), width=12, has_colors=has_colors)
        safe_addstr(stdscr, 7 + ro, col_r + 27, f"{gpu['vram_used']:.0f}/{gpu['vram_total']:.0f} MB", c_magenta)
        
        safe_addstr(stdscr, 8 + ro, col_r, f"│ GTT Use:  ", c_cyan)
        draw_colored_bar(stdscr, 8 + ro, col_r + 12, gpu['gtt_used'], max(gpu['gtt_total'], 1), width=12, has_colors=has_colors)
        safe_addstr(stdscr, 8 + ro, col_r + 27, f"{gpu['gtt_used']:.0f}/{gpu['gtt_total']:.0f} MB")
        
        safe_addstr(stdscr, 9 + ro, col_r, f"│ GPU Core: ", c_cyan)
        safe_addstr(stdscr, 9 + ro, col_r + 12, f"{gpu['sclk']:.0f} MHz | Temp: {gpu['temp']:.1f} °C", c_magenta)
        
        safe_addstr(stdscr, 10 + ro, col_r, f"│ GPU Volt: ", c_cyan)
        safe_addstr(stdscr, 10 + ro, col_r + 12, f"GFX: {gpu['vddgfx']:.3f}V | NB: {gpu['vddnb']:.3f}V")
        
        # CPU Frequencies & Loads
        safe_addstr(stdscr, 12 + ro, col_r, "┌─ CPU Core Telemetry (Freq & Load) ────────────┐", c_cyan | c_bold)
        for i in range(6):
            load_l = loads[i] if i < len(loads) else 0.0
            freq_l = freqs[i] if i < len(freqs) else 0.0
            draw_core_line(stdscr, 13 + i + ro, col_r + 2, i, freq_l, load_l, has_colors)
            
            safe_addstr(stdscr, 13 + i + ro, col_r + 24, "│", c_cyan)
            
            load_r_val = loads[i+6] if (i+6) < len(loads) else 0.0
            freq_r_val = freqs[i+6] if (i+6) < len(freqs) else 0.0
            draw_core_line(stdscr, 13 + i + ro, col_r + 26, i+6, freq_r_val, load_r_val, has_colors)

        # Thermals & Cooling
        safe_addstr(stdscr, 20 + ro, col_r, "┌─ Thermals & Fan Speed ────────────────────────┐", c_cyan | c_bold)
        safe_addstr(stdscr, 21 + ro, col_r, f"│ CPU Temp: ", c_cyan)
        draw_colored_bar(stdscr, 21 + ro, col_r + 12, temp, 95.0, width=12, has_colors=has_colors)
        safe_addstr(stdscr, 21 + ro, col_r + 27, f"{temp:.1f} °C", c_red if temp > 75 else c_green)
        
        safe_addstr(stdscr, 22 + ro, col_r, f"│ Fan Spd:  ", c_cyan)
        draw_colored_bar(stdscr, 22 + ro, col_r + 12, fan, 3859.0, width=12, has_colors=has_colors)
        safe_addstr(stdscr, 22 + ro, col_r + 27, f"{fan:.0f} RPM (Lvl: {fan_lvl})", c_magenta)
        
        safe_addstr(stdscr, 23 + ro, col_r, f"│ Aux Temp: ", c_cyan)
        safe_addstr(stdscr, 23 + ro, col_r + 12, f"ThinkPad Sensor: {temp:.1f}°C | Wi-Fi: {wifi_temp:.1f}°C", c_green)

        # USB-C Charger
        safe_addstr(stdscr, 25 + ro, col_r, "┌─ USB-C Charger Ports ─────────────────────────┐", c_cyan | c_bold)
        for idx, p in enumerate(usbc):
            port_num = idx + 1
            if p["online"] == 1:
                p_watts = p["v_max"] * p["c_max"]
                live_w = p["v_now"] * p["c_now"]
                safe_addstr(stdscr, 26 + idx + ro, col_r, f"│ Port {port_num}: ", c_cyan)
                safe_addstr(stdscr, 26 + idx + ro, col_r + 10, f"PD Contract: {live_w:.1f}W ({p['v_now']:.1f}V @ {p['c_now']:.1f}A)", c_green)
            else:
                safe_addstr(stdscr, 26 + idx + ro, col_r, f"│ Port {port_num}: ", c_cyan)
                safe_addstr(stdscr, 26 + idx + ro, col_r + 10, f"Offline", curses.A_DIM)
                
        quit_y = max_y - 1 if max_y > 33 else (33 + ro)
        safe_addstr(stdscr, quit_y, 2, "Press 'q' to quit monitor dashboard.", curses.A_DIM)
        stdscr.refresh()
        
        try:
            ch = stdscr.getch()
            if ch in (ord('q'), ord('Q')):
                break
            elif ch == curses.KEY_MOUSE:
                try:
                    curses.getmouse()
                except Exception:
                    pass
        except Exception:
            pass

def main():
    curses.wrapper(monitor)

if __name__ == "__main__":
    main()
