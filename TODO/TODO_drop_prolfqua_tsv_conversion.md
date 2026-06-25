# TODO: Drop the prolfqua-format TSV conversion

## Goal

Stop producing the prolfqua-format `WU<id>_report.tsv` (the one whose `Run` column is
renamed to `File.Name`). Let every downstream consumer read DIA-NN's native output
directly. This removes a DIA-NN 1.x compatibility shim and unblocks pmultiqc, which is
broken by the rename.

This is **gated on a prolfquapp change** (tracked in
`prolfqua_fml/prolfquapp/TODO/TODO_diann2x_native_output.md`). Do not drop the conversion
until prolfquapp can read native DIA-NN 2.x output.

## Verified Current State (2026-06-24)

### Where the rename happens

`convert_parquet_to_tsv()` in `src/diann_runner/snakemake_helpers.py:525-528`:

```python
column_mapping = {
    'Run': 'File.Name',
}
df = df.rename(columns=column_mapping)
```

DIA-NN 2.x writes the main report (parquet) with a bare `Run` column (e.g.
`20260623_010_C42222_S1172811_Plate_7001_H1`) plus `Run.Index`, and no `File.Name`. The
conversion renames `Run` → `File.Name` and writes a TSV.

Called once, from the `convert_parquet_to_tsv` rule
(`src/diann_runner/Snakefile.DIANN3step.smk:349-360`), reading `report_parquet`.

### Who consumes the renamed TSV

Two consumers reference `FINAL_QUANT_OUTPUTS["report_tsv"]`:

1. **`diann-qc`** (`rule diannqc`, Snakefile:395) — our own plotter.
2. **prolfqua QC** (`rule prolfqua_qc`, Snakefile:459) — via the report's parent dir.

### Who actually needs the rename — verified

| Consumer | Needs `File.Name`? | Can read native DIA-NN 2.x? | Notes |
|----------|--------------------|-----------------------------|-------|
| **prolfquapp** | **Yes** | **No** (today) | `diann_read_output()` derives `raw.file` from `File.Name` (`prolfquapp/R/preprocess_DIANN.R:40-44`); reads TSV only (`readr::read_tsv`); `get_DIANN_files()` greps `report\.tsv$`. **This is the sole reason the rename exists.** |
| **diann-qc** | No | **Yes, already** | `plotter.py:138-140` reads `.parquet` and calls `_normalize_file_column()` (its own `Run`→`File.Name` shim, `plotter.py:31-43`). The `stats.tsv` it also reads has native `File.Name`. |
| **pmultiqc** | No — **broken by it** | Yes (parquet) | Requires the native `Run` column; the renamed TSV crashes it. See `TODO_pmultiqc_integration.md`. |

Conclusion: the `Run`→`File.Name` rename is a **prolfquapp-only** DIA-NN 1.x compatibility
shim. `diann-qc` does not need it; pmultiqc is actively broken by it.

## Proposed Change

1. **Update prolfquapp first** (cross-repo prerequisite) to read native DIA-NN 2.x output
   — see `prolfqua_fml/prolfquapp/TODO/TODO_diann2x_native_output.md`.
2. **Point `diann-qc` at the parquet.** Change `rule diannqc` to pass
   `FINAL_QUANT_OUTPUTS["report_parquet"]` instead of `report_tsv`. No plotter code change
   is needed — `load_data()` already branches on `.parquet` and normalizes the column.
3. **Point `prolfqua_qc` at the parquet** (after step 1), or have prolfquapp's
   `get_DIANN_files()` discover the parquet in the same directory.
4. **Remove the `convert_parquet_to_tsv` rule and helper** (or reduce it to a no-op /
   the DDA `PG.Quantity` shim only, if that is still needed — verify the `is_dda` branch
   at `snakemake_helpers.py:532-534` independently).
5. Drop `report_tsv` from `get_final_quantification_outputs()` once no rule references it.

After this, the parquet is the single source of truth; all three QC tools (diann-qc,
prolfqua, pmultiqc) read it.

## Why the prolfquapp side is low-risk

The parquet `Run` column is already the bare run basename (no path, no extension).
prolfquapp's `raw.file` derivation does `basename(gsub("\\\\","/", File.Name))` then strips
`\\.d\\.zip$|\\.d$|\\.raw$|\\.mzML$`. Applied to `Run`, every step is a no-op, so the
resulting `raw.file` values are **identical** to today. The change is mechanical.

## Risks / Checks

- Confirm the `is_dda` / `PG.Quantity = PG.MaxLFQ` shim (`snakemake_helpers.py:532-534`)
  is still required by prolfqua for DDA; if so, keep that transformation but apply it to
  the parquet read path rather than producing a renamed TSV.
- `diann-qc`'s `stats.tsv` read is unaffected (native `File.Name`), but re-run the
  `diannqc` rule against the parquet to confirm the PDF is identical.
- Any external/manual tooling that consumed `WU<id>_report.tsv` directly would lose it;
  grep deployment scripts / SUSHI (`DIANNApp.rb`) before removing.
- `diann_runner` and the deployed `slurmworker` are paired change surfaces.

## Sequencing

```text
[prolfquapp: read native DIA-NN 2.x]  ->  [diann_runner: diann-qc reads parquet]
        (cross-repo, blocks)                    (can land independently / first)
                       \                       /
                        v                     v
              [diann_runner: drop convert_parquet_to_tsv + report_tsv]
                                   |
                                   v
                  [pmultiqc reads parquet with no rename]
```

diann-qc can be switched to the parquet **independently and first** (it already supports
it), shrinking the TSV's consumer set to prolfqua before the final removal.

## Acceptance Criteria

- No rule produces a `Run`→`File.Name`-renamed TSV.
- `diann-qc` PDF is generated from the parquet and matches the prior output.
- prolfqua QC runs from native DIA-NN output (parquet or native-name TSV).
- pmultiqc consumes the parquet with no staging rename of the report.
- `get_final_quantification_outputs()` no longer exposes `report_tsv` (or it is clearly
  documented as deprecated) once unreferenced.
