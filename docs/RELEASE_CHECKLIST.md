# Release checks

1. Run configured test/release workflows on the x86-64 and ARM64 build runners.
2. Test installed app/menu launch, scaling, resize, dark/light palette,
   pause/resume and quit on GNOME/KDE Wayland and X11, plus Xfce, Cinnamon,
   MATE and LXQt. Test uninstalled desktop extra diagnostics and terminal mode.
3. Sample Intel, AMD and ARM64 laptops, multiple battery packs, battery-less
   systems, proprietary NVIDIA, missing EC sensors and hotplug/disappearing
   hardware. Confirm absent measurements stay unavailable.
4. Verify exported JSON, large CPU/sensor sets, counter resets, suspend/resume,
   non-root file permissions and no control writes.
5. Test source/wheel installation on supported distro Python versions and bundle
   graphics/glibc dependencies on the documented build baseline.
6. Retain third-party licenses and dynamically replaceable Qt libraries in each
   bundle. Check license notices/source availability for the actual Qt/PySide build.
7. Publish architecture-labelled bundles and checksums only after these checks.
