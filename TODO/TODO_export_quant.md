# TODO: enable DIA-NN `--export-quant` (fragment-level quantities)

**Date:** 2026-06-22
**Status:** Implemented as an opt-in first-class option, off by default.

## Why this came up

The downstream `anndata_proteomics_bridge` (APB) converts DIA-NN output to AnnData/MuData and
wants a **fragment-level** modality. That needs the per-fragment quantity columns
(`Fragment.Quant.Raw`, `Fragment.Quant.Corrected`, `Fragment.Correlations`, and in some versions
`Fragment.Info`). Investigating the ProteoBench DIA-NN reference files showed:

- **DIA-NN 1.x** `report.tsv` carried those fragment columns **by default**.
- **DIA-NN 2.x** `report.parquet` **omits them** — the only fragment-ish columns left are
  `Best.Fr.Mz` / `Best.Fr.Mz.Delta` (a single best-fragment m/z, not abundances).
- Per the [DIA-NN README](https://github.com/vdemichev/DiaNN/blob/master/README.md), 2.x exposes
  per-fragment quantities only via **`--export-quant`** ("appends … observed (per-run) information
  on the library fragment ions of a precursor (top 12 sorted by the reference intensity) … observed
  signal intensity (non-normalised) … fragment XIC quality").
- Cross-checked: **none** of the cached ProteoBench DIA-NN runs (1.7–2.3) passed `--export-quant`
  (only one 2.2.0 run used `--xic`).

So without `--export-quant`, DIA-NN 2.x runs produced by this runner cannot feed APB's
fragment-level / 5-level MuData (only ion / peptidoform / peptide / protein).

## Current status in diann_runner

- **Documented:** yes, in `docs/DIANN_PARAMETERS.md` ("Export Options"). The entry now
  documents the fragment columns, the DIA-NN 2.x omits-by-default caveat, APB as a
  downstream consumer, and the report-size trade-off.
- **Exposed as a parameter:** yes. B-Fabric key
  `12c_diann_quantification_export_quant` and the SUSHI GUI param
  `quantification_export_quant` (`DIANNApp.rb`) both map to canonical `export_quant`
  and emit `--export-quant` on *quantifying* raw-data steps (skipped on a library-only
  Step B run).
- **Reachable:** via the dedicated checkbox in B-Fabric or SUSHI, or, still, via
  freestyle passthrough for advanced users.
- **On by default:** no.

## Proposed actions

1. **Done:** add a dedicated B-Fabric toggle, default off.
2. **Trade-off to weigh:** fragment export substantially enlarges `report.parquet` (top-12
   fragments × every precursor × every run). Only worth it when a fragment-level downstream is
   actually wanted → argues for opt-in (b) over default (a).
3. **Consider `--xic` / `--xic-theoretical-fr`** for richer fragment extraction (separate
   `.xic.parquet`); decide whether that's in scope or a separate diagnostic option.
4. **Expand `docs/DIANN_PARAMETERS.md`** `--export-quant` entry: the columns it adds, the 2.x
   omits-by-default caveat, and that it's required for APB's fragment level.
5. **Capture a reference run:** once enabled, archive one DIA-NN 2.x `--export-quant` report so APB
   can author + validate `diann/v2/parse_diann_fragment.toml` against its real columns (2.x may use
   `Fragment.Info` labels → a labelled fragment rule, vs the positional v1 rule).

## Open questions

- Default-on vs opt-in bfabric param vs freestyle-only?
- Storage budget for the larger reports (gstore impact)?
- Which steps carry it — B, C, or both? (freestyle currently applies to B/C.)
- Pair with `--xic` or keep fragment export minimal?

## Links

- DIA-NN README (`--export-quant`, `--xic`): https://github.com/vdemichev/DiaNN/blob/master/README.md
- DIA-NN discussion on Fragment.Quant columns: https://github.com/vdemichev/DiaNN/discussions/951
- Downstream consumer: `anndata_proteomics_bridge` — DIA-NN fragment level / version-folder rules
  (`parsing_rules/diann/v1/parse_diann_fragment.toml` exists for 1.x; `v2` blocked on this).
