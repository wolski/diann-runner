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

## Project Structure

```
diann_runner/
├── pyproject.toml           # Package configuration
├── Dockerfile.diann         # Docker image for DIA-NN
├── Snakefile                # Snakemake workflow
├── docs/                    # Documentation and examples
│   ├── README.md           # Configuration guide
│   └── default_config.json # Example config file
├── src/
│   └── diann_runner/
│       ├── __init__.py      # Package exports
│       ├── cli.py           # Command-line interface
│       ├── docker.py        # Docker runner utilities
│       ├── workflow.py      # Workflow script generators
│       └── plotter.py       # QC plotting tools
└── tests/                   # Test suite
```

## Usage

### Command-Line Interface

**Note:** By default, all commands use `diann-docker` (Docker wrapper) as the DIA-NN binary. You can override this with `--diann-bin` flag if you have a native installation.

Generate all three workflow stages:

```bash
diann-workflow all-stages \
  --fasta /path/to/db.fasta \
  --raw-files sample1.mzML sample2.mzML \
  --workunit-id WU123 \
  --var-mods "35,15.994915,M"
```

Generate individual stages (with config state management):

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

Create a default config file (to avoid repeating parameters):
```bash
# Use the example config from docs/
diann-workflow library-search \
  --config-defaults docs/default_config.json \
  --fasta db.fasta

# Or create your own config with custom settings
diann-workflow create-config \
  --output my_defaults.json \
  --workunit-id WU123 \
  --var-mods "35,15.994915,M" \
  --threads 32

# Then use it (command-line args override defaults)
diann-workflow library-search \
  --config-defaults my_defaults.json \
  --fasta db.fasta

diann-workflow all-stages \
  --config-defaults my_defaults.json \
  --fasta db.fasta \
  --raw-files sample1.mzML sample2.mzML
```

See `docs/README.md` for more information about configuration files and common modifications.

Execute a generated script:
```bash
diann-workflow run-script --script step_A_library_search.sh
```

Get help:
```bash
diann-workflow --help
diann-workflow all-stages --help
diann-workflow run-script --help
diann-workflow create-config --help
```

### Docker Runner

Run DIA-NN in Docker:

```bash
diann-docker --help
diann-docker --f data.mzML --fasta db.fasta --out report.tsv
```

### Python API

Use as a library:

```python
from diann_runner import (
    generate_library_search,
    generate_quantification_with_refinement,
    generate_final_quantification
)

# Define parameters
var_mods = [('35', '15.994915', 'M')]  # Oxidation
raw_files = ['sample1.mzML', 'sample2.mzML']
common_params = {'threads': 64, 'qvalue': 0.01}

# Generate scripts
generate_library_search(
    fasta_path='/path/to/db.fasta',
    output_dir='out_A',
    workunit_id='WU123',
    var_mods=var_mods,
    common_params=common_params
)
```

### Snakemake Workflow

Run the complete workflow:

```bash
cd work_directory
snakemake -s /path/to/diann_runner/Snakefile --cores 64
```

## Development

Run tests:

```bash
python3 tests/test_workflow.py
# or with pytest
python3 -m pytest tests/
```

