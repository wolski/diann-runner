# TODO: Integration Test (end-to-end Snakemake run from real bfabric inputs)

## Goal

Validate the full `Snakefile.DIANN3step.smk` workflow end-to-end against a known input: a [ProteoBench](https://proteobench.cubimed.rub.de/) dataset previously run through the bfabric production app. Reusing the real `params.yml` + `dataset.csv` from that bfabric run means every parameter parser, every Bfabric flat-key mapping, and every workflow stage gets exercised with production-shaped inputs — not synthetic ones.

This is the test we'll use to:

1. Catch regressions in `parse_flat_params()` / `create_diann_workflow()` / `load_deploy_config()`.
2. Smoke-verify the Docker runtime path on dev machines (CI-shaped).
3. Smoke-verify the Apptainer runtime path on the apptainer host (fgcz-c-043).
4. Confirm the new `container_runtime` flag flow doesn't break anything between Snakefile, wrappers, and `DiannWorkflow`.

## Inputs (to be provided)

The user (Witek) will produce these from a real bfabric run:

- [ ] `params.yml` — flat-key Bfabric parameters (what the GUI generates).
- [ ] `dataset.csv` — sample-to-condition mapping.
- [ ] `dataset.parquet` — same content as `dataset.csv` but parquet-formatted (the Snakefile's `dataset_csv` rule converts parquet → csv, so this is the upstream input).
- [ ] Download URL for the raw spectrometry files (likely `.raw` or `.d.zip`, ProteoBench is typically Thermo `.raw`).
- [ ] Expected workunit ID + container ID (Bfabric `registration` block in `params.yml`).
- [ ] FASTA database path / URL (referenced by `params.yml.03_fasta_database_path`).

## Folder Layout the Workflow Expects

From [Snakefile.DIANN3step.smk:38-47](../src/diann_runner/Snakefile.DIANN3step.smk#L38) and [snakemake_helpers.py](../src/diann_runner/snakemake_helpers.py):

```
<work_dir>/
├── params.yml                   # Bfabric flat-key params + registration block
├── input/
│   ├── <fasta>.fasta            # Database, resolved by resolve_fasta_path()
│   └── raw/
│       ├── dataset.parquet      # → converted to dataset.csv by rule dataset_csv
│       ├── sample1.raw          # or .d.zip / .mzML
│       ├── sample2.raw
│       └── ...
└── (Snakemake-generated outputs go here)
```

## Driver Script

A small Python script — proposed location: `tests/integration/setup_integration_test.py` — that:

1. Accepts a target work directory (e.g. `--work-dir /tmp/diann_integration`).
2. Downloads the raw files from the provided URL into `<work_dir>/input/raw/`.
3. Drops `params.yml` at `<work_dir>/params.yml`.
4. Drops `dataset.parquet` at `<work_dir>/input/raw/dataset.parquet`.
5. Copies the FASTA into `<work_dir>/input/`.
6. Optionally invokes `diann-snakemake --cores N -p all` (or just prints the command).
7. Runs `diann-snakemake -n` (dry-run) by default; `--run` actually executes.

Sketch:

```python
# tests/integration/setup_integration_test.py
import argparse, shutil, subprocess
from pathlib import Path
from urllib.request import urlretrieve

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--work-dir", required=True, type=Path)
    p.add_argument("--raw-url", required=True, help="URL of raw archive (.zip/.tar)")
    p.add_argument("--params-yml", required=True, type=Path)
    p.add_argument("--dataset-parquet", required=True, type=Path)
    p.add_argument("--fasta", required=True, type=Path)
    p.add_argument("--runtime", choices=("docker", "apptainer"), default="docker",
                   help="Sanity-check expectation; informational only — detection is automatic.")
    p.add_argument("--cores", type=int, default=8)
    p.add_argument("--run", action="store_true", help="Actually execute, not just dry-run.")
    args = p.parse_args()

    raw_dir = args.work_dir / "input" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # 1. download + extract raw files
    archive = raw_dir / Path(args.raw_url).name
    urlretrieve(args.raw_url, archive)
    if archive.suffix == ".zip":
        subprocess.run(["unzip", "-o", str(archive), "-d", str(raw_dir)], check=True)
    # (handle .tar / .tar.gz analogously)

    # 2-4. drop in metadata
    shutil.copy(args.params_yml, args.work_dir / "params.yml")
    shutil.copy(args.dataset_parquet, raw_dir / "dataset.parquet")
    shutil.copy(args.fasta, args.work_dir / "input" / args.fasta.name)

    # 5. run snakemake
    cmd = ["diann-snakemake", "--cores", str(args.cores), "all"]
    if not args.run:
        cmd.append("-n")
    return subprocess.run(cmd, cwd=args.work_dir).returncode
```

## Acceptance Criteria

The integration test passes when, from a clean `<work_dir>`:

1. `setup_integration_test.py --run` completes with exit code 0.
2. All these output files exist:
   - `<work_dir>/out-DIANN_libA/WU{id}_report-lib.predicted.speclib`
   - `<work_dir>/out-DIANN_quantB/WU{id}_report.parquet`
   - `<work_dir>/out-DIANN_quantC/WU{id}_report.parquet` (if `enable_step_c=True`)
   - `<work_dir>/out-DIANN_quantC/WU{id}_report_prozor.parquet`
   - `<work_dir>/Result_WU{id}.zip`
   - `<work_dir>/outputs.yml`
3. `Result_WU{id}.zip` contains the expected QC PDF and prozor parquet.
4. Generated `step_*.sh` scripts contain `--runtime <expected_runtime>` matching the host's `detect_runtime()` result.

## Cross-Runtime Verification

Run the same test on two hosts:

| Host | Expected `detect_runtime()` | Verifies |
|---|---|---|
| Dev machine (docker) | `docker` | Docker path; backwards compatibility |
| fgcz-c-043 (apptainer) | `apptainer` | New apptainer path; SIF builds; Wine compat for msconvert |

Compare:

- The DIA-NN `.config.json` files (modulo paths) — should be byte-identical.
- The `Result_WU{id}.zip` parquet contents — should match within numerical tolerance (DIA-NN can have non-determinism at very low levels).
- The prozor parquet — protein groups should match exactly.

## Open Questions

1. **Where do the raw files live?** ProteoBench publishes via Zenodo / their own host. Need a stable URL or a procedure for fetching.
2. **License of the dataset?** Should the driver script ship the URL hardcoded, or only accept it as an argument?
3. **CI integration?** Run on every PR (slow but thorough) or only nightly / on-demand?
4. **Disk + time budget.** A real DIA-NN run on ProteoBench is ~30+ minutes per stage. Acceptable for nightly CI; too slow for per-PR. Maybe a "smoke" mode that runs only Step A (library prediction, no raw files) plus a single-raw-file Step B?

## Next Steps

1. Witek provides the input artifacts listed above.
2. Witek shares the raw-data download URL.
3. Implement `setup_integration_test.py` per the sketch.
4. Run it on dev machine (docker). Capture outputs.
5. Run it on fgcz-c-043 (apptainer) after SIFs are populated via `deploy.smk all_sif --config sif_builder=native`.
6. Diff outputs across the two runs. File any discrepancies as separate TODOs.
