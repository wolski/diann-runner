# Deployment Guide: diann_runner on FGCZ Linux Servers

This guide explains how to deploy the `diann_runner` package to FGCZ Linux servers using the Snakemake-based deployment workflow.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Deployment Options](#deployment-options)
4. [Step-by-Step Deployment](#step-by-step-deployment)
5. [Verification](#verification)
6. [Troubleshooting](#troubleshooting)
7. [Configuration](#configuration)
8. [Cleanup](#cleanup)

---

## Prerequisites

Before deploying, ensure the following are installed on the Linux server:

### Required

- **Python 3.10+** - Check with: `python3 --version`
- **Docker** - Check with: `docker --version`
  - Docker daemon must be running: `docker ps`
- **Git** - Check with: `git --version`
- **Snakemake** - Check with: `snakemake --version`
  - Install if needed: `pip install snakemake`
- **uv package manager** - Check with: `uv --version`
  - Install if needed: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Recommended

- **Fish shell** - For running existing workflow scripts
- **16GB+ RAM** - For large datasets
- **50GB+ disk space** - For Docker images and data

---

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/fgcz/diann_runner.git
cd diann_runner
```

### 2. Run Deployment

```bash
# Default deployment (includes oktoberfest)
snakemake -s deploy.smk --cores 1

# Faster deployment (skip oktoberfest)
snakemake -s deploy.smk --cores 1 --config skip_oktoberfest=true

# Dry run first to see what will happen
snakemake -s deploy.smk --cores 1 --dry-run
```

### 3. Activate Environment

```bash
# Fish shell
source .venv/bin/activate.fish

# Bash shell
source .venv/bin/activate
```

### 4. Verify Installation

```bash
diann-docker --help
diann-workflow --help
docker images | grep diann
```

---

## Deployment Options

### Configuration File Method

Edit `deploy_config.yaml`:

```yaml
skip_oktoberfest: false  # Set to true to skip Oktoberfest build
force_rebuild: false     # Set to true to force Docker image rebuilds
```

Then run:

```bash
snakemake -s deploy.smk --cores 1
```

### Command-Line Method

Override settings directly:

```bash
# Skip Oktoberfest (faster, saves 4GB)
snakemake -s deploy.smk --cores 1 --config skip_oktoberfest=true

# Force rebuild of Docker images
snakemake -s deploy.smk --cores 1 --config force_rebuild=true

# Combine options
snakemake -s deploy.smk --cores 1 --config skip_oktoberfest=true force_rebuild=true
```

---

## Step-by-Step Deployment

The deployment workflow consists of the following steps:

### 1. Prerequisites Check

Verifies:
- Python 3.10+ is installed
- Snakemake is available
- uv is installed
- Docker is installed and running
- Git is available
- Sufficient disk space (50GB+)
- CPU cores detected

**Flag:** `.deploy_flags/prerequisites_checked.flag`

### 2. Create Virtual Environment

Creates a Python virtual environment using `uv venv`.

**Output:** `.venv/` directory
**Flag:** `.deploy_flags/venv_created.flag`

### 3. Install Package

Installs the `diann_runner` package in editable mode using `uv pip install -e .`.

This makes the following CLI tools available:
- `diann-docker` - Docker wrapper for DIA-NN
- `diann-workflow` - Workflow generation CLI
- `diann-cleanup` - Cleanup utility
- `diann-qc` - QC plotting tool
- `oktoberfest-docker` - Oktoberfest wrapper
- `prolfquapp-docker` - Prolfqua wrapper

**Flag:** `.deploy_flags/package_installed.flag`

### 4. Build Docker Images

#### DIA-NN (Required)
Builds `diann:2.3.0` Docker image (~10 minutes, 766MB).

**Dockerfile:** `docker/Dockerfile.diann`
**Flag:** `.deploy_flags/diann_docker_built.flag`

#### Oktoberfest (Optional)
Builds `oktoberfest:latest` Docker image (~30-60 minutes, 4GB).

Downloads Dockerfile if not present, then builds the image.

**Skip with:** `--config skip_oktoberfest=true`
**Flag:** `.deploy_flags/oktoberfest_docker_built.flag`

### 5. Verify Installation

Checks that all CLI tools are installed and Docker images are available.

**Flag:** `.deploy_flags/installation_verified.flag`

### 6. Configure for FGCZ

Checks for BFabric infrastructure and provides recommended thread configuration based on detected CPU cores.

**Flag:** `.deploy_flags/fgcz_configured.flag`

### 7. Deployment Complete

Displays summary and next steps.

**Flag:** `.deploy_flags/deployment_complete.flag`

---

## Verification

### Check CLI Tools

```bash
source .venv/bin/activate.fish

diann-docker --help
diann-workflow --help
diann-cleanup --help
diann-qc --help
```

### Check Docker Images

```bash
docker images | grep -E "(diann|oktoberfest)"
```

Expected output:

```
diann                2.3.0    <image-id>   766MB
oktoberfest          latest   <image-id>   4.05GB  (if not skipped)
```

### Test DIA-NN Docker Wrapper

```bash
diann-docker
```

Should display DIA-NN help message.

---

## Troubleshooting

### Problem: Prerequisites check fails

**Solution:** Install missing components:

```bash
# Install Snakemake
pip install snakemake

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Ensure Docker daemon is running
sudo systemctl start docker
```

### Problem: Docker build fails

**Solution 1:** Check Docker daemon is running:

```bash
docker ps
```

**Solution 2:** Check disk space:

```bash
df -h .
```

**Solution 3:** Check build logs:

```bash
ls logs/
cat logs/build_diann_docker.log
```

### Problem: Docker permission denied

**Solution:** Add your user to the docker group:

```bash
sudo usermod -aG docker $USER
# Log out and back in for changes to take effect
```

### Problem: Virtual environment activation fails

**For Fish:**

```fish
source .venv/bin/activate.fish
```

**For Bash:**

```bash
source .venv/bin/activate
```

### Problem: Want to rebuild from scratch

**Solution:** Clean deployment flags and re-run:

```bash
snakemake -s deploy.smk clean_deployment
snakemake -s deploy.smk --cores 1
```

Or force rebuild Docker images:

```bash
snakemake -s deploy.smk --cores 1 --config force_rebuild=true
```

---

## Configuration

### Thread Configuration

After deployment, configure thread count in your `params.yml` based on server CPU cores:

```yaml
params:
  diann:
    threads: 64  # Adjust to match your server (shown during deployment)
```

Check CPU cores:

```bash
nproc  # Shows number of CPU cores
```

### BFabric Integration

If deploying to FGCZ infrastructure with BFabric:

- Deployment checks for `/home/bfabric/slurmworker/bin/fgcz_app_runner`
- Snakefile includes `stageoutput` and `outputsyml` rules
- No additional configuration needed

If deploying to a test server without BFabric:

- Warning message is normal
- BFabric rules will be skipped automatically

---

## Cleanup

### Remove Deployment Flags Only

Re-deploy without rebuilding Docker images:

```bash
snakemake -s deploy.smk clean_deployment
snakemake -s deploy.smk --cores 1
```

### Complete Cleanup

Remove everything (flags, venv, Docker images):

```bash
snakemake -s deploy.smk clean_all
```

This will prompt for confirmation before removing:
- `.deploy_flags/` - Deployment state
- `.venv/` - Python virtual environment
- Docker images: `diann:2.3.0`, `oktoberfest:latest`

---

## Next Steps After Deployment

### 1. Prepare Your Data

```bash
mkdir WU_YOURPROJECT
cd WU_YOURPROJECT

# Copy your data files
cp /path/to/your/*.mzML .
cp /path/to/your/database.fasta .
```

### 2. Create Configuration

```bash
# Copy example params.yml
cp ../example_params_yaml/params.yml .

# Edit to match your data
nano params.yml
```

Key settings to configure:
- `workunit_id`: Your workunit ID
- `fasta_file`: Path to your FASTA database
- `threads`: Number of cores (use `nproc` to check)
- `variable_modifications`: PTMs to search for

### 3. Run Workflow

#### Option A: Use Existing Fish Scripts

```bash
fish ../run_snakefile_workflow.fish --cores 64
```

#### Option B: Use Snakemake Directly

```bash
snakemake -s ../Snakefile.DIANN3step --cores 64 all
```

#### Option C: Use CLI for Custom Workflows

```bash
# Activate venv first
source ../.venv/bin/activate.fish

# Generate all workflow scripts
diann-workflow all-stages \
    --fasta database.fasta \
    --raw-files *.mzML \
    --workunit-id WU001 \
    --var-mods "35,15.994915,M" \
    --threads 64

# Execute generated scripts
bash step_A_library_search.sh
bash step_B_quantification_refinement.sh
bash step_C_final_quantification.sh
```

---

## File Structure After Deployment

```
diann_runner/
├── .deploy_flags/              # Deployment state flags
│   ├── prerequisites_checked.flag
│   ├── venv_created.flag
│   ├── package_installed.flag
│   ├── diann_docker_built.flag
│   ├── oktoberfest_docker_built.flag
│   ├── installation_verified.flag
│   ├── fgcz_configured.flag
│   └── deployment_complete.flag
├── .venv/                      # Python virtual environment
│   └── bin/
│       ├── diann-docker
│       ├── diann-workflow
│       ├── diann-cleanup
│       └── ...
├── logs/                       # Deployment logs
│   ├── check_prerequisites.log
│   ├── build_diann_docker.log
│   └── ...
├── deploy.smk                  # Deployment workflow
├── deploy_config.yaml          # Deployment configuration
└── README_DEPLOYMENT.md        # This file
```

---

## Advanced Usage

### Resume Partial Deployment

Snakemake automatically resumes from the last successful step:

```bash
# If deployment was interrupted, just re-run
snakemake -s deploy.smk --cores 1
```

### Check What Will Be Done

```bash
# Dry run shows pending steps
snakemake -s deploy.smk --cores 1 --dry-run
```

### View Deployment Graph

```bash
# Generate DAG visualization (requires graphviz)
snakemake -s deploy.smk --dag | dot -Tpng > deployment_dag.png
```

### Force Specific Rule

```bash
# Force rebuild of just the DIA-NN Docker image
snakemake -s deploy.smk --cores 1 --forcerun build_diann_docker
```

---

## Support

For issues or questions:

1. Check logs in `logs/` directory
2. Verify prerequisites with `snakemake -s deploy.smk check_prerequisites`
3. Consult the main repository README
4. Contact FGCZ support

---

## Summary

**Deployment in 3 commands:**

```bash
git clone https://github.com/fgcz/diann_runner.git
cd diann_runner
snakemake -s deploy.smk --cores 1 --config skip_oktoberfest=true
```

**Total time:**
- With Oktoberfest: ~40-70 minutes
- Without Oktoberfest: ~10-15 minutes

**Disk space:**
- With Oktoberfest: ~5GB
- Without Oktoberfest: ~1GB

Ready to analyze your mass spectrometry data!
