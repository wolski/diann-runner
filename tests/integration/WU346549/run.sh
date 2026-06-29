#!/usr/bin/env bash
# Run the DIA-NN 3-step workflow for the WU346549 integration test, via either
# entry point.
#
# Prerequisite: ./setup_integration_test.py  (downloads the FASTA + 6 raw files
# and builds the input/ tree in this directory).
#
# Usage:
#   ./run.sh                  # dry-run via diann-snakemake (default)
#   ./run.sh run              # execute via diann-snakemake
#   ./run.sh apprunner        # dry-run via `run-diann apprunner`
#   ./run.sh apprunner run    # execute via `run-diann apprunner`
#   CORES=64 ./run.sh ...
#
# Both entry points read the SAME committed inputs (params.yml +
# input/raw/dataset.parquet). `run-diann apprunner` additionally exercises the
# params.yml -> DIANNRunnerParams (TOML) and dataset.parquet -> dataset.csv
# normalization that the bare diann-snakemake passthrough skips.
#
# diann-snakemake / run-diann auto-detect the container runtime (apptainer wins
# over docker when both are present), so the same commands work on the docker
# dev box and on the apptainer host (fgcz-c-043).
set -euo pipefail
cd "$(dirname "$0")"

CORES="${CORES:-32}"
MODE="${1:-dry}"

case "$MODE" in
  run)   # back-compat: full run via diann-snakemake
    diann-snakemake --cores "$CORES" -p all
    ;;
  dry)
    echo "Dry-run via diann-snakemake (pass 'run' to execute):"
    diann-snakemake --cores "$CORES" -p -n all
    ;;
  apprunner)
    # FASTA as staged by setup_integration_test.py:
    # input/<basename of params.yml's input_fasta_databases>.
    db=$(awk -F': *' '/input_fasta_databases/{print $2; exit}' params.yml)
    args=(apprunner
      --raw-dir input/raw
      --dataset input/raw/dataset.parquet
      --params params.yml
      --fasta "input/$(basename "$db")"
      --work-dir . --output-dir . --cores "$CORES")
    if [ "${2:-}" = run ]; then
      run-diann "${args[@]}"
    else
      echo "Dry-run via run-diann apprunner (pass 'apprunner run' to execute):"
      run-diann "${args[@]}" -n
      # apprunner normalizes params.yml -> diann_runner_params.toml + dataset.csv
      # in place; remove them so a later './run.sh' (diann-snakemake) reads
      # params.yml again instead of the leftover TOML (Snakefile is dual-mode).
      rm -f diann_runner_params.toml dataset.csv
    fi
    ;;
  *)
    echo "usage: $0 [dry|run|apprunner [run]]" >&2
    exit 2
    ;;
esac
