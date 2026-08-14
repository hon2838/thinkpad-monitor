from setuptools import setup, find_packages

setup(
    name="thinkpad-monitor",
    version="1.0.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=["psutil>=5.8.0"],
    entry_points={
        "console_scripts": [
            "thinkpad-monitor=thinkpad_monitor.monitor:main",
        ],
    },
)
