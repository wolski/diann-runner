# Oktoberfest/Koina Integration

Alternative spectral library predictor integration for diann_runner.

**Status:** Experimental / Not integrated into main workflow

## Overview

This subproject provides tools to use [Oktoberfest](https://github.com/wilhelm-lab/oktoberfest) and [Koina](https://koina.wilhelmlab.org/) as alternative spectral library predictors instead of DIA-NN's built-in predictor.

## Contents

| File | Purpose |
|------|---------|
| `koina_adapter.py` | Translate DIA-NN config → Oktoberfest config |
| `oktoberfest_docker.py` | Docker wrapper for running Oktoberfest |
| `workflow_koina.config.json` | Example workflow config for Koina comparison |
| `docs/SPECTRAL_PREDICTION.md` | Detailed usage guide |
| `docs/COMPARING_PREDICTORS.md` | Side-by-side comparison workflow |

## When to Use

Use Oktoberfest/Koina when:
- Instrument-specific predictions needed (timsTOF, Astral)
- Non-standard digestion (LysC, AspN)
- Complex PTM analysis requiring specialized models
- Benchmarking different prediction approaches

Use DIA-NN's built-in predictor (default) when:
- Standard tryptic digestion on Orbitrap HCD
- Simplicity and speed are priorities
- Integrated workflow without external dependencies

## Quick Start

### 1. Build Oktoberfest Docker Image

```bash
git clone --depth 1 https://github.com/wilhelm-lab/oktoberfest.git oktoberfest_repo
cd oktoberfest_repo
git rev-parse HEAD > hash.file
docker build --platform linux/amd64 -t oktoberfest:latest .
```

### 2. Install Tools (from main diann_runner directory)

```bash
cd /path/to/diann_runner
uv pip install -e "contrib/oktoberfest"
```

Or run directly:

```bash
uv run contrib/oktoberfest/oktoberfest_docker.py -c config.json
uv run contrib/oktoberfest/koina_adapter.py --help
```

### 3. Generate Oktoberfest Config

```bash
python contrib/oktoberfest/koina_adapter.py \
  --diann-config out-DIANN_libA/WU123_predicted.speclib.config.json \
  --fasta database.fasta \
  --output oktoberfest_config.json
```

### 4. Run Oktoberfest

```bash
python contrib/oktoberfest/oktoberfest_docker.py -c oktoberfest_config.json
```

### 5. Use Generated Library with DIA-NN

```bash
diann-workflow quantification-refinement \
  --config workflow_config.json \
  --predicted-lib output/speclib.msp \
  --raw-files *.mzML
```

## Documentation

- [SPECTRAL_PREDICTION.md](docs/SPECTRAL_PREDICTION.md) - Full usage guide
- [COMPARING_PREDICTORS.md](docs/COMPARING_PREDICTORS.md) - Comparison workflow

## References

- [Oktoberfest paper](https://doi.org/10.1002/pmic.202300112) - Picciani et al., PROTEOMICS 2024
- [Koina paper](https://www.nature.com/articles/s41467-025-64870-5) - Nature Communications 2025
- [Oktoberfest docs](https://oktoberfest.readthedocs.io/)
- [Koina server](https://koina.wilhelmlab.org/)
