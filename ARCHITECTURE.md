# Architecture

## Stack (pinned in `uv.lock`)

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Mature scientific ecosystem; all wheels available for Windows x64. |
| UI | PySide6-Essentials 6.12 (Qt 6, LGPL-3.0) | Native desktop widgets and docking. Essentials-only keeps the bundle free of WebEngine/Qt3D. |
| 3D | VTK 9.7 via PyVista 0.49 + pyvistaqt 0.13 | Validated scientific rendering engine: picking, clipping planes, depth peeling, text, large meshes. |
| Numerics | NumPy 2, SciPy 1.18 (`cKDTree`) | Vectorized geometry; KD-tree neighbour search for packing. SciPy is also needed for planned simulation phases. |
| Packaging | PyInstaller 6 (one-folder) + Inno Setup 6 | Offline executable; replaceable Qt DLLs (LGPL); standard Windows installer. |
| Tests | pytest 9 + pytest-qt | Unit, scientific-invariant and end-to-end GUI tests. |

## Module map (`src/cellab`)

```
science/   knowledge.py   curated knowledge base loader, integrity rules, search
           profile.py     quantitative cell profiles (volume fractions, counts, provenance)
           validation.py  model-vs-reference comparison (PASS/FAIL/REPRESENTATIONAL/IMPLICIT)
model/     geom.py        vectorized geometry (segment distances, ellipsoids, rotations)
           packing.py     capsule packing: KD-tree + Verlet list, exact segment contacts
           cell_model.py  deterministic procedural cell builder -> Populations
render/    geometry.py    populations -> merged PyVista meshes with per-cell instance_id
           scene.py       actors, section plane, picking, highlight, LOD, label layout
           overlays.py    leader-line labels and scale bar (screen space, per-frame)
           style.py       colours/materials per structure
ui/        main_window.py window, actions, docks, self-test
           viewport.py    Qt event filter -> click/drag/wheel, camera fly-to animation
           panels.py      structure browser (tree + search), inspector widget
           inspector_html.py  pure HTML generation for the inspector (unit-tested)
           dialogs.py     validation report, about
           theme.py       dark Fusion theme
data/      knowledge/*.json  structures + references (single source of scientific truth)
           profiles/*.json   cell profiles
app.py     CLI entry: --self-test, --screenshot, --window-screenshot, --select, --software-gl
```

Dependency direction: `ui -> render -> model -> science`. Nothing in `science` or `model`
imports Qt or VTK, so those layers stay testable and reusable by future simulation engines.

## Key decisions

1. **Data-driven science.** All text and quantities live in JSON with provenance.
   Code never hard-codes a biological claim. New cell types are new profile files.
2. **Exact compartment realization.** Counts and total volumes come from the profile. Shape
   variation is drawn and then renormalized, so the totals hold exactly. Mesh templates are
   radially volume-compensated, so rendered volumes match within 1% (test-enforced).
3. **Packing by relaxation, not random sequential addition.** About 33% of the free cytoplasm
   is filled by discrete organelles, which is near the jamming limit for random sequential
   addition. Instead, random starts are relaxed by pairwise separation using exact capsule
   closest points (Ericson 2005), with KD-tree candidates and a Verlet skin. It converges in
   about 50 iterations; the model builds in about 2 s.
4. **One mesh per population.** About 1M triangles in roughly 20 draw calls. A per-cell
   `instance_id` array maps any picked triangle to the organelle instance.
5. **Picking.** `vtkCellPicker` honours the section clipping plane, so clipped geometry is
   never picked. The translucent plasma membrane is picked last. Clicks are detected with a
   Qt event filter, because PyVista's interactor style consumes VTK button-release events.
6. **Section view.** A mapper clipping plane (cheap, GPU-side). Backface properties render
   cut organelles as solid. Focus raises the plane when the target is above it.
7. **Labels.** Occlusion-aware anchors (read from the depth buffer) placed on a ring around the
   projected cell, or the viewport when zoomed in. Leader lines, viewport clamping and
   vertical de-overlap are recomputed each frame.
8. **Software-GL mode.** Auto-detected (Mesa llvmpipe, WARP, SwiftShader, GDI): disables depth
   peeling and hides fine structures while the camera moves.
9. **Determinism.** A seeded RNG in the profile gives an identical cell on every run and
   machine, so screenshots and tests are reproducible.
10. **Offline.** No network calls at runtime (test-enforced with a socket guard). External
    links in the inspector open only on an explicit click.

## Packaging notes

- `packaging/record_vtk_modules.py` records the VTK modules loaded during a real self-test.
  The spec excludes the others (PyVista references about 150 lazily), and dynamic VTK
  override modules (`vtkmodules.numpy_interface`, `vtkmodules.util`) are added as hidden imports.
- The frozen app must pass `--self-test`: validation, centre pick, highlight and screenshot.
  Both build scripts enforce this.
- Windows builds must be produced on Windows (PyInstaller does not cross-compile):
  `packaging/build_windows.ps1` locally, or the `windows` job in `.github/workflows/build.yml`.

## Extension points (for later phases)

- **New cell types:** add `data/profiles/<name>.json` and any new structures in `structures.json`.
- **New geometry kinds:** add a `Population.kind` in `cell_model.py` and a mesh builder in `geometry.py`.
- **Simulation engines (Phase 6):** consume `CellModel` (pure NumPy) and update populations;
  the scene re-meshes changed populations.
- **Offline databases (Phase 5):** importer scripts write licensed, versioned data packs under
  `data/packs/`. The knowledge base resolves IDs against the installed packs.
