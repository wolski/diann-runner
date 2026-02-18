---
title: "diann_runner: Automated DIA-NN Workflows"
author: "Witold Wolski, FGCZ"
date: 2026-02-18
---

# What Problem Does diann_runner Solve?

- DIA-NN requires a **multi-step workflow** with many parameters
- Manual execution is error-prone: parameters can drift between steps
- Integration with B-Fabric LIMS needs automated job submission
- Reproducibility requires consistent, tracked configurations

**diann_runner automates the entire DIA-NN pipeline from raw files to QC reports.**

---

# The Three-Stage DIA-NN Workflow

```
   Raw Files + FASTA
        |
   [Step A] Library Prediction
        |  (deep learning, FASTA only)
        v
   [Step B] Library Refinement + Quantification
        |  (empirical library from real data)
        v
   [Step C] Final Quantification (optional)
        |  (use refined library on full dataset)
        v
   QC Reports + Result Tables
```

- **Step A**: Predicts a spectral library from FASTA using deep learning
- **Step B**: Refines the library with actual MS data, quantifies proteins
- **Step C**: Optional re-quantification on a larger file set using the refined library

---

# Supported Input Formats

| Format | Source | Handling |
|--------|--------|----------|
| `.raw` | Thermo instruments | Converted to mzML via ThermoRawFileParser (Docker) |
| `.d.zip` | Bruker timsTOF | Extracted and passed directly to DIA-NN |
| `.mzML` | Any vendor (pre-converted) | Used directly |

- Input files are auto-detected from `input/raw/`
- Format is determined automatically -- no user configuration needed

---

# Key Configurable Parameters

| Parameter | What it controls |
|-----------|-----------------|
| Variable modifications | e.g. Oxidation (M), Phospho (STY) |
| Cross-run normalization | On by default, disable with `--no-norm` |
| Match-between-runs | Improves quantification across runs |
| Protein inference | Standard or relaxed (gene-level grouping) |
| Q-value threshold | FDR control (default: 1%) |

All parameters are set once in B-Fabric and **automatically kept consistent** across all three steps via configuration files.

---

# B-Fabric Integration: End-to-End Automation

```
B-Fabric                    bfabric-app-runner               Compute Server
-------                     ------------------               --------------
 User creates workunit  -->  Dispatcher:
 with parameters             - creates working directory
                             - writes params.yml
                             - stages raw files + FASTA
                             to input/                    -->  Snakemake runs
                                                              DIA-NN workflow
                                                              (Steps A/B/C)
                          <----------------------------------
 Results visible           Registers results:
 in B-Fabric               - reads outputs.yml
                            - copies ZIPs to storage
                            - links resources to workunit
```

- **bfabric-app-runner** is the bridge between B-Fabric and the pipeline
- The **dispatcher** prepares the environment (params.yml, input files)
- After Snakemake finishes, the **outputs register** command reads `outputs.yml` and uploads result ZIPs back to B-Fabric

---

# Pipeline Architecture

```
params.yml  (from bfabric-app-runner)
    |
    v
Snakemake Workflow
    |  (orchestrates all steps)
    |
    +---> Step A script  --->  Predicted library
    +---> Step B script  --->  Refined library + quantification
    +---> Step C script  --->  Final results (optional)
    +---> Prozor         --->  Protein inference from FASTA (optional)
    +---> QC reports     --->  Plots + statistics
    |
    v
outputs.yml  (consumed by bfabric-app-runner)
```

- Snakemake handles **dependencies**, **retries**, and **parallelization**
- Each step saves a `.config.json` to guarantee parameter consistency
- `outputs.yml` declares which ZIPs to register back in B-Fabric

---

# Outputs

| File | Content |
|------|---------|
| `*_report.tsv` | Precursor-level quantification (main result) |
| `*_report.pg_matrix.tsv` | Protein group quantities across samples |
| `*_report.stats.tsv` | Per-run statistics |
| `*_prozor.parquet` | Re-annotated protein groups (greedy parsimony) |
| `Result_WU*.zip` | QC plots and reports |
| `DIANN_Result_WU*.zip` | Complete DIA-NN results for archiving |

All results are automatically packaged and registered in B-Fabric.

---

# Deployment

- **Two repositories** involved:
    - `diann_runner` -- workflow code, Snakefile, Docker images
    - `slurmworker` -- B-Fabric app config (`app.yml`, `dispatch.py`, `pylock.toml`)
- **Deployment** via Snakemake: `snakemake -s deploy.smk --cores 1`
    - Installs Python package (`uv pip install -e .`)
    - Builds Docker images (DIA-NN, ThermoRawFileParser)
    - Verifies CLI tools and infrastructure
- **Updating production**: push both repos, pull on server
- **Production servers**: fgcz-r-038, fgcz-c-072, fgcz-c-073, fgcz-r-033
- **Environments**: production (64 cores, `/home/bfabric/`) and development (local paths, 8 cores)

---

# Summary

- **Fully automated**: raw files in, QC reports out
- **Reproducible**: all parameters tracked in config files
- **Flexible**: supports Thermo, Bruker, and pre-converted mzML
- **Integrated**: B-Fabric submission, Docker containers, Snakemake orchestration
- **Quality controlled**: automatic QC plots and statistics per run

