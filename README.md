# DIA-NN Runner

Python tools for running DIA-NN mass spectrometry workflows with Docker and Snakemake.

## Installation

```bash
uv pip install -e .
```

## CLI Commands

| Command | Purpose |
|---------|---------|
| `diann-workflow` | Generate three-stage DIA-NN workflow scripts |
| `diann-docker` | Run DIA-NN in Docker container |
| `diann-snakemake` | Execute Snakemake workflow |
| `diann-qc` | Generate QC plots from results |
| `diann-qc-report` | Generate Markdown QC report |
| `diann-cleanup` | Clean up workflow output files |
| `prolfquapp-docker` | Run prolfqua QC in Docker |
| `thermoraw` | Convert Thermo RAW to mzML (native on macOS, Docker elsewhere) |
| `prozor-diann` | Run protein inference on DIA-NN report using prozor algorithm |

Use `<command> --help` for options.

**Note:** `diann-snakemake` is equivalent to `python -m diann_runner.snakemake_cli` (used by slurmworker).

## Quick Start

```bash
# Generate workflow scripts
diann-workflow all-stages \
  --fasta db.fasta \
  --raw-files *.mzML \
  --workunit-id WU123

# Run them
bash step_A_library_search.sh
bash step_B_quantification_refinement.sh
bash step_C_final_quantification.sh
```

Or run DIA-NN directly:

```bash
diann-docker --f sample.mzML --fasta db.fasta --out report.tsv
```

## Three-Stage Workflow

| Stage | Input | Output |
|-------|-------|--------|
| **A: Library Search** | FASTA | Predicted spectral library |
| **B: Refinement** | Library + mzML (subset OK) | Refined library |
| **C: Quantification** | Refined library + all mzML | Final reports |

## Documentation

- [Usage Guide](docs/USAGE_EXAMPLES.md) - Detailed workflow patterns
- [DIA-NN Parameters](docs/DIANN_PARAMETERS.md) - Parameter reference
- [Deployment Guide](README_DEPLOYMENT.md) - Production setup

## Development

```bash
uv pip install -e ".[test]"
python -m pytest tests/
```
