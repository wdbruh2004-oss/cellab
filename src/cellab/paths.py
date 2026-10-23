"""Resource path resolution that works from source, wheels and PyInstaller bundles."""

from __future__ import annotations

import sys
from pathlib import Path


def package_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / "cellab"
    return Path(__file__).resolve().parent


def data_path(*parts: str) -> Path:
    return package_root().joinpath("data", *parts)
