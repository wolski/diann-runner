#!/usr/bin/env fish

# Setup test directory for DDA workflow testing
# Run from diann_runner root: ./data/dda_mzml/setup_test_run.fish

set WORK_DIR WU12345_work
set DATA_DIR (dirname (status --current-filename))

if not test -d $WORK_DIR
    echo "Setting up $WORK_DIR directory for DDA testing..."
    mkdir -p $WORK_DIR

    # Copy test mzML files (2 DDA files)
    echo "Copying test data files..."
    cp $DATA_DIR/LFQ_Orbitrap_DDA_Condition_A_Sample_Alpha_01.mzML $WORK_DIR/
    cp $DATA_DIR/LFQ_Orbitrap_DDA_Condition_B_Sample_Alpha_01.mzML $WORK_DIR/

    # Copy dataset.csv, FASTA, and params.yml
    cp $DATA_DIR/dataset.csv $WORK_DIR/
    cp $DATA_DIR/ProteoBenchFASTA_MixedSpecies_HYE.fasta $WORK_DIR/
    cp $DATA_DIR/params.yml $WORK_DIR/

    echo "✓ Setup complete!"
    echo ""
    echo "To run the workflow:"
    echo "  cd $WORK_DIR && ../run_snakemake_workflow.fish --cores 8"
else
    echo "✓ $WORK_DIR already exists"
    echo ""
    echo "To run the workflow:"
    echo "  cd $WORK_DIR && ../run_snakemake_workflow.fish --cores 8"
end
