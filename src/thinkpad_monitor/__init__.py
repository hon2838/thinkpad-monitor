"""
ThinkPad & ThinkBook Hardware Monitor
A lightweight terminal-based telemetry dashboard for Lenovo laptops running Linux.
"""

from .monitor import main, monitor

__version__ = "1.0.0"
__author__ = "Matthew Hon"
__all__ = ["main", "monitor", "__version__"]
