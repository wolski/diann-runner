# Integration test — ProteoBench DIA-Astral *entrapment* (no-digestion)

Exercises the **no-digestion** search mode (`lib_digestion_cut: no digestion` →
`--cut ''` + `--missed-cleavages 0`, prozor bypassed) end to end on the real
ProteoBench DIA-Astral human entrapment data. This is Part 2 of
[`../../../TODO/TODO_entrapment_support.md`](../../../TODO/TODO_entrapment_support.md)
packaged like [`../WU346549/`](../WU346549/).

The entrapment FASTA is **already digested** — every record is a single peptide
(`>sp|PSLDQLAAHPWMLGADGGVPESCDLR_target|...`) — so DIA-NN's in-silico digestion
must be off; each record is taken verbatim as a precursor candidate.

## Entry point

Driven by `run-diann sushi` — the readable-key CLI adapter with
`register_outputs=False` (no B-Fabric). This is **not** the SUSHI GUI; it is the
no-GUI CLI harness Part 2 calls for. (`apprunner` is not used here: it hardcodes
B-Fabric registration, which a benchmark must not do.)

## Parameters — version × mods, one folder per combo

The DIA-NN version and the variable-mods arm are exposed so the same data can be
re-run per version. Each combo is written to its own clearly-named folder:

```
runs/diann-<version>-<mods>/
  sushi_params.yml            # generated for this combo (version + mods vary)
  out-DIANN_libA/ quantB/     # DIA-NN outputs
  Result_WU<version>_<mods>.zip
```

| Variable | Values | Meaning |
|----------|--------|---------|
| `VERSION` | `2.3.2`, `2.5.0`, `2.5.1` | `pipeline_diann_version` (container image tag) |
| `MODS` | `metox`, `nomods` | Met-oxidation only, or no variable mods (both allowed by the brief) |
| `CORES` | int (default 32) | thread count |
| `RUNTIME` | `docker` (default), `apptainer` | container runtime (see Notes → *Runtime*) |

## Run

```bash
cd tests/integration/entrapment

./setup_integration_test.py           # download FASTA (~48 MB) + 6 raws (~21 GB)

make dry                              # dry-run one combo (VERSION=2.5.1 MODS=metox)
make run                              # execute that combo
make run VERSION=2.5.0 MODS=nomods    # a different combo
make sweep                            # every VERSIONS x MODS_ARMS combo
make sweep CORES=64 VERSIONS="2.5.1"  # narrow the matrix
```

Or drive `run.sh` directly: `VERSION=2.3.2 MODS=metox ./run.sh run`.

Everything for this case lives here (self-contained) — run it from this
directory, not the package root.

## What's committed vs generated

| Path | Status |
|------|--------|
| `setup_integration_test.py`, `run.sh`, `Makefile`, `README.md`, `input_dataset.tsv` | committed |
| `input/` (FASTA + `raw/*.raw`) | downloaded (gitignored) |
| `runs/` (per-combo work dirs + outputs) | generated (gitignored) |

`input_dataset.tsv` carries `Name` + `Thermo RAW [File]` (verbatim ProteoBench
filenames — do **not** rename) + a `Condition [Factor]` column (A/B).

## Notes

- **Runtime:** the harness defaults to `RUNTIME=docker` and passes `run-diann
  --docker`, so it uses the docker images built by `make deploy`. This is
  because `run-diann`'s CLI otherwise defaults to **apptainer**, which resolves
  DIA-NN to SIF images under the shared `/misc/fgcz01/nextflow_apptainer_cache/`
  — a cache that is not mounted on every FGCZ host (e.g. fgcz-r-038, where
  apptainer fails with `lstat /misc/fgcz01: no such file or directory`). Use
  `RUNTIME=apptainer` only on a node that mounts that cache.
- **Raw reading:** `pipeline_raw_converter: native` — DIA-NN reads the Thermo
  `.raw` directly (no msconvert), and the shared `input/raw` is mounted read-only
  into each combo's container, so the 6 raws are read in place, not re-copied or
  re-converted per combo.
- **Astral needs DIA-NN 2.x** and a Linux host with the container runtime + enough
  scratch for outputs; the ~21 GB raw set and the runs do not fit / run on the
  Apple-Silicon dev box.
- **ProteoBench submission** (convert each `Result_WU*/…report.parquet` to the
  DIA-NN module format, tabulate entrapment FDR per version × mods) is the
  remaining Part-2 step, done from the collected `runs/` outputs.
