# Integration test — end-to-end Snakemake run from real bfabric inputs

Validates the full `Snakefile.DIANN3step.smk` workflow end-to-end against a known
input (a ProteoBench dataset previously run through the bfabric production app).
Reusing the *real* `params.yml` + `dataset.parquet` exercises every parameter
parser, every flat-key mapping, and every workflow stage with production-shaped
inputs rather than synthetic ones.

See [`../../TODO/TODO_integration_test.md`](../../TODO/TODO_integration_test.md)
for the full plan, rationale, and open questions.

## Driver: `setup_integration_test.py`

The driver stages inputs into a clean work directory and runs `diann-snakemake`.

### What you provide

From a real bfabric run:

- `params.yml` — flat-key bfabric parameters **plus** the `registration:` block
  (`workunit_id`, `container_id`).
- `dataset.parquet` — sample-to-condition mapping (the workflow's `dataset_csv`
  rule converts this to `dataset.csv`).
- FASTA database referenced by `params.yml`.
- Raw spectrometry files, as either a download URL (`--raw-url`) or an
  already-fetched local file / archive / directory (`--raw-dir`).

### Expected work-directory layout (built by the driver)

```
<work_dir>/
├── params.yml
├── input/
│   ├── <fasta>.fasta            # resolve_fasta_path() forces references to input/<name>
│   └── raw/
│       ├── dataset.parquet
│       ├── sample1.raw          # or .d.zip / .mzML
│       └── ...
```

### Usage

Dry-run (default — stages inputs, then `diann-snakemake -n`):

```bash
python tests/integration/setup_integration_test.py \
    --work-dir /tmp/diann_integration \
    --raw-dir /path/to/raw_files_or_archive \
    --params-yml fixtures/params.yml \
    --dataset-parquet fixtures/dataset.parquet \
    --fasta fixtures/db.fasta
```

Execute the full workflow and verify acceptance criteria:

```bash
python tests/integration/setup_integration_test.py \
    --work-dir /tmp/diann_integration \
    --raw-url https://example.org/proteobench_raw.zip \
    --params-yml fixtures/params.yml \
    --dataset-parquet fixtures/dataset.parquet \
    --fasta fixtures/db.fasta \
    --cores 32 --run
```

`--clean` removes the work dir before staging. `--runtime {docker,apptainer}` is
an *informational* expectation only — the runtime is auto-detected by
`detect_runtime()` (apptainer wins when both are installed).

## Concrete reference case: WU346549 (ProteoBench DIA Orbitrap AIF)

This is the worked example the plan targets — a DIA-NN 2.5.0 `two_step` run on the
ProteoBench triple-proteome HYE benchmark. Two fixtures live in this folder
(gitignored, provided out-of-band):

- `WU346549_work.zip` — contains the real `params.yml` and `dataset.csv`.
- `fastas.zip` — contains `input/order.fasta` + the database FASTA
  (`input/p34486_Proteobench_TripleProteome_20240614.fasta`).

The six raw files (~9.2 GB total, ~1.5 GB each) are **not** shipped; they are
downloaded from **PRIDE accession PXD028735** via the tracked manifest
[`proteobench_PXD028735_dia_aif.txt`](proteobench_PXD028735_dia_aif.txt). The
download is resumable and skips any file already present at full size, so the
command is safe to re-run.

```bash
cd tests/integration

# 1. Unpack the small metadata fixtures (params.yml + dataset.csv)
unzip -o -j WU346549_work.zip params.yml dataset.csv -d /tmp/wu346549_meta

# 2. Stage + download raws + run (dry-run first; add --run to execute)
python setup_integration_test.py \
    --work-dir /tmp/diann_wu346549 \
    --params-yml /tmp/wu346549_meta/params.yml \
    --dataset-csv /tmp/wu346549_meta/dataset.csv \
    --fasta-zip fastas.zip \
    --raw-manifest proteobench_PXD028735_dia_aif.txt \
    --cores 32 --run
```

Notes:

- `--dataset-csv` is converted to the `dataset.parquet` the workflow expects.
- `--fasta-zip` is extracted at the work-dir root because the zip already carries
  the `input/...fasta` layout. (`params.yml` has `03_fasta_use_custom: false`, so
  only the database FASTA is actually used; `order.fasta` is staged but ignored.)
- Raw files keep their exact names — ProteoBench requires they not be renamed.
- `enable_step_c` is `false` for this workunit, so the final outputs live in
  `out-DIANN_quantB/`.

## Acceptance criteria

With `--run`, the driver checks that these exist and are non-empty:

- `out-DIANN_libA/WU{id}_report-lib.predicted.speclib`
- `out-DIANN_quantB/WU{id}_report.parquet`
- `out-DIANN_quant{B,C}/WU{id}_report.parquet` (C when `enable_step_c=true`)
- `out-DIANN_quant{B,C}/WU{id}_report_prozor.parquet`
- `Result_WU{id}.zip`
- `outputs.yml`

(`workunit_id` and `enable_step_c` are read back from the staged `params.yml`.)

## Cross-runtime verification

Run the same test on two hosts and diff the outputs:

| Host                  | `detect_runtime()` | Verifies                                   |
|-----------------------|--------------------|--------------------------------------------|
| Dev machine (docker)  | `docker`           | Docker path; backwards compatibility       |
| fgcz-c-043 (apptainer)| `apptainer`        | Apptainer path; SIF builds; Wine msconvert |

On the apptainer host, populate the SIF cache first
(`deploy.smk all_sif --config sif_builder=native`).

Compare:

- DIA-NN `.config.json` files (modulo paths) — should be byte-identical.
- `Result_WU{id}.zip` parquet contents — match within numerical tolerance.
- prozor parquet — protein groups should match exactly.
