#!/usr/bin/env fish

# Setup test directory for DIA workflow testing
# Run from diann_runner root: ./data/dia_mzml/setup_test_run.fish

set WORK_DIR WU54321_work
set DATA_DIR (dirname (status --current-filename))

if not test -d $WORK_DIR
    echo "Setting up $WORK_DIR directory for DIA testing..."
    mkdir -p $WORK_DIR

    # Copy test mzML files (2 DIA files from dataset2.csv)
    echo "Copying test data files..."
    cp $DATA_DIR/LFQ_Orbitrap_AIF_Condition_A_Sample_Alpha_01.mzML $WORK_DIR/
    cp $DATA_DIR/LFQ_Orbitrap_AIF_Condition_B_Sample_Alpha_01.mzML $WORK_DIR/

    # Copy dataset2.csv (as dataset.csv), FASTA, and params.yml
    cp $DATA_DIR/dataset2.csv $WORK_DIR/dataset.csv
    cp ../dda_mzml/ProteoBenchFASTA_MixedSpecies_HYE.fasta $WORK_DIR/
    cp $DATA_DIR/params.yml $WORK_DIR/

    echo "✓ Setup complete!"
    echo ""
    echo "To run the workflow:"
    echo "  cd $WORK_DIR && diann-snakemake --cores 8 -p all"
else
    echo "✓ $WORK_DIR already exists"
    echo ""
    echo "To run the workflow:"
    echo "  cd $WORK_DIR && diann-snakemake --cores 8 -p all"
end
