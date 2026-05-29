# Integration tests — end-to-end Snakemake runs from real bfabric inputs

Each subdirectory is a self-contained, runnable work directory for one real
workunit. Reusing the *real* `params.yml` + `dataset` from a bfabric run
exercises every parameter parser, every flat-key mapping, and every workflow
stage with production-shaped inputs rather than synthetic ones.

See [`../../TODO/TODO_integration_test.md`](../../TODO/TODO_integration_test.md)
for the full plan, rationale, and open questions.

## Cases

| Directory | Workunit | Dataset | Notes |
|-----------|----------|---------|-------|
| [`WU346549/`](WU346549/) | WU346549 | ProteoBench DIA Orbitrap AIF (triple-proteome HYE) | DIA-NN 2.5.0, `two_step`, `enable_step_c=false` |

## How a case works

Only the *sources* are committed, at their real work-tree positions: the setup
script, `run.sh`, `tree.txt`, and the small inputs — `params.yml`, `inputs.yml`,
`input/order.fasta`, and `input/raw/dataset.parquet` (the upstream input the
Snakefile reads). Everything large is downloaded and everything generated is
gitignored — including the root `dataset.csv`, which snakemake's `dataset_csv`
rule regenerates from `dataset.parquet`. Each case ships a local `.gitignore`
that tracks only those sources.

```bash
cd tests/integration/WU346549

./setup_integration_test.py   # zero-arg: builds input/ tree, downloads FASTA + raws
./run.sh                      # dry-run (default)
./run.sh run                  # execute the workflow
CORES=64 ./run.sh run         # override core count
```

`setup_integration_test.py` downloads:

- the **FASTA** — ProteoBench triple-proteome HYE database, from
  <https://proteobench.cubimed.rub.de/fasta/> (saved under the FGCZ name the
  production `params.yml` references);
- the **raw files** — 6 DIA Orbitrap AIF files (~9.2 GB total, ~1.5 GB each),
  PRIDE / ProteomeXchange accession **PXD028735**.

Downloads are resumable and skip files already present at full size, so both
scripts are safe to re-run.

## Container runtime

`diann-snakemake` auto-detects the runtime (apptainer wins over docker when both
are installed), so the same `run.sh` works on the docker dev box and on the
apptainer host. On an Apple-Silicon Mac use docker (apptainer is Linux-only);
run the apptainer leg on fgcz-c-043.

| Host | `detect_runtime()` | Verifies |
|---|---|---|
| Dev machine (docker) | `docker` | Docker path; backwards compatibility |
| fgcz-c-043 (apptainer) | `apptainer` | Apptainer path; SIF builds; Wine msconvert |

Compare across runtimes: DIA-NN `.config.json` (modulo paths, byte-identical),
`Result_WU{id}.zip` parquet contents (within numerical tolerance), and the prozor
parquet (protein groups exact).
