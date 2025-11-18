#!/usr/bin/env fish

# Parse arguments
set SKIP_CLEANUP false
if test "$argv[1]" = "--no-cleanup"; or test "$argv[1]" = "--skip-cleanup"
    set SKIP_CLEANUP true
end

# Setup: Create WU12345_work directory and copy test files (only if new)
if not test -d WU12345_work
    echo "Setting up WU12345_work directory..."
    mkdir -p WU12345_work

    # Copy test mzML files (2 files from dataset.csv)
    echo "Copying test data files..."
    cp data/dda_mzml/LFQ_Orbitrap_DDA_Condition_A_Sample_Alpha_01.mzML WU12345_work/
    cp data/dda_mzml/LFQ_Orbitrap_DDA_Condition_B_Sample_Alpha_01.mzML WU12345_work/

    # Copy dataset.csv and FASTA
    cp data/dda_mzml/dataset.csv WU12345_work/
    cp data/dda_mzml/ProteoBenchFASTA_MixedSpecies_HYE.fasta WU12345_work/

    # Copy params.yml
    cp example_params_yaml/params.yml WU12345_work/

    echo "Setup complete!"
else
    echo "WU12345_work directory already exists, skipping setup..."
end
echo ""

# Change to work directory
cd WU12345_work

# Cleanup before running (unless skipped)
if test $SKIP_CLEANUP = false
    echo "Cleaning up previous run..."
    source ../.venv/bin/activate.fish && diann-cleanup
else
    echo "Skipping cleanup (continuing from previous run)..."
end

# Run workflow
echo "Running workflow..."
source ../.venv/bin/activate.fish && snakemake -s ../Snakefile.DIANN3step --cores 8 all 2>&1 | tee workflow.log
