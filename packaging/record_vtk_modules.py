"""Record the VTK Python modules that the application actually loads.

Runs the real application self-test in-process and writes the loaded
``vtkmodules.*`` names to packaging/vtk_runtime_modules.txt. The PyInstaller spec
excludes every other VTK module, which cuts the bundle size substantially.
Re-run after upgrading VTK/PyVista:  xvfb-run uv run python packaging/record_vtk_modules.py
"""

import atexit
import sys
from pathlib import Path

OUT = Path(__file__).with_name("vtk_runtime_modules.txt")


def _dump() -> None:
    mods = sorted(m for m in sys.modules if m.startswith("vtkmodules.vtk") and m.count(".") == 1)
    OUT.write_text("\n".join(mods) + "\n", encoding="utf-8")
    print(f"recorded {len(mods)} VTK modules -> {OUT}")


atexit.register(_dump)
from cellab.app import run  # noqa: E402

code = run(["--self-test", "--no-settings"])
raise SystemExit(code)
