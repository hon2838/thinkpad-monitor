from setuptools import setup

setup(
    name="thinkpad-monitor",
    version="1.0.0",
    py_modules=["thinkpad_monitor"],
    install_requires=["psutil>=5.8.0"],
    entry_points={
        "console_scripts": [
            "thinkpad-monitor=thinkpad_monitor:main",
        ],
    },
)
