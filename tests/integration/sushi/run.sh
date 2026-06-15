#!/usr/bin/env bash
# Integration test for the `run-diann sushi` CLI entry point.
#
# Unlike WU346549/ (AppRunner native inputs, downloads ~9 GB of real raws),
# this case is fully committed and CI-able: it drives `run-diann sushi` with
# the SUSHI-native input shapes a real SUSHI job produces —
#   - sushi_params.yml   (readable-key param mapping EzAppDiann dumps)
#   - input_dataset.tsv  (Name + 'Thermo RAW [File]' + factors)
# plus a tiny committed FASTA and runtime-created stub raw files. No gstore,
# no containers, no DIA-NN execution.
#
#   ./run.sh        # dry-run (default) — exercises the sushi adapter + DAG build
#   ./run.sh run    # actually execute (needs containers + real raws — not CI)
#   CORES=64 ./run.sh run
set -euo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"
CORES="${CORES:-8}"
MODE="${1:-dry}"

# Stub raw files the dataset references — a dry-run only needs them to EXIST
# (validate_request + the Snakefile's detect_input_files glob); contents are
# irrelevant. Gitignored, recreated here on every run.
tail -n +2 input_dataset.tsv | cut -f2 | while read -r rel; do
  [ -n "$rel" ] || continue
  mkdir -p "$(dirname "$rel")"
  : > "$rel"
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --data-root overrides sushi_params.yml's production dataRoot so the dataset's
# relative 'Thermo RAW [File]' paths resolve against THIS fixture; the sushi
# adapter derives the raw dir from them and pulls the FASTA from fasta_databases.
ARGS=(sushi
  --params sushi_params.yml
  --dataset input_dataset.tsv
  --data-root "$HERE"
  --work-dir "$WORK" --output-dir "$WORK"
  --cores "$CORES")
[ "$MODE" = run ] || ARGS+=(-n)

echo "run-diann ${ARGS[*]}"
run-diann "${ARGS[@]}"
