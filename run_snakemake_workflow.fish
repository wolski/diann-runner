#!/usr/bin/env fish

# Script to run DIA-NN workflow from current directory
# Usage: cd /path/to/your/data && /path/to/diann-runner/run_workflow.fish [--no-cleanup] [--cores N]
#
# Requirements:
#   - Current directory must contain .raw files (or .mzML or .d.zip)
#   - params.yml must exist in current directory with correct configuration
#   - dataset.csv will be auto-generated if missing

# Get the directory where this script is located
set SCRIPT_DIR (dirname (status --current-filename))

# Configuration - paths relative to script location
set SNAKEFILE $SCRIPT_DIR/Snakefile.DIANN3step
set VENV_PATH $SCRIPT_DIR/.venv
set PARAMS_TEMPLATE $SCRIPT_DIR/example_params_yaml/params.yml

# Work in current directory
set WORK_DIR (pwd)

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
echo "DIA-NN Workflow Runner"
echo "=========================================="
echo "Working directory: $WORK_DIR"
echo "Snakefile: $SNAKEFILE"
echo "Cores: $CORES"
echo ""

# Generate dataset.csv if it doesn't exist
if not test -f $WORK_DIR/dataset.csv
    echo "Generating dataset.csv from .raw files..."

    # Detect file type
    set raw_files $WORK_DIR/*.raw
    set mzml_files $WORK_DIR/*.mzML
    set dzip_files $WORK_DIR/*.d.zip

    # Create CSV with header and all files
    echo "raw.file,name,Group" > $WORK_DIR/dataset.csv

    if test -e $raw_files[1]
        for rawfile in $raw_files
            set basename (basename $rawfile .raw)
            echo "$basename,$basename,sample" >> $WORK_DIR/dataset.csv
        end
    else if test -e $mzml_files[1]
        for mzmlfile in $mzml_files
            set basename (basename $mzmlfile .mzML)
            echo "$basename,$basename,sample" >> $WORK_DIR/dataset.csv
        end
    else if test -e $dzip_files[1]
        for dzipfile in $dzip_files
            set basename (basename $dzipfile .d.zip)
            echo "$basename,$basename,sample" >> $WORK_DIR/dataset.csv
        end
    else
        echo "✗ Error: No .raw, .mzML, or .d.zip files found in $WORK_DIR"
        exit 1
    end

    set file_count (math (wc -l < $WORK_DIR/dataset.csv) - 1)
    echo "✓ dataset.csv generated with $file_count files"
else
    echo "ℹ  dataset.csv already exists, using existing file"
end
echo ""

# Check that params.yml exists
if not test -f $WORK_DIR/params.yml
    echo "✗ Error: params.yml not found in $WORK_DIR"
    echo ""
    echo "Please create params.yml with your configuration."
    echo "You can copy the template from:"
    echo "  $PARAMS_TEMPLATE"
    echo ""
    echo "Make sure to configure:"
    echo "  - registration/workunit_id"
    echo "  - params/fasta/database_path"
    echo "  - params/diann/threads"
    echo "  - params/diann/is_dda (true for DDA, false for DIA)"
    exit 1
else
    echo "ℹ  Using params.yml from $WORK_DIR"
end
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

# Check exit status using pipestatus to get snakemake's exit code
set workflow_status $pipestatus[1]
if test $workflow_status -eq 0
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
    echo "Exit code: $workflow_status"
    exit 1
end
