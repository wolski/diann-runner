# DIA-NN Runner

Python tools for running DIA-NN mass spectrometry workflows with Docker and Snakemake.

## Installation

```bash
uv pip install -e .
```

## CLI Commands

| Command | Purpose |
|---------|---------|
| `diann-docker` | `diann_docker.py` | Run DIA-NN in Docker container |
| `diann-snakemake` | `snakemake_cli.py` | Execute Snakemake workflow |
| `diann-qc` | `plotter.py` | Generate QC plots from results |
| `diann-qc-report` | `qc_report.py` | Generate Markdown QC report |
| `diann-cleanup` | `cleanup.py` | Clean up workflow output files |
| `prolfquapp-docker` | `prolfquapp_docker.py` | Run prolfqua QC in Docker |
| `thermoraw` | `thermoraw_docker.py` | Convert Thermo RAW to mzML (native on macOS, Docker elsewhere) |
| `prozor-diann` | `prozor_diann.py` | Run protein inference on DIA-NN report using prozor algorithm |

Use `<command> --help` for options.

**Note:** `diann-snakemake` is equivalent to `python -m diann_runner.snakemake_cli` (used by slurmworker).

## Quick Start

```bash
# Run the Snakemake workflow
diann-snakemake --cores 8 -p all
```

Or run DIA-NN directly using the Docker wrapper:

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
