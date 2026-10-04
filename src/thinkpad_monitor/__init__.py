"""Read-only Linux laptop monitoring; optional native Qt desktop."""
__version__ = "2.0.0"
__author__ = "Matthew Hon"


def main():
    from .cli import main as run
    return run()
