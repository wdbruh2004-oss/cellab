# Tasks

Legend: `[x]` done and tested · `[~]` done, not yet verified on the target platform · `[ ]` open

> The specification received in session 1 started partway through (at the Phase 5
> description). Phase 1 was defined by the spec's execution directive. **Phases 2–4 were not
> in the received text**; paste them to refine the plan.

## Phase 1 — Launchable 3D cell explorer (session 1)

- [x] Environment inspection, version selection, `uv.lock` (Python 3.12, PySide6 6.12, VTK 9.7, PyVista 0.49, SciPy 1.18)
- [x] Project structure, persistent state files
- [x] Desktop window: docks, toolbar, menus, dark theme, saved layout
- [x] 3D viewport (VTK in Qt), gradient background, depth peeling (hardware GL), FXAA
- [x] Scientifically labelled hepatocyte: 19 structure types, Table 12-2 counts and volumes
- [x] Deterministic non-overlapping packing (exact capsule distances), about 2 s build
- [x] Mouse navigation, click selection (instance-level), double-click / `F` fly-to
- [x] Section view with depth slider; cut faces rendered solid; auto-raise on focus
- [x] Occlusion-aware leader-line labels with de-overlap; live scale bar
- [x] Scientific inspector (status badges, sources, markers, per-instance measurements)
- [x] Structure browser with search, visibility, isolate / show all
- [x] Validation report and `--self-test`
- [x] 71 tests (unit, scientific invariants, GUI end-to-end, offline guard); ruff clean
- [x] Linux one-folder bundle built and self-tested (`build/CellLab-0.1.0-linux-x86_64.tar.gz`)
- [~] Windows bundle and installer: `packaging/build_windows.ps1`, `installer.iss` and CI job written but **not yet run on Windows**

## Open items (priority order)

1. [ ] **W1** Run `packaging\build_windows.ps1` on Windows 10/11 (or push and run the CI `windows` job). Check the self-test, HiDPI scaling and start-up time.
2. [ ] **S1** Verify the Table 12-2 transcription and textbook ranges against physical copies.
3. [ ] **S2** Import licensed GO and UniProt releases offline. Verify every GO ID and accession; show official names and definitions with licence notices.
4. [ ] **L1** Choose the project licence (needed for the installer's licence page).
5. [ ] **P1** Performance: optional detail levels (mesh LOD), instanced rendering for pores and ribosomes, start-up layout cache.
6. [ ] **U1** Hover tooltips; measurement tool (distance between two picks); bookmarks for camera views.
7. [ ] **U2** Second cell profile (for example a generic cultured cell or neuron) to exercise the data-driven design.

## Phase 5 — Offline scientific data (from spec)

- [ ] Licensed offline molecular structures (PDB/mmCIF subset), protein info, pathways, searchable references
- [ ] Data-pack format with version, licence and checksum; importer scripts; cache

## Phase 6 — Advanced simulation (from spec)

- [ ] Engine interface on top of `CellModel`; optional molecular dynamics, spatial models, electrophysiology using validated engines

## Phase 7 — Education and assistant (from spec)

- [ ] Structured courses, quizzes, local search, optional offline AI

## Phase 8 — Production release (from spec)

- [~] Installer · [~] Executable · [ ] Local scientific databases · [x] Assets · [x] User manual
- [x] Developer documentation · [x] Automated tests · [ ] Benchmark reports · [x] Licence notices
- [ ] Update and expansion architecture
