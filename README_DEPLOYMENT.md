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
8. [Slurmworker Integration](#slurmworker-integration)
9. [Cleanup](#cleanup)

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
# Default deployment
snakemake -s deploy.smk --cores 1

# Dry run first to see what will happen
snakemake -s deploy.smk --cores 1 --dry-run

# Optional: include Oktoberfest (~4GB, see contrib/oktoberfest/)
snakemake -s deploy.smk --cores 1 --config skip_oktoberfest=false
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
docker images | grep diann
```

---

## Deployment Options

### Configuration File Method

Edit `deploy_config.yaml`:

```yaml
skip_oktoberfest: true   # Default: skip (tools in contrib/oktoberfest/)
force_rebuild: false     # Set to true to force Docker image rebuilds
```

Then run:

```bash
snakemake -s deploy.smk --cores 1
```

### Command-Line Method

Override settings directly:

```bash
# Force rebuild of Docker images
snakemake -s deploy.smk --cores 1 --config force_rebuild=true

# Include Oktoberfest (optional, adds ~4GB)
snakemake -s deploy.smk --cores 1 --config skip_oktoberfest=false
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
- `diann-cleanup` - Cleanup utility
- `diann-qc` - QC plotting tool
- `prolfquapp-docker` - Prolfqua wrapper

**Optional:** Oktoberfest tools available in `contrib/oktoberfest/`

**Flag:** `.deploy_flags/package_installed.flag`

### 4. Build Docker Images

#### DIA-NN (Required)
Builds `diann:2.3.2` Docker image (~10 minutes, 766MB).

**Dockerfile:** `docker/Dockerfile.diann`
**Flag:** `.deploy_flags/diann_docker_built.flag`

#### ThermoRawFileParser (Required)
Builds `thermorawfileparser:latest` Docker image for converting Thermo RAW files to mzML.

**Dockerfile:** `docker/Dockerfile.thermorawfileparser`
**Flag:** `.deploy_flags/thermorawfileparser_docker_built.flag`

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

## Slurmworker Integration

This section explains how `diann_runner` integrates with the FGCZ slurmworker infrastructure for automated Bfabric workunit processing.

**Note:** The slurmworker configuration files (`app.yml`, `dispatch.py`, etc.) are maintained in a **separate repository**: [slurmworker](https://github.com/fgcz/slurmworker). The `diann_runner` package is referenced as a dependency by slurmworker, not the other way around.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Bfabric LIMS                                  │
│                    (triggers workunit execution)                        │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  SLURMWORKER REPO (github.com/fgcz/slurmworker)                         │
│  config/A386_DIANN_23/                                                  │
│  ├── app.yml          ← Defines versions & commands for bfabric-app-runner
│  ├── dispatch.py      ← Creates params.yml + inputs.yml from workunit   │
│  ├── pyproject.toml   ← Dependencies (includes diann-runner)            │
│  └── pylock.toml      ← Locked deps (synced to server via git)          │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ references as dependency
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  DIANN_RUNNER REPO (this repo)                                          │
│  ├── src/diann_runner/       ← Python package (CLI tools)               │
│  ├── Snakefile.DIANN3step.smk← Main workflow                            │
│  └── docker/                 ← Dockerfiles                              │
└─────────────────────────────────────────────────────────────────────────┘
```

### Slurmworker Config Files

These files are in the **slurmworker repository** (not diann_runner):
- Local development: `~/projects/slurmworker/config/A386_DIANN_23/`
- Production server: `/home/bfabric/slurmworker/config/A386_DIANN_23/`

| File | Purpose |
|------|---------|
| `app.yml` | Defines app versions and commands for bfabric-app-runner |
| `dispatch.py` | Converts Bfabric workunit to `params.yml` + `inputs.yml` |
| `pyproject.toml` | Python dependencies (references diann-runner) |
| `pylock.toml` | Locked dependencies for reproducible environments |

### Execution Flow

When Bfabric triggers a workunit:

**1. Dispatch phase** (`make dispatch`):
- Runs `dispatch.py` which reads the workunit definition
- Creates `work/params.yml` (workflow parameters from Bfabric GUI)
- Creates `work/inputs.yml` (input files to fetch from storage)

**2. Inputs phase** (`make inputs`):
- Downloads dataset files from Bfabric storage
- Fetches FASTA file for the order

**3. Process phase** (`make process`):
- Runs `python -m diann_runner.snakemake_cli --cores 64 -p all -d`
- Executes `Snakefile.DIANN3step.smk` with the prepared inputs

**4. Stage phase** (`make stage`):
- Uploads results back to Bfabric

### How diann_runner is Installed

The `pyproject.toml` in slurmworker config references diann_runner:

```toml
dependencies = [
    "diann-runner @ file:///home/bfabric/diann_runner",
    # ... other deps
]
```

When `bfabric-app-runner` creates the python environment, it:
1. Reads `pylock.toml` for locked dependencies
2. Creates an isolated environment with all packages
3. Installs diann_runner from the local checkout

### Updating diann_runner on Production

**On your local machine (two repositories involved):**

```bash
# 1. Make changes to diann_runner repo
cd ~/projects/diann_runner
# ... edit files ...
git add -A && git commit -m "your changes" && git push

# 2. Update lock file in slurmworker repo (separate repository!)
cd ~/projects/slurmworker/config/A386_DIANN_23
uv lock -U && uv sync
uv export --format pylock.toml -o pylock.toml --no-emit-project

# 3. Commit and push slurmworker changes
git add pylock.toml
git commit -m "update pylock"
git push
```

**On the server (fgcz-c-073) - pull both repositories:**

```bash
# 1. Pull slurmworker repo (contains app.yml, dispatch.py, pylock.toml)
cd /home/bfabric/slurmworker
git pull

# 2. Pull diann_runner repo (contains the actual workflow code)
# IMPORTANT: This step is often forgotten but required!
cd /home/bfabric/diann_runner
git pull
```

### Development vs Production Versions

The `app.yml` defines two versions:

**Production (`version: "2.3"`):**
- Uses `/home/bfabric/...` paths
- Uses `python_env` type with `pylock.toml`
- Runs with 64 cores

**Development (`version: devel`):**
- Uses local paths (e.g., `/Users/wolski/projects/...`)
- Can use `uv run --script` for dispatch
- Runs with fewer cores (8)

### Local Testing

Test the integration locally before deploying. Requires both repositories cloned:
- `~/projects/diann_runner` - this repo
- `~/projects/slurmworker` - the slurmworker repo

```bash
# Install bfabric-app-runner
uv tool install -p 3.13 bfabric-app-runner

# Prepare a workunit locally (read-only mode)
# Note: --app-spec points to the slurmworker repo, not diann_runner
bfabric-app-runner prepare workunit \
  --app-spec ~/projects/slurmworker/config/A386_DIANN_23/app.yml \
  --work-dir WU338923 --workunit-ref 338923 --read-only

# Or force devel version
bfabric-app-runner prepare workunit \
  --app-spec ~/projects/slurmworker/config/A386_DIANN_23/app.yml \
  --work-dir WU338923 --workunit-ref 338923 --read-only \
  --force-app-version devel

# Run the workunit (in the WU directory)
cd WU338923
make run-all  # or: make dispatch && make inputs && make process && make stage
```

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
- Docker images: `diann:2.3.2`, `thermorawfileparser:latest`, `oktoberfest:latest`

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
cp ../bfabric_executable/params.yml .

# Edit to match your data
nano params.yml
```

Key settings to configure:
- `workunit_id`: Your workunit ID
- `fasta_file`: Path to your FASTA database
- `threads`: Number of cores (use `nproc` to check)
- `variable_modifications`: PTMs to search for

### 3. Run Workflow

#### Option A: Use diann-snakemake

```bash
diann-snakemake --cores 64 -p all
```

#### Option B: Use Snakemake directly

```bash
snakemake -s /path/to/Snakefile.DIANN3step.smk --cores 64 -p all
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
snakemake -s deploy.smk --cores 1
```

**Total time:** ~10-15 minutes

**Disk space:** ~1GB

**Optional Oktoberfest:** See `contrib/oktoberfest/` for alternative spectral predictor integration (~4GB additional).

Ready to analyze your mass spectrometry data!
