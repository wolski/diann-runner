#!/usr/bin/env bash
# Integration test for the `run-diann sushi` CLI entry point.
#
# Reuses the WU346549 fixture's real downloaded inputs (run `make setup` in
# ../WU346549/ first — ~9 GB):
#   - sushi_params.yml   readable-key param mapping EzAppDiann dumps;
#                        fasta_databases -> ../WU346549/input/<db>.fasta
#   - input_dataset.tsv  Name + 'Thermo RAW [File]' -> ../WU346549/input/raw/*.raw + factors
#
#   ./run.sh        # dry-run (default): sushi adapter + Snakemake DAG build
#   ./run.sh run    # execute the full workflow (needs containers + the raws)
#   CORES=64 ./run.sh run
set -euo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"
CORES="${CORES:-8}"
MODE="${1:-dry}"

# --data-root (absolute) resolves the dataset's '../WU346549/...' raw paths; the
# sushi adapter derives the single raw dir from them and pulls the FASTA from
# fasta_databases. Outputs land here (gitignored) — SUSHI itself delivers via
# g-req, so register_outputs=False.
ARGS=(sushi
  --params sushi_params.yml
  --dataset input_dataset.tsv
  --data-root "$HERE"
  --work-dir . --output-dir .
  --cores "$CORES")
[ "$MODE" = run ] || ARGS+=(-n)

echo "run-diann ${ARGS[*]}"
run-diann "${ARGS[@]}"

# Dry-run materializes diann_runner_params.toml + dataset.csv in place; drop them
# so a later run doesn't read stale artifacts.
[ "$MODE" = run ] || rm -f diann_runner_params.toml dataset.csv
