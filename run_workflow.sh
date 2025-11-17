#!/bin/bash
set -e

# Parse arguments
SKIP_CLEANUP=false
if [[ "$1" == "--no-cleanup" ]] || [[ "$1" == "--skip-cleanup" ]]; then
    SKIP_CLEANUP=true
fi

# Change to work directory
cd WU12345_work

# Cleanup before running (unless skipped)
if [[ "$SKIP_CLEANUP" == "false" ]]; then
    echo "Cleaning up previous run..."
    fish -c "source ../.venv/bin/activate.fish && diann-cleanup"
else
    echo "Skipping cleanup (continuing from previous run)..."
fi

# Run workflow
echo "Running workflow..."
fish -c "source ../.venv/bin/activate.fish && snakemake -s ../Snakefile.DIANN3step --cores 8 all" 2>&1 | tee workflow.log
