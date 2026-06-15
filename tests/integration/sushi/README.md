# Integration test — `run-diann sushi` entry point (committed, CI-able)

Companion to [`../WU346549/`](../WU346549/): that case exercises the **AppRunner**
entry point (`run-diann apprunner` / `diann-snakemake`) from real bfabric inputs
it downloads (~9 GB). This case exercises the **SUSHI** entry point
(`run-diann sushi`) from fully **committed** inputs — no downloads, no gstore,
no containers, no DIA-NN execution.

## What's committed

| File | Role |
|------|------|
| `sushi_params.yml` | The flat readable-key param mapping a real SUSHI job emits (what `EzAppDiann` dumps). Taken from a real SUSHI invocation, **not** reverse-engineered from an AppRunner `params.yml`. |
| `input_dataset.tsv` | SUSHI dataset: `Name` + `Thermo RAW [File]` + a `[Factor]` column. |
| `input/db.fasta` | Tiny stub FASTA that `fasta_databases` points at. |
| `run.sh` | Driver. |

Raw files (`input/raw/*.raw`) are **not** committed — `run.sh` creates empty
stubs from `input_dataset.tsv` on each run (a dry-run only needs them to exist).

## Run

```bash
./run.sh          # dry-run (default): sushi adapter + Snakemake DAG build
./run.sh run      # execute (needs containers + real raws — not for CI)
```

The dry-run goes all the way through the real Snakefile: `run-diann sushi`
parses `sushi_params.yml` (readable keys → DIANNRunnerParams, via the sushi
adapter), normalizes `input_dataset.tsv`, derives the raw-file directory from
the dataset (resolved under `--data-root`, which `run.sh` points at this fixture),
pulls the FASTA from `fasta_databases`, materializes the work dir, and builds the
full DAG (`snakemake -n`). `register_outputs=False` (SUSHI delivers via g-req).
