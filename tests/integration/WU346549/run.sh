#!/usr/bin/env bash
# Run the DIA-NN 3-step workflow for the WU346549 integration test.
#
# Prerequisite: ./setup_integration_test.py  (downloads the FASTA + 6 raw files
# and builds the input/ tree in this directory).
#
# Usage:
#   ./run.sh            # dry-run (default) — shows the plan without executing
#   ./run.sh run        # actually execute the workflow
#   CORES=64 ./run.sh run
#
# diann-snakemake auto-detects the container runtime (apptainer wins over docker
# when both are present), so the same command works on the docker dev box and on
# the apptainer host (fgcz-c-043).
set -euo pipefail
cd "$(dirname "$0")"

CORES="${CORES:-32}"
MODE="${1:-dry}"

if [[ "$MODE" == "run" ]]; then
  diann-snakemake --cores "$CORES" -p all
else
  echo "Dry-run (pass 'run' to execute):"
  diann-snakemake --cores "$CORES" -p -n all
fi
