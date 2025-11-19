# DIA-NN Runner

Tools for running DIA-NN workflows with Docker and Snakemake.

## Installation

```bash
cd diann_runner
uv venv
source .venv/bin/activate  # or `.venv/Scripts/activate` on Windows
uv pip install -e .
```

For testing:
```bash
uv pip install -e ".[test]"
```

## Documentation

- **[Usage Guide](docs/USAGE_EXAMPLES.md)** - Quick reference and detailed workflow patterns
- **[Spectral Prediction](docs/SPECTRAL_PREDICTION.md)** - Using Koina/Oktoberfest for library generation
- **[Comparing Predictors](docs/COMPARING_PREDICTORS.md)** - Running parallel workflows
- **[DIA-NN Parameters](docs/DIANN_PARAMETERS.md)** - Comprehensive parameter reference
- **[Deployment Guide](README_DEPLOYMENT.md)** - Deploy to production servers

## Quick Start

### Generate all three workflow stages:

```bash
diann-workflow all-stages \
  --fasta /path/to/db.fasta \
  --raw-files sample1.mzML sample2.mzML \
  --workunit-id WU123 \
  --var-mods "35,15.994915,M"
```

### Run the generated scripts:

```bash
bash step_A_library_search.sh
bash step_B_quantification_refinement.sh
bash step_C_final_quantification.sh
```

## Configuration

### Default Configuration

Create a reusable config file to avoid repeating parameters:

```bash
# Create config with your standard settings
diann-workflow create-config \
  --output my_defaults.json \
  --workunit-id WU123 \
  --var-mods "35,15.994915,M" \
  --threads 32 \
  --qvalue 0.01

# Use it with any command
diann-workflow all-stages \
  --config-defaults my_defaults.json \
  --fasta db.fasta \
  --raw-files sample*.mzML
```

See `docs/default_config.json` for a complete configuration template.

### Common Modifications

Variable modifications use tuples of (unimod_id, mass_delta, residues):

| Modification | UniMod ID | Mass Delta | Residues | Usage |
|--------------|-----------|------------|----------|-------|
| Oxidation | 35 | 15.994915 | M | `--var-mods "35,15.994915,M"` |
| Phosphorylation | 21 | 79.966331 | STY | `--var-mods "21,79.966331,STY"` |
| Acetylation | 1 | 42.010565 | K | `--var-mods "1,42.010565,K"` |
| Acetylation (N-term) | 1 | 42.010565 | ^* | `--var-mods "1,42.010565,^*"` |
| Deamidation | 7 | 0.984016 | NQ | `--var-mods "7,0.984016,NQ"` |

**Note:** `^*` represents protein N-terminus in DIA-NN

### Key Parameters

All `DiannWorkflow` initialization parameters can be configured:

- `workunit_id` - Workunit identifier for naming outputs (required)
- `output_base_dir` - Base directory for outputs (default: `"out-DIANN"`)
- `var_mods` - Variable modifications list
- `diann_bin` - Path to DIA-NN binary (default: `"diann-docker"`)
- `threads` - CPU threads (default: `64`)
- `qvalue` - FDR threshold (default: `0.01`)
- `is_dda` - Set `True` for DDA data (default: `False`)
- `pg_level` - Protein grouping: `0`=genes, `1`=names, `2`=IDs (default: `0`)
- `min_pep_len` / `max_pep_len` - Peptide length range (default: `6-30`)
- `min_pr_charge` / `max_pr_charge` - Precursor charge range (default: `2-3`)
- `min_pr_mz` / `max_pr_mz` - Precursor m/z range (default: `400-1500`)
- `missed_cleavages` - Maximum missed cleavages (default: `1`)
- `cut` - Protease specificity (default: `"K*,R*"` for trypsin)
- `mass_acc` - MS2 mass accuracy in ppm (default: `20`)
- `mass_acc_ms1` - MS1 mass accuracy in ppm (default: `15`)

## Workflow Overview

The DIA-NN workflow consists of three stages:

### Step A: Library Search
Generate predicted spectral library from FASTA using deep learning predictor.

**Input:** FASTA database only (no raw files)
**Output:** `out-DIANN_libA/{workunit}_predicted.speclib` and `.config.json`

### Step B: Quantification with Refinement
Refine library using real data and optionally generate quantification matrices.

**Input:** Predicted library + raw/mzML files (can be a subset)
**Output:** `out-DIANN_quantB/{workunit}_refined.speclib`, reports (if quantify=True), `.config.json`

### Step C: Final Quantification
Produce final quantification results using refined library.

**Input:** Refined library + raw/mzML files (can be different/larger set than Step B)
**Output:** `out-DIANN_quantC/{workunit}_reportC.tsv`, protein/precursor matrices

**Important:** Each stage saves a `.config.json` file to ensure parameter consistency across the workflow.

## Command-Line Interface

**Note:** By default, all commands use `diann-docker` (Docker wrapper) as the DIA-NN binary. Override with `--diann-bin` if you have a native installation.

### Individual Stages with Config Chaining

```bash
# Step A: Library search
# Creates: out_A_libA/WU123_predicted.speclib
#      and out_A_libA/WU123_predicted.speclib.config.json
diann-workflow library-search \
  --fasta db.fasta \
  --output-dir out_A \
  --workunit-id WU123 \
  --var-mods "35,15.994915,M"

# Step B: Quantification with refinement
# Requires config from Step A to ensure parameter consistency
# Creates: out_A_quantB/WU123_refined.speclib
#      and out_A_quantB/WU123_refined.speclib.config.json
diann-workflow quantification-refinement \
  --config out_A_libA/WU123_predicted.speclib.config.json \
  --predicted-lib out_A_libA/WU123_predicted.speclib \
  --raw-files sample1.mzML sample2.mzML

# Step C: Final quantification
# Requires config from Step B to ensure parameter consistency
# Creates: out_A_quantC/WU123_reportC.tsv
#      and out_A_quantC/WU123_reportC.tsv.config.json
diann-workflow final-quantification \
  --config out_A_quantB/WU123_refined.speclib.config.json \
  --refined-lib out_A_quantB/WU123_refined.speclib \
  --raw-files sample1.mzML sample2.mzML
```

**Important:** Steps B and C require a `--config` parameter pointing to the JSON config file from the previous step. This ensures that critical parameters (var_mods, threads, qvalue, etc.) remain consistent across the entire workflow.

### Execute Generated Scripts

```bash
diann-workflow run-script --script step_A_library_search.sh
```

### Get Help

```bash
diann-workflow --help
diann-workflow all-stages --help
diann-workflow library-search --help
diann-workflow create-config --help
```

## Docker Runner

Run DIA-NN in Docker:

```bash
diann-docker --help
diann-docker --f data.mzML --fasta db.fasta --out report.tsv
```

## Python API

Use as a library:

```python
from diann_runner import DiannWorkflow

# Initialize with shared parameters
workflow = DiannWorkflow(
    workunit_id='WU123',
    var_mods=[('35', '15.994915', 'M')],  # Oxidation
    threads=64,
    qvalue=0.01,
)

# Generate all three scripts
workflow.generate_all_scripts(
    fasta_path='/path/to/database.fasta',
    raw_files_step_b=['sample1.mzML', 'sample2.mzML'],
)
```

See [Usage Guide](docs/USAGE_EXAMPLES.md) for detailed patterns and examples.

## Snakemake Workflow

Run the complete workflow:

```bash
cd work_directory
snakemake -s /path/to/diann_runner/Snakefile --cores 64
```

## Project Structure

```
diann_runner/
├── pyproject.toml           # Package configuration
├── Dockerfile.diann         # Docker image for DIA-NN
├── Snakefile                # Snakemake workflow
├── docs/                    # Documentation
│   ├── USAGE_EXAMPLES.md   # Usage guide and patterns
│   ├── SPECTRAL_PREDICTION.md # Koina/Oktoberfest integration
│   ├── COMPARING_PREDICTORS.md # Parallel workflows
│   ├── DIANN_PARAMETERS.md # Parameter reference
│   └── default_config.json # Example config
├── src/
│   └── diann_runner/
│       ├── __init__.py      # Package exports
│       ├── cli.py           # Command-line interface
│       ├── docker.py        # Docker runner
│       ├── workflow.py      # Workflow generators
│       └── plotter.py       # QC plotting
└── tests/                   # Test suite
```

## Development

Run tests:

```bash
python3 tests/test_workflow.py
# or with pytest
python3 -m pytest tests/
```
