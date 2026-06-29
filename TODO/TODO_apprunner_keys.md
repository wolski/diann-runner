# TODO: Relabel & regroup the DIA-NN executable parameter keys

> **STATUS: IMPLEMENTED (2026-06-29).** Rename + pydantic reshape applied across
> diann_runner (model/adapters/param_core/Snakefile/tests), the A386 executable XML
> (mirrored into slurmworker, bodies byte-identical), slurmworker dispatch.py, and
> the SUSHI DIANNApp.rb. Full pytest: 220 passed. Also fixed in the same pass: the
> `no_peptidoforms` flag was never passed to DiannWorkflow (latent bug); the
> slurmworker mirror's `pg_level` enum was the pre-2026-06-26 unparseable form; and
> `_apply_fasta` now fails fast on an empty FASTA instead of an opaque IndexError.
> The design notes below are kept for the record.
>
> One combined table
> below maps every parameter across all three layers (B-Fabric ↔ SUSHI ↔ pydantic),
> current → proposed, with category/sub_category/description. React to it and we
> implement across the XML executables, both adapter maps, the SUSHI app, the
> pydantic model, and the tests.

## Decisions locked (from discussion)

1. **Drop the `_diann_` infix.** The whole executable is DIA-NN; it's redundant.
2. **Drop the numeric prefix (`05b_`, `06a_`, …).** B-Fabric now renders
   parameters in **document (XML) order**, so the number is no longer needed.
3. **GUI key = `<category>_<subcategory>_<name>`** — meaningful words, no numbers,
   no `diann` infix. Category prefix always (`pipeline_`, `input_`, `lib_`,
   `search_`, `quant_`, `output_`, `advanced_`); sub_category where a category has
   several (`lib_precursor_`, `search_mass_acc_`).
4. **Both GUIs adopt the same keys** → one shared vocabulary (SUSHI keys gain the
   category prefix too), and the **SUSHI coverage gaps are closed** (params missing
   from SUSHI today get the unified key — marked `(add)` below).
5. **Grouping corrections from reading the descriptions:**
   - `unrelated_runs` → **search_mass_acc** (flag `--individual-mass-acc`).
   - `is_dda` → **pipeline** (acquisition type, run-level).
   - `export_quant` → **output**, renamed `output_fragment_quant` (`--export-quant`).
   - `scan_window` → **quantification** (`--window`, feature detection in extraction).
   - `no_peptidoforms` → stays under **lib_mods**.
6. **Scope = all three layers (Depth 2).** Align B-Fabric keys, SUSHI keys, **and**
   the internal pydantic model. **Pydantic nests one level only** (category =
   sub-model; field = `<subcategory>_<name>`), so the path maps 1:1 to the GUI key:
   GUI `lib_precursor_charge_min` → split on the first `_` → `lib.precursor_charge_min`.
   The single spelling exception is the Input category — GUI prefix `input_`,
   pydantic namespace **`inputs`** (avoids shadowing the `input()` builtin).
7. **FASTA is a list.** DIA-NN merges multiple `--fasta` databases, SUSHI already
   multi-selects (`fasta_databases`), and the request layer
   (`DiannRunRequest.database_fasta`, `request.py:185`) is already `list[Path]`. So
   the pydantic FASTA is `inputs.fasta_databases: list[str]`. **Each frontend fills
   the list with whatever it has — a length-1 list is fine:** AppRunner contributes
   its single dropdown pick (+ optional `additional`) → a 1–2 element list; SUSHI
   contributes its multi-select → N. Nothing in the B-Fabric executable changes; if
   it ever gains real multi-select, the list just grows.

---

## Combined parameter map (current → proposed, all layers)

Sources: `docs/DIANN_PARAMETERS.md`, each parameter's `<description>` in the
executable XML, and the DIA-NN GitHub README / GUI. Rows are in **proposed
document order**. Current pydantic paths: `diann.*` = `DiannParams`, `fasta.*` =
`FastaParams`, bare = top-level `DIANNRunnerParams`
([request.py:69](diann_runner/src/diann_runner/request.py#L69)). `(add)` = closes a
SUSHI gap; `(o-o-b)` = SUSHI selects FASTA out-of-band (`fasta_databases`).

| category | sub_category | current B-Fabric key | current SUSHI key | current pydantic | → new key (B-Fabric & SUSHI) | new pydantic | description |
|----------|--------------|----------------------|-------------------|------------------|------------------------------|--------------|-------------|
| Pipeline | — | `01_diann_version` | `diann_version` | `diann.diann_version` | `pipeline_diann_version` | `pipeline.diann_version` | DIA-NN build to run (2.3.2 default … 2.6.0 newest); one .NET 8 image, reads `.raw` natively. |
| Pipeline | — | `02_workflow_mode` | `workflow_mode` | `workflow_mode` | `pipeline_workflow_mode` | `pipeline.workflow_mode` | `two_step` = predict library then quantify; `single_step` = both in one call. |
| Pipeline | — | `05_diann_is_dda` | `is_dda` | `diann.is_dda` | `pipeline_is_dda` | `pipeline.is_dda` | Acquisition type: true = DDA, false = DIA. |
| Pipeline | — | `97_raw_converter` | `raw_converter` | `raw_converter` | `pipeline_raw_converter` | `pipeline.raw_converter` | Thermo `.raw` handling: native / thermoraw / msconvert / msconvert-demultiplex. |
| Input | fasta | `03_fasta_database_path` | `fasta_databases` (multi) | `fasta.database_path` (str) | `input_fasta_databases` | `inputs.fasta_databases` (list) | One or more FASTA databases (DIA-NN merges multiple `--fasta`). SUSHI already multi-selects; B-Fabric single-select today. |
| Input | fasta | `03b_additional_fasta_database_path` | _(o-o-b)_ | _(folded in)_ | `input_fasta_additional` | _(appended to `inputs.fasta_databases`)_ | Freestyle extra FASTA path; appended to the database list (was: used only when main = NONE). |
| Input | fasta | `03_fasta_use_custom` | `order_fasta` ⚠ | `fasta.use_custom_fasta` | `input_fasta_use_custom` | `inputs.fasta_use_custom` | Also inject custom `order.fasta` from the working dir; empty file skipped. |
| Library generation | digestion | `08_diann_digestion_cut` | `digestion_cut` | `diann.cut` | `lib_digestion_cut` | `lib.digestion_cut` | Enzyme cleavage rule; default `K*,R*` (trypsin). `--cut` |
| Library generation | digestion | `08_diann_digestion_missed_cleavages` | `digestion_missed_cleavages` | `diann.missed_cleavages` | `lib_digestion_missed_cleavages` | `lib.digestion_missed_cleavages` | Max missed cleavages in digestion. `--missed-cleavages` |
| Library generation | peptide | `07_diann_peptide_min_length` | `peptide_min_length` | `diann.min_pep_len` | `lib_peptide_min_length` | `lib.peptide_min_length` | Min peptide length (aa). `--min-pep-len` |
| Library generation | peptide | `07_diann_peptide_max_length` | `peptide_max_length` | `diann.max_pep_len` | `lib_peptide_max_length` | `lib.peptide_max_length` | Max peptide length (aa). `--max-pep-len` |
| Library generation | precursor | `07_diann_peptide_precursor_charge_min` | `peptide_precursor_charge_min` | `diann.min_pr_charge` | `lib_precursor_charge_min` | `lib.precursor_charge_min` | Min precursor charge. `--min-pr-charge` |
| Library generation | precursor | `07_diann_peptide_precursor_charge_max` | `peptide_precursor_charge_max` | `diann.max_pr_charge` | `lib_precursor_charge_max` | `lib.precursor_charge_max` | Max precursor charge. `--max-pr-charge` |
| Library generation | precursor | `07_diann_peptide_precursor_mz_min` | `peptide_precursor_mz_min` | `diann.min_pr_mz` | `lib_precursor_mz_min` | `lib.precursor_mz_min` | Min precursor m/z; not auto-detected — match the DIA method. `--min-pr-mz` |
| Library generation | precursor | `07_diann_peptide_precursor_mz_max` | `peptide_precursor_mz_max` | `diann.max_pr_mz` | `lib_precursor_mz_max` | `lib.precursor_mz_max` | Max precursor m/z. `--max-pr-mz` |
| Library generation | fragment | `07_diann_peptide_fragment_mz_min` | `peptide_fragment_mz_min` | `diann.min_fr_mz` | `lib_fragment_mz_min` | `lib.fragment_mz_min` | Min fragment m/z. `--min-fr-mz` |
| Library generation | fragment | `07_diann_peptide_fragment_mz_max` | `peptide_fragment_mz_max` | `diann.max_fr_mz` | `lib_fragment_mz_max` | `lib.fragment_mz_max` | Max fragment m/z. `--max-fr-mz` |
| Library generation | mods | `06a_diann_mods_variable` | `mods_variable` | `diann.var_mods` | `lib_mods_variable` | `lib.mods_variable` | Variable modifications (`--var-mods N --var-mod UniMod:id,mass,sites`). |
| Library generation | mods | `06c_diann_mods_unimod4` | `mods_unimod4` | `diann.unimod4` | `lib_mods_unimod4` | `lib.mods_unimod4` | Fixed Carbamidomethyl (C). `--unimod4` |
| Library generation | mods | `06d_diann_mods_met_excision` | `mods_met_excision` | `diann.met_excision` | `lib_mods_met_excision` | `lib.mods_met_excision` | N-terminal methionine excision. `--met-excision` |
| Library generation | mods | `06b_diann_mods_no_peptidoforms` | `mods_no_peptidoforms` | `diann.no_peptidoforms` | `lib_mods_no_peptidoforms` | `lib.mods_no_peptidoforms` | Disable peptidoform (PTM site) scoring. `--no-peptidoforms` |
| Search & scoring | mass_acc | `09_diann_mass_acc_hint1_timstof` | _(none)_ | _(display only)_ | `search_mass_acc_hint_timstof` | _(none)_ | Read-only guidance — timsTOF: MS1 = 15, MS2 = 15. |
| Search & scoring | mass_acc | `09_diann_mass_acc_hint2_orbitrap` | _(none)_ | _(display only)_ | `search_mass_acc_hint_orbitrap` | _(none)_ | Read-only — Orbitrap/Astral: MS2 by resolution; Astral MS1=4, MS2=10. |
| Search & scoring | mass_acc | `09_diann_mass_acc_hint3_tof` | _(none)_ | _(display only)_ | `search_mass_acc_hint_tof` | _(none)_ | Read-only — TripleTOF 6600 / ZenoTOF: MS1 = 20, MS2 = 20. |
| Search & scoring | mass_acc | `09_diann_mass_acc_hint4_auto` | _(none)_ | _(display only)_ | `search_mass_acc_hint_auto` | _(none)_ | Read-only — use AUTO only for exploratory/unknown instruments. |
| Search & scoring | mass_acc | `09_diann_mass_acc_ms1` | `mass_acc_ms1` | `diann.mass_acc_ms1` | `search_mass_acc_ms1` | `search.mass_acc_ms1` | MS1 (precursor) tolerance in ppm; lower = stricter. `--mass-acc-ms1` |
| Search & scoring | mass_acc | `09_diann_mass_acc_ms2` | `mass_acc_ms2` | `diann.mass_acc` ⚠ | `search_mass_acc_ms2` | `search.mass_acc_ms2` | MS2 (fragment) tolerance in ppm; lower = stricter. `--mass-acc` |
| Search & scoring | mass_acc | `05c_diann_unrelated_runs` | `unrelated_runs` | `diann.unrelated_runs` | `search_mass_acc_unrelated_runs` | `search.mass_acc_unrelated_runs` | Per-run mass-acc + RT window. `--individual-mass-acc --individual-windows` |
| Search & scoring | scoring | `10_diann_scoring_qvalue` | `scoring_qvalue` | `diann.qvalue` | `search_scoring_qvalue` | `search.scoring_qvalue` | FDR q-value threshold; typical 0.01. `--qvalue` |
| Search & scoring | protein | `11a_diann_protein_pg_level` | `protein_pg_level` | `diann.pg_level` | `search_protein_pg_level` | `search.protein_pg_level` | Protein grouping: 0=isoform IDs, 1=names, 2=genes (default). `--pg-level` |
| Search & scoring | protein | `11c_diann_protein_ids_to_names` | _(add)_ ⚠ | `diann.ids_to_names` | `search_protein_ids_to_names` | `search.protein_ids_to_names` | Protein IDs as gene names when FASTA lacks `GN=`. `--ids-to-names` |
| Quantification | — | `05b_diann_scan_window` | `scan_window` | `diann.scan_window` | `quant_scan_window` | `quant.scan_window` | Scan-window radius (scans) for peak/feature detection; AUTO to auto-determine. `--window` |
| Quantification | — | `12a_diann_quantification_reanalyse` | `quantification_reanalyse` | `diann.reanalyse` | `quant_reanalyse` | `quant.reanalyse` | Match-between-runs (MBR) + library refinement. `--reanalyse` |
| Quantification | — | `12b_diann_quantification_no_norm` | `quantification_no_norm` | `diann.no_norm` | `quant_no_norm` | `quant.no_norm` | Disable cross-run normalization. `--no-norm` |
| Output | — | `12c_diann_quantification_export_quant` | `quantification_export_quant` | `diann.export_quant` ⚠ | `output_fragment_quant` | `output.fragment_quant` | Export fragment-level per-run quantities (larger report). `--export-quant` |
| Output | — | `14_include_libs` | _(add)_ ⚠ | `include_libs` | `output_include_libs` | `output.include_libs` | Stage predicted + refined spectral libraries as a zip. |
| Output | — | `15_generate_pmultiqc` | _(add)_ ⚠ | `generate_pmultiqc` | `output_pmultiqc` | `output.pmultiqc` | Generate a pmultiqc HTML QC report. |
| Advanced | — | `13_diann_freestyle` | `freestyle` | `diann.freestyle` | `advanced_freestyle` | `advanced.freestyle` | Extra raw DIA-NN flags appended verbatim (at your own risk). |
| Advanced | — | `99_other_verbose` | `verbose` | `diann.verbose` | `advanced_verbose` | `advanced.verbose` | DIA-NN log verbosity 0–3. `--verbose` |
| _(bookkeeping)_ | — | `application_version` | _(none)_ | _(B-Fabric internal)_ | `application_version` _(unchanged)_ | — | B-Fabric bookkeeping (executable version); not a DIA-NN parameter. |

**Internal-only fields (no GUI key — leave as-is):** `diann.diann_bin`,
`library_predictor`, `enable_step_c` (a SUSHI param + B-Fabric map entry, but not
in the A386 GUI XML), and the top-level `var_mods` dup.

⚠ **flags carried into the rename:** `diann.mass_acc` is the **MS2** value while MS1
is `diann.mass_acc_ms1` (asymmetric — fixed by `search.mass_acc_ms2`);
`diann.export_quant` → `output.fragment_quant`. **SUSHI gaps closed:**
`ids_to_names`, `include_libs`, `generate_pmultiqc` gain SUSHI keys `(add)`; SUSHI's
`order_fasta` reconciles to `input_fasta_use_custom`. **FASTA is list-shaped**
(`inputs.fasta_databases`): each frontend fills it with what it has — AppRunner's
single dropdown pick (+ optional `additional`) → a 1–2 element list; SUSHI's
`fasta_databases` multi-select → N. A length-1 list is normal; no executable
multi-select needed.

### Category → order (grouping shown by document position + XML banners)

```
Pipeline            pipeline_*                                          <!-- Pipeline / run setup -->
Input               input_fasta_*                                       <!-- Input -->
Library generation  lib_digestion_, lib_peptide_, lib_precursor_,       <!-- Library generation -->
                    lib_fragment_, lib_mods_
Search & scoring    search_mass_acc_, search_scoring_, search_protein_  <!-- Search & scoring -->
Quantification      quant_scan_window, quant_reanalyse, quant_no_norm   <!-- Quantification -->
Output              output_fragment_quant, output_include_libs, output_pmultiqc   <!-- Output -->
Advanced            advanced_*                                          <!-- Advanced -->
```

DIA-NN GUI mapping: Input → **Input**; Library generation → **Precursor ion
generation**; Search & scoring → **Algorithm**; Quantification → **Algorithm**
(extraction / MBR / normalization); Output → **Output**; Advanced → **Additional
options**.

---

## Internal pydantic model (Depth 2) — target shape

One sub-model per category (the `new pydantic` column above); fields are flat,
named `<subcategory>_<name>`. The naming quirks vanish: `mass_acc_ms1`/`mass_acc_ms2`
symmetric, and `fragment_quant`.

```python
class PipelineParams(BaseModel):
    diann_version: str
    workflow_mode: str
    is_dda: bool
    raw_converter: str

class InputParams(BaseModel):
    fasta_databases: list[str] = []   # one or more FASTA paths; DIA-NN merges multiple --fasta
    fasta_use_custom: bool            # also inject custom order.fasta from the working dir

class LibParams(BaseModel):
    digestion_cut: str
    digestion_missed_cleavages: int
    peptide_min_length: int
    peptide_max_length: int
    precursor_charge_min: int
    precursor_charge_max: int
    precursor_mz_min: int
    precursor_mz_max: int
    fragment_mz_min: int
    fragment_mz_max: int
    mods_variable: list[VarMod] = []
    mods_unimod4: bool
    mods_met_excision: bool
    mods_no_peptidoforms: bool

class SearchParams(BaseModel):
    mass_acc_ms1: IntOrAuto
    mass_acc_ms2: IntOrAuto                 # was the bare `mass_acc`
    mass_acc_unrelated_runs: bool = False
    scoring_qvalue: float
    protein_pg_level: int
    protein_ids_to_names: bool

class QuantParams(BaseModel):
    scan_window: IntOrAuto
    reanalyse: bool
    no_norm: bool

class OutputParams(BaseModel):
    fragment_quant: bool = False            # was diann.export_quant
    include_libs: bool
    pmultiqc: bool = True                   # was generate_pmultiqc

class AdvancedParams(BaseModel):
    freestyle: list[str] = []
    verbose: int

class DIANNRunnerParams(BaseModel):
    pipeline: PipelineParams
    inputs:   InputParams                   # `inputs` (plural) avoids shadowing input()
    lib:      LibParams
    search:   SearchParams
    quant:    QuantParams
    output:   OutputParams
    advanced: AdvancedParams
    # internal-only, no GUI key:
    diann_bin: str
    library_predictor: str
    enable_step_c: bool
```

---

## Decisions resolved (Q&A, 2026-06-29)

- **`inputs` namespace + one-level nesting** — pydantic path = GUI key split on the
  first `_` (`lib_precursor_charge_min` → `lib.precursor_charge_min`).
- **`output_fragment_quant`** — faithful to `--export-quant` (quant + correlations).
- **`advanced_verbose`** — stays under Advanced (no separate `logging` group).
- **FASTA = list** — `inputs.fasta_databases: list[str]`; each frontend fills it with
  what it has (AppRunner 1–2, SUSHI N). No executable multi-select needed; a length-1
  list is fine.

All naming/structure questions are now settled — the doc is ready to implement against.

---

## Migration plan — change in lockstep (when approved)

**B-Fabric GUI path**
1. `bfabric_executable/executable_A386_DIANN_3.2.xml` — rewrite `<key>`s, reorder
   blocks, update `<!-- … -->` banners.
2. `slurmworker/config/A386_DIANN_23/executable_A386_DIANN23plus.xml` — mirror of (1).
3. `BFABRIC_TO_DRUNNER` — `snakemake_helpers.py:249-284`: **left** → new keys,
   **right** → new canonical names.
4. `_bfabric_fasta()` — `snakemake_helpers.py:289-297`: build the `databases` list
   (main + freestyle `additional`) instead of selecting a single path.

**SUSHI GUI path**
5. `sushi/master/lib/DIANNApp.rb` — `@params['…']` keys → unified keys; add the
   three `(add)` params (`ids_to_names`, `include_libs`, `pmultiqc`).
6. `SUSHI_TO_DRUNNER` — `sushi_adapter.py:40-71`: left+right update as (3).

**Internal model path (Depth 2 — the deep part)**
7. `request.py` — replace `DiannParams`/`FastaParams` with the 7 category sub-models
   on `DIANNRunnerParams`.
8. `param_core.py` — `build_internal_params` + the `FieldSpec` table: emit the new
   nested shape; transforms/defaults move under their sub-model.
9. `create_diann_workflow()` — `snakemake_helpers.py:406+`: read nested paths
   (`p.lib.precursor_charge_min`, …) to build `DiannWorkflow`. **`DiannWorkflow`
   stays flat** (1:1 CLI builder) — only the mapping into it changes.
10. `Snakefile.DIANN3step.smk` — wherever it indexes the parsed params dict.
11. TOML round-trip (`to_toml`/`from_toml`) follows the model; regenerate any
    committed `diann_runner_params.toml` fixtures.

**Fixtures & tests (all paths)**
12. `params.yml` / `data/*/` fixtures; `tests/` for B-Fabric, SUSHI, and the param
    model (`extra="forbid"` flags every drift loudly).

**Deferred (per earlier agreement):** the non-A386 executables (A362, A366,
`DIANN/executable_25894.xml`) use a different pipe-delimited scheme
(`01|msconvertopts`) — align in a later pass.
