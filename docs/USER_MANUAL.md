# CellLab user manual

CellLab is an offline 3D laboratory for exploring a quantitatively modeled mammalian
hepatocyte (liver cell). Everything runs locally and no internet connection is used.

## Installing

**Windows (from the project folder):** double-click `SETUP_CellLab.bat`. It builds CellLab, adds a desktop icon and opens the app (first run needs internet, 5–15 min).
**Windows (installer):** run `CellLab-<version>-win64-setup.exe` and start CellLab from the
Start menu.
**Windows (portable):** unzip `CellLab-<version>-win64-portable.zip` anywhere and run
`CellLab\CellLab.exe`.
**Linux:** extract `CellLab-<version>-linux-x86_64.tar.gz` and run `CellLab/CellLab`.

Requirements: 64-bit OS, OpenGL 3.2 or newer, about 4 GB RAM and 700 MB of disk.
Without a GPU driver (for example in a virtual machine), CellLab detects the software
renderer and switches to a performance mode in which fine structures hide while the
camera moves.

## The window

| Area | Purpose |
|---|---|
| **Structures** (left) | Every structure grouped by system, with rendered counts. Tick boxes show or hide structures. The search box matches names, synonyms, GO IDs, gene symbols and UniProt accessions (for example `LAMP1`, `GO:0005739`, `P60709`). Press Enter to select the first hit. |
| **3D view** (centre) | The cell, labelled with leader lines and a scale bar. |
| **Scientific inspector** (right) | Description, functions, quantitative data with status badges and sources, marker proteins, representation notes and full references for the current selection. When a single organelle is selected, its measured size, volume and position are shown. |
| **Toolbar** | Reset view, Focus, Show all, Section on/off with a depth slider, Labels, Scale bar, Validation report. |

## Mouse and keyboard

| Action | Input |
|---|---|
| Rotate | Left-drag |
| Pan | Middle-drag, or Shift + left-drag |
| Zoom | Mouse wheel, or right-drag |
| Select a structure instance | Left-click |
| Select and fly to it | Double-click |
| Focus the selection | `F` (or the Focus button) |
| Reset the view | `Home` or `R` |
| Toggle section view | `S` |
| Toggle labels | `L` |
| Search | `Ctrl+F` |
| Clear the selection | `Esc` |
| Show all structures | `Ctrl+Shift+A` |
| Save a screenshot | `Ctrl+Shift+S` |
| Validation report | `Ctrl+Shift+V` |

## Section view

The section plane cuts the cell horizontally, like a microscope optical section. Drag the
depth slider to scan through the cell. Cut organelles appear as solid, darker cross-sections.
Focusing on a structure above the plane raises the plane automatically.

## Reading the scientific data

Each value carries a status badge:

- **sourced** comes from a specific table or statement.
- **textbook** is a standard textbook value.
- **approximate** is indicative.
- **model** is a parameter of this model.
- **illustrative** is visual only.

The **In this model** block shows how a compartment is realized:

- **Geometric:** the count and total volume equal the reference exactly. This applies to
  mitochondria, peroxisomes, lysosomes, endosomes and the nucleus.
- **Representational:** the arrangement is shown, but the volume is not realized. This
  applies to the ER and Golgi.

**Science → Scientific validation report** compares every compartment with the reference
table (Alberts et al. 2014, Table 12-2).

## Isolating structures

Select a structure, then press **Isolate** in the inspector to show only it and the membrane
outline. **Show all** restores everything.

## Command-line options

```
CellLab --self-test [--report result.json]   health check, exit code 0 = OK
CellLab --screenshot out.png                 render the default view and exit
CellLab --window-screenshot out.png          capture the whole window and exit
CellLab --select mitochondrion:12            start with an instance selected
CellLab --software-gl                        force the software-rendering performance mode
CellLab --size 1600x950 --no-settings        window size; ignore the saved layout
```

## Limitations

This is a quantitative but simplified model. See `SCIENCE_VALIDATION.md` for what is and
is not represented, such as cristae, membrane bilayers, real ribosome numbers and dynamics.
