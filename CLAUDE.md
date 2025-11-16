# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a Python package for running DIA-NN (mass spectrometry data analysis) workflows. It provides:
- A Docker wrapper (`diann-docker`) to run DIA-NN in containers
- A CLI tool (`diann-workflow`) to generate three-stage DIA-NN workflow scripts
- A Snakemake workflow for automated pipeline execution
- QC plotting utilities

The package uses `uv` for dependency management and `cyclopts` for CLI argument parsing.

## Development Commands

### Installation
```bash
cd diann_runner
uv venv
source .venv/bin/activate  # or `.venv/Scripts/activate` on Windows
uv pip install -e .

# For testing:
uv pip install -e ".[test]"
```

### Testing
```bash
# Run tests directly
python3 tests/test_workflow.py

# Or with pytest
python3 -m pytest tests/
```

### Docker Image
```bash
# Build the DIA-NN Docker image
docker build --platform linux/amd64 -f Dockerfile.diann -t diann:2.3.0 .

# Test the Docker wrapper
diann-docker --help
```

### Snakemake Workflow

**CRITICAL: Use run_workflow.sh for all testing**

When testing or running workflows, ALWAYS use the `run_workflow.sh` script:

```bash
# Run from the diann_runner directory
cd /path/to/diann_runner
bash run_workflow.sh
```

**Important workflow execution rules:**
- ALWAYS use `run_workflow.sh` - never run snakemake commands directly
- Run ONLY ONE workflow at a time - check for running processes first
- ALL workflow runs must log to `workflow.log` in the work directory
- The script automatically handles proper logging and cleanup
- Before starting a new run, ensure no other workflows are running:
  ```bash
  ps aux | grep -E "(snakemake|diann)" | grep -v grep
  ```

The script is located at `/Users/wolski/projects/slurmworker/config/A386_DIANN_23/diann_runner/run_workflow.sh` and handles:
- Proper working directory setup
- Consistent log file naming (`workflow.log`)
- Virtual environment activation
- Snakemake execution with correct parameters

**Do NOT:**
- Run snakemake commands directly from work directories
- Create multiple workflow log files with different names
- Run multiple workflows simultaneously
- Use different log files for each test run

## Architecture

### Three-Stage DIA-NN Workflow

The core architecture is built around DIA-NN's three-stage processing:

**Step A: Library Search** (`workflow.py:303-355`)
- Input: FASTA database only (no raw files)
- Uses deep learning predictor to generate predicted spectral library
- Outputs: `{workunit_id}_predicted.speclib` and `.config.json`

**Step B: Quantification with Refinement** (`workflow.py:357-436`)
- Input: Predicted library + raw/mzML files (can be a subset)
- Generates refined empirical library from actual data
- Optionally generates quantification matrices (controlled by `quantify` parameter)
- Uses `--reanalyse` for match-between-runs (MBR)
- Outputs: `{workunit_id}_refined.speclib` and `.config.json`

**Step C: Final Quantification** (`workflow.py:438-527`)
- Input: Refined library + raw/mzML files (can be different/larger set than Step B)
- Produces final quantification results
- Can reuse `.quant` files from Step B with `--use-quant` flag
- Outputs: Final TSV reports and matrices

### Configuration State Management

**Critical**: The workflow uses `.config.json` files to ensure parameter consistency across stages.

- Each stage saves a `.config.json` file alongside its output (e.g., `predicted.speclib.config.json`)
- Steps B and C load the config from the previous step to ensure all parameters (var_mods, threads, qvalue, etc.) remain consistent
- The CLI commands `quantification-refinement` and `final-quantification` require a `--config` parameter pointing to the previous step's config file
- This prevents common mistakes like changing modifications between stages

Implementation in `workflow.py`:
- `to_config_dict()` (line 149): Serializes all workflow parameters
- `save_config()` (line 181): Saves config JSON after each stage
- `from_config_file()` (line 204): Loads workflow from config

### Module Structure

**`workflow.py`** - Core workflow generation
- `DiannWorkflow` class: Manages all three stages with shared parameters
- `_build_common_params()`: Builds DIA-NN CLI arguments shared across stages
- `_write_shell_script()`: Generates executable bash scripts
- Each `generate_step_*()` method creates a bash script for that stage

**`cli.py`** - Command-line interface using cyclopts
- Commands: `library-search`, `quantification-refinement`, `final-quantification`, `all-stages`, `create-config`, `run-script`
- `_load_workflow_from_defaults()`: Loads workflow with config defaults + CLI overrides
- Command-line args always take precedence over config defaults

**`docker.py`** - Docker wrapper for DIA-NN
- Automatically detects Apple Silicon and uses `--platform linux/amd64`
- Mounts current directory to `/work` in container
- Preserves UID/GID on Unix systems for correct file permissions
- Environment variables: `DIANN_DOCKER_IMAGE`, `DIANN_PLATFORM`, `DIANN_EXTRA`

**`plotter.py`** - QC plotting utilities (referenced in Snakefile)

### Snakemake Workflow

The `Snakefile` orchestrates the complete pipeline:
1. File conversion (`.raw` → `.mzML` or `.d.zip` → `.d`)
2. DIA-NN execution (generates and runs bash script)
3. QC report generation
4. Results packaging and upload to bfabric

Key features:
- Reads configuration from `params.yml` in the working directory
- Dynamically detects input file types (`.raw` or `.d.zip`)
- Integrates with FGCZ infrastructure (bfabric, prolfqua)
- Uses Docker containers for msconvert and prolfqua

## Important Patterns

### File Management Policy

**NEVER use symlinks.** Always use direct file references. This project policy prohibits symlinks in all scenarios - they add unnecessary complexity and can cause issues with some tools.

### Flexible File Lists Between Stages

A key design feature is that Step B and Step C can use different file lists:

```python
# Fast library building: use subset in B, all files in C
workflow.generate_all_scripts(
    fasta_path='/path/to/db.fasta',
    raw_files_step_b=['pilot1.mzML', 'pilot2.mzML'],  # 2 files for fast library
    raw_files_step_c=['s1.mzML', ..., 's50.mzML'],    # All 50 files for quantification
    quantify_step_b=False  # Skip quantification in B, only build library
)
```

This pattern is used when:
- You have many files (50+) and want fast library building
- Building library from representative samples, then quantifying everything
- Running pilot → production workflows

### Variable Modifications Format

Variable modifications use tuples of (unimod_id, mass_delta, residues):

```python
var_mods = [
    ('35', '15.994915', 'M'),      # Oxidation (Met)
    ('4', '57.021464', 'C'),       # Carbamidomethyl (Cys)
    ('21', '79.966331', 'STY'),    # Phospho (Ser/Thr/Tyr)
]
```

### Default Binary: Docker Wrapper

By default, all workflow scripts use `diann-docker` as the DIA-NN binary. Override with:
- `--diann-bin` CLI flag
- `"diann_bin"` in config JSON
- `diann_bin` parameter in DiannWorkflow constructor

## Key Output Files

```
out-DIANN_libA/
  └── WU{id}_predicted.speclib         # Step A: Predicted library
      WU{id}_predicted.speclib.config.json

out-DIANN_quantB/
  ├── WU{id}_refined.speclib           # Step B: Refined library
  ├── WU{id}_refined.speclib.config.json
  ├── WU{id}_reportB.tsv               # Optional quantification
  └── WU{id}_reportB.pg_matrix.tsv

out-DIANN_quantC/
  ├── WU{id}_reportC.tsv               # ★ Main results
  ├── WU{id}_reportC.pg_matrix.tsv     # ★ Protein matrix
  ├── WU{id}_reportC.pr_matrix.tsv     # Precursor matrix
  └── WU{id}_final.speclib
```

## Common Workflows

### Standard: Same files for B and C
```bash
diann-workflow all-stages \
  --fasta /path/to/db.fasta \
  --raw-files sample*.mzML \
  --workunit-id WU123 \
  --var-mods "35,15.994915,M"
```

### Fast: Subset library building
```bash
# Step A: Library search
diann-workflow library-search \
  --fasta db.fasta \
  --workunit-id WU123 \
  --var-mods "35,15.994915,M"

# Step B: Fast library refinement (subset, no quantification)
diann-workflow quantification-refinement \
  --config out-DIANN_libA/WU123_predicted.speclib.config.json \
  --predicted-lib out-DIANN_libA/WU123_predicted.speclib \
  --raw-files pilot1.mzML pilot2.mzML

# Step C: Full quantification (all files)
diann-workflow final-quantification \
  --config out-DIANN_quantB/WU123_refined.speclib.config.json \
  --refined-lib out-DIANN_quantB/WU123_refined.speclib \
  --raw-files sample*.mzML
```

### With config defaults
```bash
# Create reusable config
diann-workflow create-config \
  --output my_defaults.json \
  --workunit-id WU123 \
  --var-mods "35,15.994915,M" \
  --threads 32

# Use config (CLI args override defaults)
diann-workflow all-stages \
  --config-defaults my_defaults.json \
  --fasta db.fasta \
  --raw-files sample*.mzML
```

## Testing Notes

- Tests are in `tests/` directory
- `test_workflow.py` tests the DiannWorkflow class
- `test_cli.py` tests CLI commands
- Run tests before committing changes to workflow generation logic
