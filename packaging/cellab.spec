# PyInstaller spec for CellLab (one-folder build). Run from the repository root:
#   uv run pyinstaller packaging/cellab.spec --noconfirm
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
is_win = sys.platform.startswith("win")

# Keep only the VTK modules the application loads (recorded by packaging/record_vtk_modules.py)
# plus a small safety margin; PyVista references ~150 modules lazily that the app never uses.
import vtkmodules
from PyInstaller.utils.hooks import collect_submodules

recorded = set((ROOT / "packaging" / "vtk_runtime_modules.txt").read_text().split())
margin = {"vtkmodules.vtkFiltersGeometry", "vtkmodules.vtkFiltersExtraction", "vtkmodules.vtkFiltersModeling",
          "vtkmodules.vtkFiltersHybrid", "vtkmodules.vtkFiltersTexture", "vtkmodules.vtkIOLegacy",
          "vtkmodules.vtkIOXML", "vtkmodules.vtkIOXMLParser", "vtkmodules.vtkCommonComputationalGeometry"
}
keep = recorded | margin
available = {"vtkmodules." + p.name.split(".")[0] for p in Path(vtkmodules.__file__).parent.iterdir()
             if p.name.startswith("vtk") and p.suffix in (".so", ".pyd") and "." in p.name}
vtk_excludes = sorted(available - keep)

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(ROOT / "src" / "cellab" / "data"), "cellab/data")],
    # vtkmodules imports these override/mixin modules dynamically (vtkmodules.MODULE_MAPPER)
    hiddenimports=sorted(keep) + collect_submodules("vtkmodules.util")
    + collect_submodules("vtkmodules.numpy_interface"),
    excludes=["tkinter", "IPython", "pytest", "pytestqt", "trame", "jupyter", "notebook",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
              "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtPdf", "vtkmodules.all", "vtk",
              *vtk_excludes],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="CellLab",
    console=False,
    icon=str(ROOT / "packaging" / "cellab.ico") if is_win else None,
    strip=not is_win,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="CellLab", strip=not is_win, upx=False)
