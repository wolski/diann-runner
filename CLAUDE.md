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

**Unit Tests:**
```bash
# Run tests directly
python3 tests/test_workflow.py

# Or with pytest
python3 -m pytest tests/
```

**CRITICAL: Use run_workflow.sh for all Snakemake workflow testing**

When testing or running the complete Snakemake workflow, ALWAYS use the `run_workflow.sh` script:

```bash
# Run from the diann_runner directory
bash run_workflow.sh

# To skip cleanup and continue from previous run:
bash run_workflow.sh --no-cleanup
```

The `run_workflow.sh` script:
1. Changes to the `WU12345_work` directory
2. Runs `diann-cleanup` to remove previous outputs (unless `--no-cleanup` is specified)
3. Activates the virtual environment (`.venv`)
4. Executes `snakemake -s ../Snakefile.DIANN3step --cores 8 all`
5. Logs all output to `workflow.log` for troubleshooting

**Important workflow execution rules:**
- NEVER run snakemake commands directly - always use `run_workflow.sh`
- The script ensures consistent logging, cleanup, and environment activation
- Use `--no-cleanup` flag to resume from a partially completed run

### Docker Image
```bash
# Build the DIA-NN Docker image
docker build --platform linux/amd64 -f Dockerfile.diann -t diann:2.3.0 .

# Test the Docker wrapper
diann-docker --help
```


## Architecture

### Three-Stage DIA-NN Workflow

The core architecture is built around DIA-NN's three-stage processing:

**Step A: Library Search** (`src/diann_runner/workflow.py`)
- Input: FASTA database only (no raw files)
- Uses deep learning predictor to generate predicted spectral library
- Outputs: `{workunit_id}_predicted.speclib` and `.config.json`

**Step B: Quantification with Refinement** (`src/diann_runner/workflow.py`)
- Input: Predicted library + raw/mzML files (can be a subset)
- Generates refined empirical library from actual data
- Optionally generates quantification matrices (controlled by `quantify` parameter)
- Uses `--reanalyse` for match-between-runs (MBR)
- Outputs: `{workunit_id}_refined.speclib` and `.config.json`

**Step C: Final Quantification** (`src/diann_runner/workflow.py`)
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

Implementation in `src/diann_runner/workflow.py`:
- `to_config_dict()`: Serializes all workflow parameters
- `save_config()`: Saves config JSON after each stage
- `from_config_file()`: Loads workflow from config

### Module Structure

All source modules are located in `src/diann_runner/`:

**`src/diann_runner/workflow.py`** - Core workflow generation
- `DiannWorkflow` class: Manages all three stages with shared parameters
- `_build_common_params()`: Builds DIA-NN CLI arguments shared across stages
- `_write_shell_script()`: Generates executable bash scripts
- Each `generate_step_*()` method creates a bash script for that stage

**`src/diann_runner/cli.py`** - Command-line interface using cyclopts
- Commands: `library-search`, `quantification-refinement`, `final-quantification`, `all-stages`, `create-config`, `run-script`
- `_load_workflow_from_defaults()`: Loads workflow with config defaults + CLI overrides
- Command-line args always take precedence over config defaults

**`src/diann_runner/docker.py`** - Docker wrapper for DIA-NN
- Automatically detects Apple Silicon and uses `--platform linux/amd64`
- Mounts current directory to `/work` in container
- Preserves UID/GID on Unix systems for correct file permissions
- Environment variables: `DIANN_DOCKER_IMAGE`, `DIANN_PLATFORM`, `DIANN_EXTRA`

**`src/diann_runner/plotter.py`** - QC plotting utilities (referenced in Snakefile)

**`src/diann_runner/cleanup.py`** - Cleanup utilities for workflow files

**`src/diann_runner/koina_adapter.py`** - Koina predictor integration (see docs/KOINA_INTEGRATION.md)

**`src/diann_runner/oktoberfest_docker.py`** - Oktoberfest integration for spectral prediction (see docs/OKTOBERFEST_INTEGRATION.md)

**`src/diann_runner/prolfquapp_docker.py`** - Prolfqua QC integration

**`src/diann_runner/scripts/`** - Helper shell scripts for external tools

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
  ├── WU{id}_predicted.speclib         # Step A: Predicted library
  └── WU{id}_predicted.speclib.config.json

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

**Note on FASTA files:**
- Step A requires FASTA input via `--fasta` for library generation
- Steps B and C can optionally use FASTA (via `fasta_file` parameter or DiannWorkflow constructor) for protein inference and annotation
- FASTA files are NOT copied to output directories - only the original path is referenced
- The FASTA path can be stored in the `.config.json` files for consistency across stages

## Common Workflows

### 1. Create a Configuration File (Recommended First Step)

Before running workflows, create a reusable configuration file with your default parameters:

```bash
# Create config with your standard settings
diann-workflow create-config \
  --output my_defaults.json \
  --workunit-id WU123 \
  --var-mods "35,15.994915,M" \
  --threads 32 \
  --qvalue 0.01

# View the generated config
cat my_defaults.json
```

This config can then be used with any workflow command via `--config-defaults`, with CLI arguments overriding config values as needed.

### 2. Standard Workflow: Same Files for B and C

**Without config file:**
```bash
diann-workflow all-stages \
  --fasta /path/to/db.fasta \
  --raw-files sample*.mzML \
  --workunit-id WU123 \
  --var-mods "35,15.994915,M" \
  --threads 32
```

**With config file (recommended):**
```bash
# Using config defaults, only specify file-specific args
diann-workflow all-stages \
  --config-defaults my_defaults.json \
  --fasta /path/to/db.fasta \
  --raw-files sample*.mzML
```

### 3. Fast Library Building: Subset for B, All Files for C

When you have many files (50+), use a subset for fast library building in Step B, then quantify all files in Step C:

```bash
# Step A: Library search (FASTA only, no raw files)
diann-workflow library-search \
  --config-defaults my_defaults.json \
  --fasta db.fasta

# Step B: Fast library refinement using subset (no quantification)
diann-workflow quantification-refinement \
  --config out-DIANN_libA/WU123_predicted.speclib.config.json \
  --predicted-lib out-DIANN_libA/WU123_predicted.speclib \
  --raw-files pilot1.mzML pilot2.mzML \
  --no-quantify  # Skip quantification, only build refined library

# Step C: Full quantification with all files
diann-workflow final-quantification \
  --config out-DIANN_quantB/WU123_refined.speclib.config.json \
  --refined-lib out-DIANN_quantB/WU123_refined.speclib \
  --raw-files sample*.mzML
```

**Note:** The `--config` parameter in Steps B and C points to the `.config.json` file from the previous step, ensuring parameter consistency across stages.

## Documentation

Additional documentation is available in the `docs/` directory:
- `docs/README.md` - Documentation index
- `docs/DIANN_PARAMETERS.md` - **Comprehensive DIA-NN parameter reference** (compiled from GitHub repo, issues, and discussions)
- `docs/USAGE_EXAMPLES.md` - Usage examples and recipes
- `docs/QUICK_REFERENCE.md` - Quick reference guide
- `docs/KOINA_INTEGRATION.md` - Koina predictor integration
- `docs/OKTOBERFEST_INTEGRATION.md` - Oktoberfest integration for spectral prediction
- `docs/COMPARING_PREDICTORS.md` - Comparison of different spectral predictors
- `docs/TESTING_LOG.md` - Testing history and results
- `docs/SNAKEFILE_TEST.md` - Snakemake workflow testing guide
- `docs/default_config.json` - Default configuration template

**When troubleshooting DIA-NN issues**: Consult `docs/DIANN_PARAMETERS.md` for parameter explanations, common issues, and links to relevant GitHub discussions.

## Testing Notes

- Tests are in `tests/` directory
- `test_workflow.py` tests the DiannWorkflow class
- `test_cli.py` tests CLI commands
- Run tests before committing changes to workflow generation logic
