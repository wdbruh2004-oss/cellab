"""CellLab: offline-first 3D cellular laboratory."""

__version__ = "0.1.0"
APP_NAME = "CellLab"


def main() -> int:
    from cellab.app import run
    return run()
