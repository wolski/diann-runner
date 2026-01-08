# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a Python package for running DIA-NN (mass spectrometry data analysis) workflows. It provides:
- A Docker wrapper (`diann-docker`) to run DIA-NN in containers
- A CLI tool (`diann-workflow`) to generate three-stage DIA-NN workflow scripts
- A Snakemake workflow for automated pipeline execution
- QC plotting utilities

The package uses `uv` for dependency management and `cyclopts` for CLI argument parsing.

## CLI Entry Points

All commands defined in `pyproject.toml`:

| Command | Module | Purpose |
|---------|--------|---------|
| `diann-docker` | `docker.py` | Run DIA-NN in Docker container |
| `diann-workflow` | `cli.py` | Generate three-stage workflow scripts |
| `diann-cleanup` | `cleanup.py` | Clean up workflow output files |
| `diann-qc` | `plotter.py` | Generate QC plots from DIA-NN results |
| `diann-koina-adapter` | `koina_adapter.py` | Koina predictor integration |
| `oktoberfest-docker` | `oktoberfest_docker.py` | Run Oktoberfest for spectral prediction |
| `prolfquapp-docker` | `prolfquapp_docker.py` | Run prolfqua QC in Docker |

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

**Snakemake Workflow Execution:**

Use `run_snakemake_workflow.fish` to execute the complete Snakemake workflow:

```bash
# Navigate to your data directory containing .raw/.mzML/.d.zip files
cd /path/to/your/data

# Ensure params.yml exists (copy from example_params_yaml/params.yml and customize)
# The script will auto-generate dataset.csv if missing

# Run the workflow
/path/to/diann-runner/run_snakemake_workflow.fish --cores 8

# To continue from a previous run without cleanup:
/path/to/diann-runner/run_snakemake_workflow.fish --no-cleanup --cores 8
```

The script will:
1. Auto-generate `dataset.csv` from data files if missing
2. Verify `params.yml` exists (error if not found)
3. Run `diann-cleanup` (unless `--no-cleanup` specified)
4. Execute Snakemake workflow with proper environment activation
5. Log all output to `workflow.log`
6. Report success/failure with correct exit codes

### Docker Image
```bash
# Build the DIA-NN Docker image
docker build --platform linux/amd64 -f docker/Dockerfile.diann-2.3.1 -t diann:2.3.1 .

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

**`src/diann_runner/plotter.py`** - QC plotting utilities (`diann-qc` command)

**`src/diann_runner/cleanup.py`** - Cleanup utilities (`diann-cleanup` command)

**`src/diann_runner/koina_adapter.py`** - Koina predictor integration (`diann-koina-adapter` command, see docs/SPECTRAL_PREDICTION.md)

**`src/diann_runner/oktoberfest_docker.py`** - Oktoberfest integration (`oktoberfest-docker` command, see docs/SPECTRAL_PREDICTION.md)

**`src/diann_runner/prolfquapp_docker.py`** - Prolfqua QC integration (`prolfquapp-docker` command)

**`snakemake_helpers.py`** - Helper functions for Snakemake (at project root)
- `detect_input_files()`: Detects .d.zip, .raw, or .mzML files with priority logic
- `parse_flat_params()`: Transforms flat Bfabric XML keys to nested structure
- `parse_var_mods_string()`: Parses modification strings into tuples
- `create_diann_workflow()`: Factory function to initialize DiannWorkflow from parsed params
- `get_final_quantification_outputs()`: Returns output paths based on Step B vs Step C
- `convert_parquet_to_tsv()`: Converts DIA-NN 2.3+ parquet output to TSV
- `build_oktoberfest_config()`: Builds Oktoberfest configuration dictionary

### Snakemake Workflow

The `Snakefile.DIANN3step.smk` orchestrates the complete pipeline:
1. File conversion (`.raw` → `.mzML` or `.d.zip` → `.d`)
2. DIA-NN execution (generates and runs bash script)
3. QC report generation
4. Results packaging and upload to bfabric

Key features:
- Reads configuration from `params.yml` in the working directory
- Dynamically detects input file types (`.raw`, `.d.zip`, or `.mzML`) via `detect_input_files()`
- Integrates with FGCZ infrastructure (bfabric, prolfqua)
- Uses Docker containers for msconvert and prolfqua
- Supports optional Step C (controlled by `enable_step_c` parameter)
- Supports alternative library predictors: DIA-NN (default) or Oktoberfest

### Bfabric Parameter Flow Architecture

The workflow integrates with Bfabric LIMS, which requires a specific parameter transformation pipeline:

**Parameter Flow:**
```
Bfabric XML (executable.xml)
  → GUI parameter selection
  → YAML with flat keys (params.yml)
  → Python nested structure
  → DiannWorkflow
  → DIA-NN CLI commands
```

**Key Components:**

1. **XML Definition** (`example_params_yaml/executable_new.xml`)
   - Defines GUI parameters with flat keys like `06a_diann_mods_variable`
   - Uses hierarchical numbering (06a, 06b, 06c) for logical grouping
   - Parameter order affects GUI layout in Bfabric

2. **YAML Output** (`params.yml`)
   - Generated by Bfabric with flat keys matching XML
   - Example: `06a_diann_mods_variable: '--var-mods 1 --var-mod UniMod:35,15.994915,M'`

3. **Parsing Layer** (`snakemake_helpers.py`)
   - `parse_flat_params()`: Transforms flat XML keys to nested Python structure
   - `parse_var_mods_string()`: Parses modification strings into tuples
   - Maps Bfabric keys to workflow parameters:
     - `06a_diann_mods_variable` → `diann['var_mods']`
     - `11b_diann_protein_relaxed_prot_inf` → `diann['relaxed_prot_inf']`
     - `12a_diann_quantification_reanalyse` → `diann['reanalyse']`

4. **Snakefile Integration** (`Snakefile.DIANN3step`)
   - Calls `parse_flat_params(config_dict["params"])` to transform parameters
   - Passes nested structure to `DiannWorkflow` constructor

5. **Workflow Generation** (`src/diann_runner/workflow.py`)
   - `DiannWorkflow` class uses nested parameters
   - `_build_common_params()`: Converts to DIA-NN CLI flags
   - Conditionally adds flags based on boolean parameters:
     - `--relaxed-prot-inf` (if `relaxed_prot_inf=True`)
     - `--reanalyse` (if `reanalyse=True`)
     - `--no-norm` (if `no_norm=True`)

**Important Rule:** Complex Python code must ALWAYS go in `snakemake_helpers.py`, never directly in the Snakefile. The Snakefile should only orchestrate rules and call helper functions.

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

DIA-NN 2.3+ outputs `.parquet` files by default. The workflow converts these to TSV for downstream tools.

```
out-DIANN_libA/
  ├── WU{id}_report-lib.predicted.speclib  # Step A: Predicted library
  └── WU{id}_libA.config.json

out-DIANN_quantB/
  ├── WU{id}_report-lib.parquet        # Step B: Refined library (parquet format)
  ├── WU{id}_quantB.config.json
  ├── WU{id}_report.parquet            # Main report (parquet)
  ├── WU{id}_report.tsv                # Converted for downstream tools
  ├── WU{id}_report.pg_matrix.tsv      # Protein group matrix
  └── WU{id}_report.stats.tsv          # Statistics

out-DIANN_quantC/                      # Only if enable_step_c=True
  ├── WU{id}_report-lib.parquet        # ★ Final library
  ├── WU{id}_report.parquet            # ★ Main results (parquet)
  ├── WU{id}_report.tsv                # ★ Converted for prolfqua/diann-qc
  ├── WU{id}_report.pg_matrix.tsv      # ★ Protein matrix
  └── WU{id}_report.stats.tsv          # Statistics
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
- `docs/USAGE_EXAMPLES.md` - **Usage guide with quick reference and detailed patterns**
- `docs/SPECTRAL_PREDICTION.md` - Koina/Oktoberfest integration for spectral library generation
- `docs/COMPARING_PREDICTORS.md` - Running parallel workflows with different predictors
- `docs/DIANN_PARAMETERS.md` - **Comprehensive DIA-NN parameter reference** (compiled from GitHub repo, issues, and discussions)
- `docs/default_config.json` - Default configuration template
- `README_DEPLOYMENT.md` - Deployment guide for production servers

**When troubleshooting DIA-NN issues**: Consult `docs/DIANN_PARAMETERS.md` for parameter explanations, common issues, and links to relevant GitHub discussions.

## Testing Notes

- Tests are in `tests/` directory
- `test_workflow.py` tests the DiannWorkflow class
- `test_cli.py` tests CLI commands
- Run tests before committing changes to workflow generation logic
