#!/usr/bin/env fish

# Parse arguments
set SKIP_CLEANUP false
if test "$argv[1]" = "--no-cleanup"; or test "$argv[1]" = "--skip-cleanup"
    set SKIP_CLEANUP true
end

# Setup: Create WU54321_work directory and copy test files (only if new)
if not test -d WU54321_work
    echo "Setting up WU54321_work directory..."
    mkdir -p WU54321_work

    # Copy test mzML files (2 DIA files from dataset2.csv)
    echo "Copying test data files..."
    cp data/dia_mzml/LFQ_Orbitrap_AIF_Condition_A_Sample_Alpha_01.mzML WU54321_work/
    cp data/dia_mzml/LFQ_Orbitrap_AIF_Condition_B_Sample_Alpha_01.mzML WU54321_work/

    # Copy dataset2.csv and FASTA
    cp data/dia_mzml/dataset2.csv WU54321_work/dataset.csv
    cp data/dda_mzml/ProteoBenchFASTA_MixedSpecies_HYE.fasta WU54321_work/

    # Copy params.yml from dia_mzml folder
    cp data/dia_mzml/params.yml WU54321_work/

    echo "Setup complete!"
else
    echo "WU54321_work directory already exists, skipping setup..."
end
echo ""

# Change to work directory
cd WU54321_work

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
