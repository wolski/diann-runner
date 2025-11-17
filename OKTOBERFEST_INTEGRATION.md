# Oktoberfest Integration Documentation

This document describes how to use Oktoberfest for spectral library generation as an alternative to DIA-NN's built-in predictor.

## Overview

Oktoberfest uses deep learning models (Prosit/Koina) to predict spectral libraries from FASTA files. This integration provides:
- Docker-based execution for easy deployment
- Parameter translation from DIA-NN configs
- Integration with the DIA-NN workflow for Steps B and C

## Setup

### 1. Build Oktoberfest Docker Image

```bash
# Clone the official Oktoberfest repository
cd /path/to/your/projects
git clone --depth 1 https://github.com/wilhelm-lab/oktoberfest.git oktoberfest_repo

# Create hash.file (required by the Dockerfile)
cd oktoberfest_repo
git rev-parse HEAD > hash.file

# Build the Docker image
docker build --platform linux/amd64 -t oktoberfest:latest .
```

### 2. Install diann-runner Package

```bash
cd /path/to/diann_runner
source .venv/bin/activate.fish  # or activate.fish for fish shell
uv pip install -e .
```

This installs the `oktoberfest-docker` command-line tool.

## Usage

### Standalone: Generate Library from FASTA

#### Step 1: Create Oktoberfest Config

Create `oktoberfest_config.json`:

```json
{
    "type": "SpectralLibraryGeneration",
    "tag": "",
    "inputs": {
        "library_input": "your_database.fasta",
        "library_input_type": "fasta",
        "instrument_type": "QE"
    },
    "output": "./output",
    "models": {
        "intensity": "Prosit_2023_intensity_timsTOF",
        "irt": "Prosit_2019_irt"
    },
    "prediction_server": "koina.wilhelmlab.org:443",
    "ssl": true,
    "spectralLibraryOptions": {
        "fragmentation": "HCD",
        "collisionEnergy": 25,
        "precursorCharge": [2, 3],
        "minIntensity": 0.0005,
        "nrOx": 1,
        "batchsize": 10000,
        "format": "msp"
    },
    "fastaDigestOptions": {
        "fragmentation": "HCD",
        "digestion": "full",
        "missedCleavages": 1,
        "minLength": 7,
        "maxLength": 30,
        "enzyme": "trypsin",
        "specialAas": "KR",
        "db": "concat"
    }
}
```

#### Step 2: Run Oktoberfest

```bash
# Make sure you're in the directory with your FASTA file and config
source .venv/bin/activate.fish
oktoberfest-docker -c oktoberfest_config.json 2>&1 | tee oktoberfest.log
```

**Output:**
- Log file: `oktoberfest.log` (contains all stdout/stderr)
- Library files in `./output/` directory

### Generate Config from DIA-NN Config

If you have a DIA-NN workflow config, you can automatically generate an Oktoberfest config:

```bash
diann-koina-adapter \
  --diann-config out-DIANN/WU12345_predicted.speclib.config.json \
  --fasta database.fasta \
  --output oktoberfest_config.json \
  --instrument QE \
  --show-comparison
```

This will:
1. Read DIA-NN parameters (modifications, enzyme, charges, etc.)
2. Map them to Oktoberfest config format
3. Save to `oktoberfest_config.json`
4. Optionally show parameter comparison

## Testing

### Example Test Run

Location: `diann_runner/test_oktoberfest/`

```bash
cd diann_runner
mkdir -p test_oktoberfest
cd test_oktoberfest

# Copy a FASTA file
cp ../test_snakemake/ProteoBenchFASTA_MixedSpecies_HYE.fasta .

# Create config (see example above)
cat > oktoberfest_config.json << 'EOF'
{
    "type": "SpectralLibraryGeneration",
    "tag": "",
    "inputs": {
        "library_input": "ProteoBenchFASTA_MixedSpecies_HYE.fasta",
        "library_input_type": "fasta",
        "instrument_type": "QE"
    },
    "output": "./output",
    "models": {
        "intensity": "Prosit_2023_intensity_timsTOF",
        "irt": "Prosit_2019_irt"
    },
    "prediction_server": "koina.wilhelmlab.org:443",
    "ssl": true,
    "spectralLibraryOptions": {
        "fragmentation": "HCD",
        "collisionEnergy": 25,
        "precursorCharge": [2, 3],
        "minIntensity": 0.0005,
        "nrOx": 1,
        "batchsize": 10000,
        "format": "msp"
    },
    "fastaDigestOptions": {
        "fragmentation": "HCD",
        "digestion": "full",
        "missedCleavages": 1,
        "minLength": 7,
        "maxLength": 30,
        "enzyme": "trypsin",
        "specialAas": "KR",
        "db": "concat"
    }
}
EOF

# Run Oktoberfest
fish -c "source ../.venv/bin/activate.fish && oktoberfest-docker -c oktoberfest_config.json" 2>&1 | tee oktoberfest_run.log

# Monitor progress
tail -f oktoberfest_run.log
```

**Expected Output:**
```
2025-11-14 12:31:19 - INFO - Oktoberfest version 0.10.0
2025-11-14 12:31:20 - INFO - Digesting protein 10000
2025-11-14 12:31:22 - INFO - Digesting protein 20000
...
```

## Configuration Parameters

### Key Parameters Explained

#### Instrument Types
- `QE` - Q Exactive (Orbitrap)
- `Lumos` - Orbitrap Fusion Lumos
- `timsTOF` - Bruker timsTOF

#### Models
- **Intensity models**:
  - `Prosit_2023_intensity_timsTOF` - Latest model for timsTOF
  - `Prosit_2019_intensity` - Original Prosit model
- **iRT models**:
  - `Prosit_2019_irt` - Retention time prediction
  - `Prosit_2023_irt` - Latest RT model

#### Modifications
- `nrOx`: Number of oxidations (M) allowed (0, 1, 2, etc.)
- Fixed modifications are handled via Prosit models (e.g., Carbamidomethyl on C)

#### Digestion Options
- `enzyme`: trypsin, lysc, argc, aspn, etc.
- `missedCleavages`: Usually 0-2
- `minLength`/`maxLength`: Peptide length constraints
- `db`: "concat" for target-decoy, "target" for target-only

## Docker Wrapper Implementation

The `oktoberfest-docker` wrapper (`src/diann_runner/oktoberfest_docker.py`):

- Automatically detects Apple Silicon and uses `--platform linux/amd64`
- Mounts current directory to `/work` in container
- Sets `PYTHONPATH=/root` to access oktoberfest module
- Runs as root user (required for accessing `/root/oktoberfest`)
- Executes: `python -m oktoberfest -c <config>`

**Environment variables:**
- `OKTOBERFEST_DOCKER_IMAGE` - Override default image (default: `oktoberfest:latest`)
- `OKTOBERFEST_PLATFORM` - Override platform detection
- `OKTOBERFEST_EXTRA` - Additional docker run arguments

## Output Files

After successful execution, the `output/` directory contains:

```
output/
├── speclib.msp              # MSP format spectral library (if format: msp)
├── speclib.dlib             # DLIB format spectral library (if format: dlib)
├── speclib_prosit.hdf       # Internal HDF5 format
└── peptides.csv             # Peptide list with predicted features
```

**Note**: Supported output formats are `msp` and `dlib`. CSV format is NOT supported.

## Troubleshooting

### Common Issues

1. **"No module named oktoberfest"**
   - The Docker image wasn't built correctly
   - Rebuild: `docker build --platform linux/amd64 -t oktoberfest:latest .`

2. **"KeyError: 'models'"**
   - Config format is incorrect
   - Ensure you're using `SpectralLibraryGeneration` type
   - Must have `models` dict with `intensity` and `irt` keys

3. **Slow execution**
   - Oktoberfest needs to query Koina server for predictions
   - Large FASTA files take time (60k proteins ~10-30 minutes)
   - Consider reducing `batchsize` if memory issues occur

4. **Connection errors to koina.wilhelmlab.org**
   - Check internet connectivity
   - Koina server might be down (check status)
   - Try setting `"ssl": false` if certificate issues occur

### Checking Logs

All output is captured in the log file specified with `tee`:

```bash
# Real-time monitoring
tail -f oktoberfest_run.log

# Search for errors
grep -i error oktoberfest_run.log

# Check completion
tail -20 oktoberfest_run.log
```

## Snakemake Integration

The workflow now supports choosing between DIA-NN and Oktoberfest for library generation in `Snakefile.DIANN3step`.

### Configuration

Add to your `params.yml`:

```yaml
params:
  library_predictor: "oktoberfest"  # or "diann" (default)

  oktoberfest:
    instrument_type: "QE"  # QE, Lumos, or timsTOF
    intensity_model: "Prosit_2023_intensity_timsTOF"
    irt_model: "Prosit_2019_irt"
    prediction_server: "koina.wilhelmlab.org:443"
    ssl: true
    fragmentation: "HCD"
    collision_energy: 25
    min_intensity: 0.0005
    nr_ox: 1
    batchsize: 10000
    format: "msp"  # msp or dlib
    digestion: "full"
    enzyme: "trypsin"
    db: "concat"  # concat for target-decoy
```

### Workflow Behavior

**When `library_predictor: "diann"` (default)**:
1. `diann_generate_scripts` - Generates shell scripts for all 3 steps
2. `run_diann_step_a` - DIA-NN library search using deep learning predictor
3. `run_diann_step_b` - Quantification with refinement (uses DIA-NN library)
4. `run_diann_step_c` - Final quantification

**When `library_predictor: "oktoberfest"`**:
1. `diann_generate_scripts` - Generates shell scripts for Steps B and C only
2. `generate_oktoberfest_config` - Creates Oktoberfest config from DIA-NN params
3. `run_oktoberfest_library` - Generates spectral library using Koina/Prosit
4. `run_diann_step_b` - Quantification with refinement (uses Oktoberfest library)
5. `run_diann_step_c` - Final quantification

The workflow automatically:
- Translates DIA-NN parameters to Oktoberfest format
- Uses charge ranges from `min_pr_charge` and `max_pr_charge`
- Uses peptide length from `min_pep_len` and `max_pep_len`
- Uses missed cleavages and enzyme settings from DIA-NN config

## Files Created

- `src/diann_runner/oktoberfest_docker.py` - Docker wrapper script
- `src/diann_runner/koina_adapter.py` - Config translation (already existed)
- `pyproject.toml` - Added `oktoberfest-docker` console script entry
- `test_oktoberfest/` - Example test directory
- `OKTOBERFEST_INTEGRATION.md` - This documentation file

## References

- Oktoberfest: https://github.com/wilhelm-lab/oktoberfest
- Koina server: https://koina.wilhelmlab.org
- Prosit paper: https://www.nature.com/articles/s41592-019-0426-7
