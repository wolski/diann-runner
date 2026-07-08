# TODO: pmultiqc Integration

## Goal

Generate a pmultiqc HTML report as an optional downstream QC output of a completed
DIA-NN runner workflow — a third QC artifact alongside the existing `diann-qc` (PDF)
and prolfqua QC (`qc_result/`) outputs.

## Status (2026-06-24)

- `pmultiqc>=0.0.44` added as a **first-class dependency** in `pyproject.toml`.
- Install + end-to-end run validated locally on `tests/DIANN/Result_WU347715.zip`
  (see **Validation** below). The report **only builds from the DIA-NN parquet**, not
  from the runner's `*_report.tsv` — that file is the prolfqua-reformatted report and
  is structurally incompatible with pmultiqc. This is the central finding of this TODO.

## Boundary

- `diann_runner` owns RAW files, RAW conversion, DIA-NN execution, and collecting final runner outputs.
- `pmultiqc` consumes **completed DIA-NN output files only** — specifically the
  `WU<id>_report.parquet` report and (optionally) the DIA-NN run log.
- Do not copy or stage RAW files for pmultiqc.
- Keep `raw_file_dir` as the runner input contract; pmultiqc must not depend on it.
- A small copy/staging step for pmultiqc report inputs is acceptable.

This TODO is the `diann_runner` side of the work. The pmultiqc side (broadening its
file-matching patterns and accepting the runner's report schema) is tracked in
`pmultqc/TODO_pmultiqc_diannrunner_integration.md`. Keep the two in sync.

## Validation (2026-06-24)

Verified in an isolated venv (Python 3.13, `uv 0.9.8`) against
`tests/DIANN/Result_WU347715.zip` (a Step B output).

### Install

- pmultiqc resolves to `0.0.44`, MultiQC to `1.33`; ~73 packages total
  (heavy ones: `pyopenms==3.4.0`, `pandas==3.0.3`, `numpy==2.5.0`, `pyarrow==24.0.0`,
  `scikit-learn`, `statsmodels`, `polars-lts-cpu`, `plotly`, `kaleido`).
- Timing: **~13 s cold** (`--no-cache`, full fresh download incl. pyopenms),
  **~1.6 s warm** cache.
- Co-resolves with `diann_runner`'s own pins with **no conflict**
  (`uv pip install -e . pmultiqc` succeeds).

### There is no `pmultiqc` command

pmultiqc has **no `[project.scripts]`** — it registers only MultiQC plugin entry points
(`pmultqc/pyproject.toml:60-84`). The binary stays `multiqc`; pmultiqc auto-activates
via its `execution_start` hook and adds `--diann-plugin`. The only pmultiqc-specific
entry point is `multiqc --pmultiqc-version`.

### The TSV report does not work; the parquet does

- Pointing pmultiqc at the runner's `WU<id>_report.tsv` crashes with
  `KeyError: "['Run'] not in index"`.
- Root cause: `convert_parquet_to_tsv()`
  (`diann_runner/src/diann_runner/snakemake_helpers.py:525`) renames **`Run` →
  `File.Name`** to make the TSV prolfqua-compatible. pmultiqc requires the native DIA-NN
  `Run` column (`pmultqc/pmultiqc/modules/common/dia_utils.py:252`). The prolfqua TSV
  no longer has it.
- The `WU<id>_report.parquet` retains the native `Run` column (verified: parquet has
  `Run` + `Run.Index`, no `File.Name`). Feeding the parquet produces a complete
  **~3.4 MB** HTML report, detects the DIA-NN version from the log
  (`2.6.0` in this fixture), and falls back gracefully on the missing experimental
  design ("experimental grouping was parsed using Run names").

### The "missing Modifications column" is a non-issue

pmultiqc does **not** read a `Modifications` column from DIA-NN. It **derives** it from
`Modified.Sequence` by parsing the inline `(UniMod:xx)` tokens
(`pmultqc/pmultiqc/modules/common/dia_utils.py:234`, function `_process_modifications`).
The `required_cols = [..., "Modifications", ...]` check at line 252 runs *after* that
derivation, so it is satisfied.

- **This is not a DIA-NN option we failed to set.** There is no DIA-NN flag that emits a
  `Modifications` column.
- The only DIA-NN requirement is `Modified.Sequence`, which is a core report column,
  always present (in both parquet and TSV); no flag disables it.
- Modifications only show as `Unmodified` if the search ran without variable mods. The
  fixture searched oxidation (`UniMod:35`), so the modification sections populate.

### Caveats surfaced during validation

- **`rich` version fragility.** With `rich==15.0.0` (pmultiqc-only venv), MultiQC 1.33's
  error-display path crashes hard with `module 'rich' has no attribute 'panel'`, masking
  the real error. The co-install with `diann_runner` happened to resolve `rich==14.3.4`,
  which avoids it. `rich` is unpinned — fragile.
- **pandas 2 → 3 jump.** No `uv.lock` exists, so the project floats to latest. The
  current project `.venv` runs `pandas 2.3.3 / numpy 2.4.0 / pyarrow 22.0.0`; a fresh
  resolve with pmultiqc lands the whole runner env on `pandas 3.0.3 / numpy 2.5.0 /
  pyarrow 24.0.0`. pandas 3.0 has breaking changes — smoke-test the prozor/plotter paths
  and consider committing a `uv.lock` to pin this deliberately.

## How pmultiqc Discovers DIA-NN Files

Verified against the pmultiqc source (`/Users/wolski/projects/pmultqc`):

**1. `--diann-plugin` is a boolean flag, not a path option** (`pmultiqc/cli.py:73`).
The directory is MultiQC's positional argument:

```bash
multiqc <input_dir> --diann-plugin -o <output_dir>
```

**2. File search patterns** (`pmultiqc/main.py:128-142`):

| Purpose | pmultiqc pattern | Matches runner output? | Usable? |
|---------|------------------|------------------------|---------|
| TSV report | `*report.tsv` | Yes — matches `WU<id>_report.tsv` | **No** — prolfqua TSV lacks `Run`, crashes |
| Parquet report | `report.parquet` (exact) | No — misses `WU<id>_report.parquet` | **Yes, after renaming** to `report.parquet` |
| Log (txt) | `report.log.txt` (exact) | No — misses `diann_quant{B,C}.log.txt` | Yes, after renaming |
| Log (alt) | `diannsummary.log` (exact) | No | n/a |

**3. How the DIA-NN module consumes them** (`pmultiqc/modules/diann/diann.py:90-117`):

- The report search tries `diann_report_tsv` **first**, then `diann_report_parquet`.
  The report is **required** — if neither is found, `get_data()` returns `False`.
- The log is used **only** for the DIA-NN version badge (`parse_diann_version`); it is
  optional and non-fatal if absent.

### Consequence for staging

Because pmultiqc tries the TSV pattern first and our TSV is the incompatible
prolfqua-format file, **we cannot point pmultiqc at `out-DIANN_quant{B,C}/` directly**
(it would match the broken TSV and crash). The staging directory must:

1. Contain the **parquet renamed to `report.parquet`** (exact name required by the
   pattern) — this is the report pmultiqc reads.
2. **Not contain any `*report.tsv`** — otherwise pmultiqc picks it first and crashes.
3. Optionally contain the run log renamed to `report.log.txt` (version badge only).

## Current DIA-NN Runner Outputs

Final output directory depends on the workflow mode:

- Step C enabled: `out-DIANN_quantC/`
- Step C disabled or single-step: `out-DIANN_quantB/`

Relevant files (Step C shown; substitute `quantB` when Step C is disabled):

```text
out-DIANN_quantC/WU<id>_report.parquet       # pmultiqc reads THIS (native Run column)
out-DIANN_quantC/WU<id>_report.tsv           # prolfqua-format (Run->File.Name); do NOT feed
out-DIANN_quantC/diann_quantC.log.txt        # rename -> report.log.txt for version badge
out-DIANN_quantC/dataset.csv                 # runner experimental design (see below)
```

## What pmultiqc Will and Will Not Show

pmultiqc's DIA-NN mode can use optional inputs that `diann_runner` does **not** emit.
Feeding only the parquet + log produces a report-derived view:

- **Populated** (report-derived): ID counts, peptides per protein, charge distribution,
  quantification tables, delta mass, RT, and **modifications** (derived from
  `Modified.Sequence`).
- **Empty / absent**:
  - **Experimental design / conditions** — pmultiqc reads `*sdrf.tsv` or
    `experimental_design.tsv`. `diann_runner` produces `dataset.csv` (different schema),
    which pmultiqc does not read. Without it, grouping falls back to run names.
  - **MS1-level metrics (TIC/BPC, MS1 peaks)** — derived from `*.mzML` or
    `*_ms_info.parquet` (via `quantms-utils`). `diann_runner` emits neither. Feeding
    mzML is possible but is spectra input and is out of scope (boundary).

Acceptable for a first integration; document the limitation so the output is not
mistaken for breakage.

## Proposed First Implementation

Add a Snakemake rule after final DIA-NN quantification that stages the minimal pmultiqc
inputs (parquet + log) and runs MultiQC with the DIA-NN plugin.

Target structure:

```text
pmultiqc_input/
  report.parquet          # renamed from WU<id>_report.parquet (native Run column)
  report.log.txt          # renamed from diann_quant{B,C}.log.txt (version badge only)

pmultiqc_result/
  pmultiqc_diann_report.html
  pmultiqc_diann_report_data/
```

Staging step (Step C shown; use `quantB` when Step C is disabled):

```bash
mkdir -p pmultiqc_input
cp out-DIANN_quantC/WU*_report.parquet   pmultiqc_input/report.parquet
cp out-DIANN_quantC/diann_quantC.log.txt pmultiqc_input/report.log.txt
# IMPORTANT: do not copy WU*_report.tsv into pmultiqc_input/ — pmultiqc tries the TSV
# pattern first and the prolfqua-format TSV crashes (missing Run column).
```

## MultiQC Command

```bash
multiqc pmultiqc_input \
  --diann-plugin \
  -o pmultiqc_result \
  --filename pmultiqc_diann_report.html \
  --force \
  --verbose
```

The input directory is the positional argument; `--diann-plugin` is a boolean flag.
`pmultiqc_diann_report.html` is a static filename and can be changed later.

## Dependency Strategy

Now a first-class dependency (`pmultiqc>=0.0.44` in `pyproject.toml`):

```bash
uv pip install -e .
```

This is Option 1 (pip dependency in the runner's own environment), chosen over a
container image for now. Trade-offs recorded in **Validation** above: ~50 extra
packages incl. `pyopenms`, and a `pandas 2 -> 3` bump on the shared env. Before
production, consider:

- committing a `uv.lock` to pin `pandas` / `rich` / `pyopenms` deliberately, and
- if env weight becomes a problem, revisiting a `pmultiqc` container image + thin
  wrapper (mirroring `prolfquapp-docker` / `deploy_dict["prolfquapp_image"]`).

## Snakemake Integration Sketch

`get_final_quantification_outputs()`
(`diann_runner/src/diann_runner/snakemake_helpers.py:475`) already exposes
`report_parquet` — **no helper change is needed for the report**. The DIA-NN run rules
also already declare the log as a named output
(`runlog = "{OUTPUT_PREFIX}_quant{B,C}/diann_quant{B,C}.log.txt"`, Snakefile lines
~217/309/337), but the helper does not expose it.

**Optional prerequisite (only for the version badge):** add a `runlog` key to
`get_final_quantification_outputs()`:

```python
"runlog": f"{output_prefix}_{step}/diann_quant{step[-1]}.log.txt",
```

Rule shape (mirrors the existing `diannqc` / `prolfqua_qc` rules):

```python
rule pmultiqc_diann_report:
    input:
        report = FINAL_QUANT_OUTPUTS["report_parquet"],
        runlog = FINAL_QUANT_OUTPUTS["runlog"],   # optional; version badge only
    output:
        html = "pmultiqc_result/pmultiqc_diann_report.html",
    log:
        logfile = "logs/pmultiqc_diann_report.log"
    shell:
        """
        rm -rf pmultiqc_input pmultiqc_result
        mkdir -p pmultiqc_input
        cp {input.report:q} pmultiqc_input/report.parquet
        cp {input.runlog:q} pmultiqc_input/report.log.txt
        multiqc pmultiqc_input --diann-plugin \
          -o pmultiqc_result \
          --filename pmultiqc_diann_report.html \
          --force --verbose
        test -s {output.html:q}
        """
```

Gate the rule behind a config flag and add its output as a final target only when
enabled (`FINAL_TARGETS`, Snakefile lines ~105-111):

```python
if WORKFLOW_PARAMS.get("generate_pmultiqc", False):
    FINAL_TARGETS.append("pmultiqc_result/pmultiqc_diann_report.html")
```

## Output Packaging

`rule zip_diann_result` (Snakefile ~402) folds extra directories into
`Result_WU<id>.zip` via `extra_dirs=[...]` (that is how `qc_result/` gets in). Options:

1. **First version:** emit `pmultiqc_result/` beside the other outputs as a standalone
   final target; do not add it to the zip yet.
2. **Once delivery is confirmed:** add `pmultiqc_result/` to the `extra_dirs` list in
   `zip_diann_result`, the same way `qc_result/` is included.

## Configuration

Add a boolean parameter, default `false` until dependency and delivery are stable:

```text
generate_pmultiqc: false
```

Per the "XML executable is the source of truth" rule, the flow is:

1. Define `generate_pmultiqc` in the Bfabric XML executable
   (`bfabric_executable/executable_new.xml`).
2. Parse it in `parse_flat_params()` in `snakemake_helpers.py`.
3. Read it in the Snakefile to gate the rule / final target.
4. Update tests to match the XML values exactly.

Possible later UI label: `Generate pmultiqc HTML report`. Reminder: `diann_runner` and
the deployed `slurmworker` XML/config are paired change surfaces.

## Tests

Use completed DIA-NN output fixtures (e.g. `tests/DIANN/Result_WU347715.zip`), not RAW.

1. Given `WU*_report.parquet` and `diann_quant{B,C}.log.txt`, the rule creates a
   non-empty `pmultiqc_result/pmultiqc_diann_report.html`.
2. The staged parquet is named `pmultiqc_input/report.parquet`; the log is
   `pmultiqc_input/report.log.txt`.
3. **Regression guard:** the staging dir contains no `*report.tsv` (feeding the
   prolfqua TSV crashes with `KeyError: ['Run']`).
4. The rule works for `out-DIANN_quantB` when Step C is disabled.
5. (Optional) `get_final_quantification_outputs()` returns a `runlog` key for both steps.
6. With the log present, the report shows the DIA-NN version; without it, the report
   still builds.
7. Missing `multiqc`/pmultiqc gives a clear dependency failure (non-zero exit).

## Later Root-Cause Cleanup In pmultiqc

The staging step is acceptable for the first integration; the clean fixes live on the
pmultiqc side (tracked in `pmultqc/TODO_pmultiqc_diannrunner_integration.md`):

- Broaden the parquet pattern from `report.parquet` to `*report.parquet`
  (`pmultiqc/main.py:135`) so `WU<id>_report.parquet` is recognized without renaming.
- Add a log pattern for `diann_quant*.log.txt` (`pmultiqc/main.py:138-142`).
- **Schema compatibility:** teach the DIA-NN reader to accept the DIA-NN 2.x schema
  (derive `Run` from `Run.Index`/`File.Name`) so it no longer depends on the legacy
  `Run` column. This would also let the runner's prolfqua TSV work directly.
- Consider reporting the `rich>=15` / MultiQC 1.33 `rich.panel` crash upstream.

After the pattern + schema fixes land, `diann_runner` could point pmultiqc directly at
`out-DIANN_quant{B,C}/` with no staging. Avoid permanent wrapper-only renaming or
special-casing a single workunit ID as the fix.

## Acceptance Criteria

- `run-diann` can optionally produce `pmultiqc_result/pmultiqc_diann_report.html`.
- The report is generated from `WU<id>_report.parquet` (native `Run`), never the
  prolfqua-format `WU<id>_report.tsv`.
- The implementation does not touch RAW-file staging and does not depend on `raw_file_dir`.
- The rule fails loudly (non-zero exit) if the final DIA-NN parquet is missing.
- Validated from an existing completed DIA-NN fixture, not a RAW run.
- The report-derived sections (incl. modifications) populate; the absence of
  experimental-design and MS1 metrics is documented, not mistaken for breakage.
