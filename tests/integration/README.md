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
