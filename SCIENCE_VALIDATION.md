# Scientific validation and limitations

This file records what CellLab claims, where each claim comes from, how it is checked,
and what is deliberately simplified. Update it whenever scientific content changes.

## 1. Status vocabulary (shown as badges in the inspector)

| Status | Meaning |
|---|---|
| **sourced** | Transcribed from a specific table or statement in the cited reference. |
| **textbook** | Standard textbook value or range, cited to the chapter that states it. |
| **approximate** | Order-of-magnitude or approximate value; indicative only. |
| **model** | Parameter chosen inside the cited biological range, or derived from sourced values. |
| **illustrative** | Visual representation only; no quantitative claim. |

Enforced by `KnowledgeBase.validate()` and its tests:
- Every non-illustrative quantity must cite at least one reference.
- Every reference ID must resolve.
- GO IDs must match `GO:\d{7}`.
- UniProt accessions must match the official accession pattern.
- Ranges must be ordered `[min, max]`.

## 2. Reference profile: hepatocyte compartments

The default cell is a **mammalian hepatocyte**. Its composition reproduces
Alberts et al., *Molecular Biology of the Cell*, 6th ed. (2014), **Table 12-2**:

| Compartment | % of cell volume | Approx. number per cell | Realization in CellLab |
|---|---|---|---|
| Cytosol | 54 | 1 | implicit (space between structures) |
| Mitochondria | 22 | 1700 | geometric, exact count and total volume |
| Rough ER cisternae | 9 | 1 | representational sheets (volume not realized) |
| Smooth ER + Golgi cisternae | 6 | — | representational (volume not realized) |
| Nucleus | 6 | 1 | geometric, exact volume |
| Peroxisomes | 1 | 400 | geometric, exact count and total volume |
| Lysosomes | 1 | 300 | geometric, exact count and total volume |
| Endosomes | 1 | 200 | geometric, exact count and total volume |

> **Transcription caveat.** These values were transcribed from curated knowledge of
> the textbook. The book itself was not available in this environment.
> `tests/test_profile.py::TABLE_12_2` pins the transcription. Before any
> publication-grade use, a person must check it against a physical copy (TASKS.md, item S1).

Cell size is a model parameter: an ellipsoid of 24 × 22 × 18 µm. Its volume is
4,976 µm³ and its equivalent-sphere diameter is 21.2 µm, inside the textbook
hepatocyte diameter range of 20–30 µm (test-enforced). Hepatocytes in tissue are polyhedral.

## 3. Automated quantitative checks (pytest)

| Check | Test | Result (this build) |
|---|---|---|
| Profile equals Table 12-2 transcription | `test_profile_reproduces_reference_table` | pass |
| Model count = reference count (geometric compartments) | `test_counts_match_reference` | pass |
| Model volume fraction = reference (rel. 1e-9) | `test_volume_fractions_match_reference` | pass |
| Rendered mesh volume within 1% of model volume | `test_rendered_volumes_match_model` | pass (< 0.25% deviation) |
| No two discrete organelles overlap (exact capsule–capsule distance ≥ 40 nm gap) | `test_no_overlaps_between_discrete_organelles` | pass |
| Organelles inside the cell and outside the nucleus | `test_organelles_respect_boundaries` | pass |
| Mitochondrial diameters inside textbook 0.5–1 µm | `test_mitochondrial_diameters_in_textbook_range` | pass (0.52–0.96 µm) |
| Nuclear pore count inside textbook 3000–4000 | `test_nuclear_pore_count_in_textbook_range` | pass (3,500) |
| Golgi cisternae per stack inside 4–6 | `test_golgi_stack_size_in_textbook_range` | pass (5) |
| Centriole diameter/length/count/orthogonality | `test_centriole_dimensions` | pass (0.22 × 0.45 µm, 2, orthogonal) |
| Nucleoli and chromatin inside the nucleus | `test_nucleoli_inside_nucleus`, `test_chromatin_inside_nucleus` | pass |
| Validation report detects a 5% volume error | `test_validation_detects_wrong_volume` | pass |

The same comparison is in the app under **Science → Scientific validation report**. The
packaged executable re-runs it in `--self-test`.

## 4. Derived (model) quantities

From V_cell = 4,976 µm³ and Table 12-2:
- Nucleus: 298.6 µm³, ellipsoid 8.9 × 8.9 × 7.2 µm (axis ratio 1:1:0.8 is a model choice).
- Mean mitochondrion: 0.644 µm³. Radii are drawn from a truncated normal (0.35 ± 0.04 µm,
  0.26–0.48 µm) and lengths from a lognormal (CV 0.35). Lengths are then scaled so the total
  volume is exact.
- Mean peroxisome / lysosome / endosome diameters: about 0.62 / 0.68 / 0.78 µm (±15% CV, exact totals).

## 5. Deliberate simplifications (known limitations)

| Area | Simplification |
|---|---|
| Cell shape | Ellipsoid. No polyhedral shape, bile canaliculi, microvilli, or sinusoidal/canalicular polarity. |
| Membranes | Single surfaces. Bilayer thickness (5 nm) and the double nuclear membrane are not resolved. |
| Mitochondria | Straight capsules. No cristae, branching, fission/fusion networks or matrix granules. |
| Rough/smooth ER, Golgi | Arrangement only. 9% and 6% volume shares are shown as reference data, not realized geometrically. |
| Ribosomes, chromatin | Screen-space point samples. Real ribosome counts are orders of magnitude higher. |
| Cytoskeleton | Counts, curvature and densities are illustrative. On-screen line widths are exaggerated. |
| Binucleation / polyploidy | Common in hepatocytes; the model uses one diploid-appearing nucleus. |
| Lipid droplets, glycogen | Not modeled (no sourced volume share in the reference profile). |
| Dynamics | None yet: static snapshot (simulation is planned for later phases). |

## 6. Marker proteins and identifiers

Human marker proteins are listed with UniProtKB accessions. GO cellular-component IDs are
attached to each structure.

The network policy of this environment blocked UniProt and the Gene Ontology, so
**accessions and GO IDs were curated, not machine-verified against the live databases**.
Their format is test-enforced. Verification against downloaded, licensed releases
(UniProt and GO are both CC BY 4.0) is TASKS.md item S2. No database records are redistributed;
only identifiers and the project's own summaries are included.

## 7. Diffusion simulation

- Engine: Brownian dynamics, Gaussian steps with per-axis variance 2·D·dt (dt = 0.1 ms). Moves ending
  inside an organelle, the nucleus or outside the plasma membrane are rejected.
- Validation: in free space the mean squared displacement equals 6·D·t (test, within 5%); particles
  never occupy forbidden space (test); organelles reduce the effective D (test).
- Parameters: GFP translational D = 27 µm²/s in cytoplasm and 87 µm²/s in water (Swaminathan et al.
  1997, status *approximate*, to verify under S1).
- Limitations: point particles; the cytoplasmic D already contains macromolecular crowding, so the
  extra organelle obstruction is an upper-bound illustration; no binding, flow, active transport or
  passage through nuclear pores.

## 8. References

Full citations are in `src/cellab/data/knowledge/references.json` and in each inspector page.
Main sources:
- Alberts B et al. *Molecular Biology of the Cell*, 6th ed. Garland Science; 2014.
- Milo R, Phillips R. *Cell Biology by the Numbers*. Garland Science; 2016.
- Mescher AL. *Junqueira's Basic Histology* (liver chapter).
- Ku NO et al. Keratins let liver live. *Hepatology* 2007;46:1639–1649.
- Gene Ontology Consortium. *Genetics* 2023;224:iyad031.
- UniProt Consortium. *Nucleic Acids Res* 2023;51:D523–D531.
