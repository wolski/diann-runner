#!/usr/bin/env fish

# Script to run DIA-NN workflow on plasma DDA data
# Usage: ./run_plasma_workflow.fish [--no-cleanup] [--cores N]

# Configuration
set WORK_DIR /scratch/wolski/plasma_DDA_40148
set SNAKEFILE /scratch/wolski/diann-runner/Snakefile.DIANN3step
set VENV_PATH /scratch/wolski/diann-runner/.venv
set PARAMS_TEMPLATE /scratch/wolski/diann-runner/example_params_yaml/params.yml

# Parse arguments
set SKIP_CLEANUP false
set CORES 8

for arg in $argv
    switch $arg
        case "--no-cleanup" "--skip-cleanup"
            set SKIP_CLEANUP true
        case "--cores"
            set CORES $argv[2]
            set argv $argv[3..-1]
        case "--cores=*"
            set CORES (string split "=" $arg)[2]
    end
end

echo "=========================================="
echo "DIA-NN Plasma Workflow"
echo "=========================================="
echo "Working directory: $WORK_DIR"
echo "Snakefile: $SNAKEFILE"
echo "Cores: $CORES"
echo ""

# Copy and customize params.yml if it doesn't exist
if not test -f $WORK_DIR/params.yml
    echo "Copying params.yml template..."
    cp $PARAMS_TEMPLATE $WORK_DIR/params.yml

    echo "Customizing params.yml for plasma data..."
    # Update workunit_id and FASTA path
    sed -i 's/workunit_id: "12345"/workunit_id: "40148"/' $WORK_DIR/params.yml
    sed -i 's/database_path: "ProteoBenchFASTA_MixedSpecies_HYE.fasta"/database_path: "fgcz_10116_1spg_rat_20240418.fasta"/' $WORK_DIR/params.yml
    sed -i 's/threads: 12/threads: 32/' $WORK_DIR/params.yml

    echo "✓ params.yml created and customized"
else
    echo "ℹ  params.yml already exists, using existing file"
end
echo ""

# Change to work directory
cd $WORK_DIR
echo "Changed to work directory: $WORK_DIR"
echo ""

# Cleanup before running (unless skipped)
if test $SKIP_CLEANUP = false
    echo "Cleaning up previous run..."
    source $VENV_PATH/bin/activate.fish && diann-cleanup
    echo "✓ Cleanup complete"
else
    echo "⊘ Skipping cleanup (continuing from previous run)..."
end
echo ""

# Run workflow
echo "=========================================="
echo "Starting Snakemake workflow..."
echo "=========================================="
source $VENV_PATH/bin/activate.fish && \
    snakemake -s $SNAKEFILE --cores $CORES all 2>&1 | tee workflow.log

# Check exit status
if test $status -eq 0
    echo ""
    echo "=========================================="
    echo "✓ Workflow completed successfully!"
    echo "=========================================="
    echo "Results in: $WORK_DIR"
else
    echo ""
    echo "=========================================="
    echo "✗ Workflow failed - check workflow.log"
    echo "=========================================="
    exit 1
end
