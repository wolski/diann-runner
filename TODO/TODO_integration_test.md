# TODO: Integration Test (end-to-end Snakemake run from real bfabric inputs)

> **Status (2026-05-29): implemented and committed (`7204650`).** The driver,
> fixtures, FASTA/raw download, and run script are done and the full DAG dry-run
> passes against the real `params.yml`. What remains is the *live* end-to-end run
> + cross-runtime diff — to be done on a Linux box (see **Run Instructions** at
> the bottom). The design landed as a **zero-argument per-workunit case**
> (`tests/integration/WU346549/`) rather than the generic argument-driven sketch
> originally proposed below.

## Goal

Validate the full `Snakefile.DIANN3step.smk` workflow end-to-end against a known input: a [ProteoBench](https://proteobench.cubimed.rub.de/) dataset previously run through the bfabric production app. Reusing the real `params.yml` + `dataset.csv` from that bfabric run means every parameter parser, every Bfabric flat-key mapping, and every workflow stage gets exercised with production-shaped inputs — not synthetic ones.

This is the test we'll use to:

1. ✅ Catch regressions in `parse_flat_params()` / `create_diann_workflow()` / `load_deploy_config()`. *(Validated by the dry-run: all three parse/load the real `params.yml` and build a complete DAG.)*
2. ✅ Smoke-verify the Docker runtime path on dev machines (CI-shaped). *(Dry-run on the M1 dev box auto-detected `docker`.)*
3. ⬜ Smoke-verify the Apptainer runtime path on the apptainer host (fgcz-c-043). *(Pending — needs the Linux apptainer host + populated SIF cache.)*
4. ✅ Confirm the new `container_runtime` flag flow doesn't break anything between Snakefile, wrappers, and `DiannWorkflow`. *(Dry-run shows `--runtime docker` forwarded into the prolfqua/thermoraw commands.)*

## Inputs — DONE (concrete case: WU346549, ProteoBench DIA Orbitrap AIF)

Provided as committed fixtures in `tests/integration/WU346549/fixtures/`, or downloaded by the setup script:

- [x] `params.yml` — flat-key Bfabric parameters (committed fixture).
- [x] `dataset.csv` — sample-to-condition mapping (committed fixture).
- [x] `dataset.parquet` — **generated** from `dataset.csv` by the setup script into `input/raw/dataset.parquet` (the upstream input of rule `dataset_csv`).
- [x] Raw spectrometry files — 6 Thermo `.raw` files, **downloaded** from PRIDE / ProteomeXchange **PXD028735** (~9.2 GB total, ~1.5 GB each). Resumable, skip-if-present.
- [x] Workunit ID + container ID — in the committed `params.yml` `registration` block (`workunit_id: 346549`, `container_id: 37485`, `enable_step_c=false`).
- [x] FASTA database — **downloaded** from ProteoBench (`https://proteobench.cubimed.rub.de/fasta/ProteoBenchFASTA_MixedSpecies_HYE.zip`) and saved under the FGCZ name `params.yml` references (`p34486_Proteobench_TripleProteome_20240614.fasta`). Plus the tiny committed `order.fasta` (iRT + protein-G spike-ins; unused here since `03_fasta_use_custom=false`).

## Folder Layout the Workflow Expects — DONE

Matches `tree.txt` (committed). The setup script builds exactly this in
`tests/integration/WU346549/` (which **is** the snakemake work dir):

```
tests/integration/WU346549/
├── params.yml                   # staged from fixtures/
├── dataset.csv                  # staged from fixtures/
├── inputs.yml                   # staged from fixtures/ (bfabric artifact, informational)
├── input/
│   ├── order.fasta              # staged from fixtures/
│   ├── p34486_..._20240614.fasta # downloaded (ProteoBench)
│   └── raw/
│       ├── dataset.parquet      # generated from dataset.csv  → rule dataset_csv → dataset.csv
│       └── LFQ_Orbitrap_AIF_Condition_{A,B}_Sample_Alpha_0{1,2,3}.raw  # downloaded (PRIDE)
└── (Snakemake-generated outputs: out-DIANN_libA/, out-DIANN_quantB/, logs/, Result_WU346549.zip, ...)
```

## Driver Script — DONE (design changed: zero-arg per-workunit case)

Implemented as **`tests/integration/WU346549/setup_integration_test.py`**, run with
**no arguments** (`./setup_integration_test.py`). It:

1. ✅ Stages the committed fixtures (`params.yml`, `dataset.csv`, `inputs.yml`, `order.fasta`).
2. ✅ Downloads the FASTA from ProteoBench and saves it under the expected FGCZ name.
3. ✅ Generates `input/raw/dataset.parquet` from `dataset.csv`.
4. ✅ Downloads the 6 raw files from PRIDE (resumable via `curl -C -`; skips files already present at full size).

The snakemake invocation lives in **`tests/integration/WU346549/run.sh`**
(`./run.sh` = dry-run; `./run.sh run` = execute). Only the sources
(`setup_integration_test.py`, `run.sh`, `tree.txt`, `fixtures/`) are committed —
a local `.gitignore` ignores all downloaded/generated content.

> Note: the original generic argument-driven sketch (`--raw-url`, `--params-yml`,
> …) was superseded by the simpler zero-arg case, per the requirement that
> `./setup_integration_test.py` run with no parameters.

## Acceptance Criteria

The integration test passes when, from a clean `WU346549/`:

1. ✅ `./setup_integration_test.py` builds the input tree; `diann-snakemake -n` produces a complete, valid DAG. *(Done on dev box.)*
2. ⬜ `./run.sh run` completes with exit code 0 and all these output files exist *(pending live run on Linux)*:
   - `out-DIANN_libA/WU346549_report-lib.predicted.speclib`
   - `out-DIANN_quantB/WU346549_report.parquet`
   - `out-DIANN_quantB/WU346549_report_prozor.parquet` *(quantB, since `enable_step_c=false`)*
   - `Result_WU346549.zip`
   - `outputs.yml`
3. ⬜ `Result_WU346549.zip` contains the expected QC PDF and prozor parquet.
4. ✅ Generated `step_*.sh` scripts / container commands carry `--runtime <detected>` matching the host's `detect_runtime()`. *(Dry-run confirms `--runtime docker`.)*

## Cross-Runtime Verification

Run the same case on two hosts:

| Host | Expected `detect_runtime()` | Verifies | Status |
|---|---|---|---|
| Dev machine (docker) | `docker` | Docker path; backwards compatibility | ✅ DAG dry-run passed (M1, amd64 emulation for a live run) |
| fgcz-c-043 (apptainer) | `apptainer` | New apptainer path; SIF builds; Wine compat for msconvert | ⬜ pending |

Compare:

- The DIA-NN `.config.json` files (modulo paths) — should be byte-identical.
- The `Result_WU{id}.zip` parquet contents — should match within numerical tolerance (DIA-NN can have non-determinism at very low levels).
- The prozor parquet — protein groups should match exactly.

## Open Questions — RESOLVED

1. ✅ **Where do the raw files live?** PRIDE / ProteomeXchange **PXD028735**, six `.raw` files. URLs hardcoded in `setup_integration_test.py` (also mirrored at `https://proteobench.cubimed.rub.de/raws/DIA/`). Verified all 6 return HTTP 200.
2. ✅ **License / hardcode the URL?** ProteoBench is a public benchmark; URLs are hardcoded in the (committed) setup script, raws/FASTA are downloaded, not committed.
3. ⬜ **CI integration?** Not wired yet. A full run is ~hours + 9.2 GB; suited to nightly/on-demand, not per-PR. The cheap DAG dry-run (with placeholder raws) is a fast per-PR-able smoke check if desired.
4. ◐ **Disk + time budget.** Full run is large/slow; the DAG dry-run is seconds. A future "smoke" mode (Step A only / single raw) could trim this.

> ⚠️ **FASTA caveat:** the ProteoBench public FASTA (16,670,994 B) differs by ~250 KB from the FGCZ production copy (16,920,220 B) — same triple-proteome content, marginally different contaminant set. Fine for an end-to-end *run*; **not** bit-exact reproduction of the WU346549 reference run. For bit-exact diffs, host the FGCZ FASTA somewhere downloadable.

## Next Steps

1. ✅ Input artifacts provided (committed fixtures + download URLs).
2. ✅ Raw-data download wired (PRIDE PXD028735) + FASTA download (ProteoBench).
3. ✅ `setup_integration_test.py` implemented (zero-arg) + `run.sh`.
4. ✅ Validated on dev machine via DAG dry-run (docker).
5. ⬜ Run live on a Linux docker box; capture outputs; check acceptance criteria.
6. ⬜ Run on fgcz-c-043 (apptainer) after SIFs are populated via `deploy.smk all_sif --config sif_builder=native`.
7. ⬜ Diff outputs across the two runs. File any discrepancies as separate TODOs.

---

## Run Instructions (Linux box)

Everything needed to run the WU346549 integration test end-to-end. The work dir
**is** `tests/integration/WU346549/` — run from there.

### 0. Get the code + install the package

```bash
git clone https://github.com/wolski/diann-runner.git    # or: git pull
cd diann-runner
uv venv && source .venv/bin/activate
uv pip install -e .
```

### 1. Build the input tree (downloads FASTA + 9.2 GB raws; resumable)

```bash
cd tests/integration/WU346549
./setup_integration_test.py
```

This stages the fixtures, downloads the ProteoBench FASTA (saved as
`input/p34486_Proteobench_TripleProteome_20240614.fasta`), generates
`input/raw/dataset.parquet`, and downloads the 6 PRIDE PXD028735 `.raw` files.
Safe to re-run — it skips anything already present at full size.

### 2a. Docker host (e.g. fgcz-r-029 / a docker dev box)

`detect_runtime()` returns `docker` automatically. The DIA-NN / thermoraw /
prolfqua images must be available to docker (built locally from `docker/` or via
`snakemake -s deploy.smk --cores 1`; they are **not** on Docker Hub).

```bash
./run.sh            # dry-run: prints the DAG, executes nothing
./run.sh run        # execute the full workflow
CORES=64 ./run.sh run
```

### 2b. Apptainer host (fgcz-c-043 / c-050, runs as trxcopy)

`detect_runtime()` returns `apptainer` (it wins when both are installed). The
workflow reads the SIF image **paths** from the deploy config
(`src/diann_runner/config/defaults_{local,server}.yml` → `images.apptainer`),
which currently point at `/misc/fgcz01/nextflow_apptainer_cache/*.sif`. There is
no env var — the SIFs must exist at those paths (or edit the config / build them
there).

```bash
# one-time: build the SIFs at the paths defaults_*.yml expects.
# native builder needs apptainer only (no docker); use sif_builder=docker on a
# docker-capable host to convert locally-built images instead.
snakemake -s deploy.smk all_sif \
    --config sif_builder=native sif_output_dir=/misc/fgcz01/nextflow_apptainer_cache

cd tests/integration/WU346549
./setup_integration_test.py
./run.sh run
```

If you build SIFs elsewhere, point the config there (e.g. edit
`images.apptainer` in `defaults_*.yml`, or rebuild with a matching
`sif_output_dir`). See `TODO/TODO_add_aptainer_compatibility.md` for runtime
details.

### 3. Acceptance check

After `./run.sh run`, confirm (workunit 346549, `enable_step_c=false` → outputs in `out-DIANN_quantB/`):

```bash
ls -la out-DIANN_libA/WU346549_report-lib.predicted.speclib \
       out-DIANN_quantB/WU346549_report.parquet \
       out-DIANN_quantB/WU346549_report_prozor.parquet \
       Result_WU346549.zip outputs.yml
unzip -l Result_WU346549.zip      # expect report.tsv, pr/pg_matrix.tsv, QC pdf, prozor parquet
```

### 4. Cross-runtime diff (docker vs apptainer)

Run steps 1–3 on both a docker host and fgcz-c-043, then compare:

- `out-DIANN_*/WU346549_*.config.json` — byte-identical (modulo absolute paths).
- `Result_WU346549.zip` parquet contents — equal within numerical tolerance.
- `*_report_prozor.parquet` — protein groups identical.

### Notes

- The DIA-NN image is `linux/amd64`. On Apple Silicon it runs under emulation
  (slow); prefer a real x86-64 Linux host for the live run. Apptainer is
  Linux-only — there is no useful M1 path for the apptainer leg.
- Raw files keep their exact PRIDE names (ProteoBench requirement — do not rename).
