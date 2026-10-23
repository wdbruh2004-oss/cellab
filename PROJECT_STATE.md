# Project state

_Last updated: 2026-10-23, end of session 1 (Phase 1)._

## Completed functionality (implemented and tested)

- Launchable desktop app `cellab` (PySide6 + VTK/PyVista) with a functional 3D explorer of a
  quantitatively modeled hepatocyte. See README.md for the feature list.
- Science layer: curated knowledge base covering 19 structures and 6 references, with
  integrity rules. The hepatocyte profile reproduces Alberts Table 12-2. The validation
  module compares model against reference.
- Model layer: deterministic procedural builder; relaxation packer with exact capsule
  contacts; 2,600 discrete organelles; build time about 2 s.
- Render layer: merged meshes (about 1.0M triangles), instance-level picking, section plane,
  highlight, software-GL interaction LOD, occlusion-aware labels, scale bar.
- UI: structure browser with search, inspector, validation and about dialogs, fly-to camera,
  CLI (`--self-test`, `--screenshot`, `--window-screenshot`, `--select`, `--software-gl`).
- Packaging: PyInstaller spec with a VTK module allowlist; Linux bundle built and
  self-tested; Windows script, Inno Setup installer and GitHub Actions CI written.
- One-click Windows setup (`SETUP_CellLab.bat` -> `packaging/install_windows.ps1`): builds and
  self-tests CellLab.exe, installs it per-user, adds desktop/Start-menu shortcuts. PowerShell
  scripts syntax-checked with pwsh 7.4 on Linux; not yet executed on Windows.
- VTK warnings go to `%LOCALAPPDATA%\CellLab\CellLab\vtk.log` (no pop-up windows on Windows).

## Environment of session 1

Linux cloud container (Ubuntu 24.04), 4 CPU cores, 15 GB RAM, no GPU (Mesa llvmpipe through
Xvfb). Network: PyPI reachable; UniProt, GO and python.org blocked by policy. **Windows was
not available.**

## Files (all new this session)

`pyproject.toml`, `uv.lock`, `src/cellab/**` (science, model, render, ui, data), `tests/*` (6 modules),
`packaging/*` (spec, launcher, build_windows.ps1, build_linux.sh, installer.iss, icon, VTK allowlist),
`scripts/*` (make_icon, make_screenshots, gen_notices), `.github/workflows/build.yml`,
`README.md`, `ARCHITECTURE.md`, `SCIENCE_VALIDATION.md`, `TASKS.md`, `PROJECT_STATE.md`,
`THIRD_PARTY_NOTICES.md`, `docs/USER_MANUAL.md`, `docs/images/*.png`.

## Tests executed

- GitHub Actions (https://github.com/wdbruh2004-oss/cellab): Linux job green (ruff, 72 tests, bundle + self-test); Windows job green (72 tests, PyInstaller exe + self-test, Inno Setup installer); release `latest-build` published with installer, portable zip and Linux tarball.

- `xvfb-run -a uv run pytest`: **72 passed** (about 70 s).
- `uv run ruff check src tests`: clean.
- Packaged Linux app `build/dist/CellLab/CellLab --self-test`: `"ok": true`. It covers
  validation, centre pick, highlight and screenshot.
- Bundle: 582 MB unpacked, 199 MB `.tar.gz`.

## Known errors and limitations

- The Windows executable and installer are built and self-tested in CI (GitHub `windows-latest`, Mesa software OpenGL) but not yet run on a real Windows desktop with a GPU.
- Software OpenGL frame time is about 0.6 s at 1400×1000. Interaction LOD helps; a real GPU is expected to be about 100× faster (not measured).
- Labels are re-laid out after interaction ends, not continuously while dragging.
- Selection highlight is a translucent shell; there is no silhouette outline yet.
- Scientific identifiers (GO IDs, UniProt accessions) are format-checked but not verified online (network policy).
- Phases 2–4 of the specification were not in the received text.

## Remaining tasks

See TASKS.md (W1, S1, S2, L1, P1, U1, U2 and Phases 5–8).

## Exact next implementation step

**W1:** install `CellLab-0.1.0-win64-setup.exe` (release `latest-build`) on a Windows 10/11 x64
desktop and check start-up, HiDPI labels, GPU rendering and mouse picking. Then start **S2** by writing
`scripts/import_go.py`, which reads a downloaded `go-basic.obo` (CC BY 4.0) into
`data/packs/go/` and verifies every `go.id` in `structures.json`.
