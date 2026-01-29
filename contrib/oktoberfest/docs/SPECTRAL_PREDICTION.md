# Spectral Library Prediction with Koina/Oktoberfest

This guide covers using Koina/Oktoberfest for spectral library generation as an alternative to DIA-NN's built-in predictor.

## Overview

**Koina** is a prediction server/API providing access to state-of-the-art MS prediction models (Prosit, AlphaPept, MS2PIP, etc.).

**Oktoberfest** is a Python library that orchestrates predictions via Koina to generate spectral libraries for mass spectrometry analysis.

**Integration:** This package provides Docker wrapper and parameter translation to seamlessly use Oktoberfest-generated libraries with the DIA-NN workflow.

### Benefits vs DIA-NN's Built-in Predictor

**Use Koina/Oktoberfest when:**
- ✅ Instrument-specific predictions needed (timsTOF, Astral, etc.)
- ✅ Non-standard digestion (LysC, AspN, etc.)
- ✅ Complex PTM analysis requiring specialized models
- ✅ Benchmarking different prediction approaches
- ✅ Access to latest published models

**Use DIA-NN's built-in predictor when:**
- ✅ Standard tryptic digestion on Orbitrap HCD
- ✅ Simplicity and speed are priorities
- ✅ Integrated workflow without external dependencies
- ✅ Already proven performance for your use case

### Available Models

#### Fragment Intensity Prediction

| Model | Best For | Notes |
|-------|----------|-------|
| `Prosit_2020_intensity_HCD` | Orbitrap HCD | Most common, well-validated |
| `Prosit_2023_intensity_timsTOF` | timsTOF | For Bruker instruments |
| `AlphaPept_ms2_generic` | Generic | Cross-instrument |

#### Retention Time Prediction

| Model | Best For |
|-------|----------|
| `Prosit_2019_irt` | iRT scale (normalized RT) |
| `Deeplc` | Chromatography-specific |

#### Ion Mobility Prediction

| Model | Best For |
|-------|----------|
| `Prosit_2023_IM` | timsTOF CCS prediction |

## Setup

### 1. Build Oktoberfest Docker Image

```bash
# Clone the official Oktoberfest repository
git clone --depth 1 https://github.com/wilhelm-lab/oktoberfest.git oktoberfest_repo
cd oktoberfest_repo

# Create hash.file (required by Dockerfile)
git rev-parse HEAD > hash.file

# Build Docker image (~30-60 minutes, 4GB)
docker build --platform linux/amd64 -t oktoberfest:latest .
```

### 2. Install diann-runner Package

```bash
cd /path/to/diann_runner
source .venv/bin/activate.fish
uv pip install -e .
```

This installs the `oktoberfest-docker` command-line tool.

## Configuration

### Parameter Mapping: DIA-NN ↔ Oktoberfest

The package automatically translates between DIA-NN and Oktoberfest config formats:

| DIA-NN Parameter | Oktoberfest Parameter | Notes |
|------------------|----------------------|-------|
| `cut: "K*,R*"` | `enzyme: "trypsin"` | Enzyme detection |
| `missed_cleavages: 1` | `missedCleavages: 1` | Direct mapping |
| `min_pep_len: 6` | `minLength: 6` | Peptide length |
| `max_pep_len: 30` | `maxLength: 30` | Peptide length |
| `min_pr_charge: 2` | `precursorCharge: [2, ...]` | Charge states |
| `max_pr_charge: 3` | `precursorCharge: [..., 3]` | Charge states |
| `var_mods: [["35", ...]]` | `nrOx: 1` | Oxidation count |
| Built-in predictor | `models.intensity: "Prosit_..."` | Model selection |

### Automatic Config Generation

Generate Oktoberfest config from existing DIA-NN config:

```bash
diann-koina-adapter \
  --diann-config out-DIANN_libA/WU123_predicted.speclib.config.json \
  --fasta database.fasta \
  --output oktoberfest_config.json \
  --instrument QE \
  --show-comparison
```

**Output example:**
```
=== Config Parameter Mapping ===

Parameter                 DIA-NN                         Oktoberfest
-------------------------------------------------------------------------------------
Enzyme                    K*,R*                          trypsin
Missed cleavages          1                              1
Peptide length            6-30                           6-30
Precursor charges         2-3                            2-3
Variable mods             UniMod:35                      nrOx: 1
Intensity model           Built-in predictor             Prosit_2020_intensity_HCD
RT model                  Built-in predictor             Prosit_2019_irt
```

### Manual Config Creation

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
        "intensity": "Prosit_2020_intensity_HCD",
        "irt": "Prosit_2019_irt"
    },
    "prediction_server": "koina.wilhelmlab.org:443",
    "ssl": true,
    "spectralLibraryOptions": {
        "fragmentation": "HCD",
        "collisionEnergy": 30,
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
        "minLength": 6,
        "maxLength": 30,
        "enzyme": "trypsin",
        "specialAas": "KR",
        "db": "concat"
    }
}
```

### Key Configuration Parameters

**Instrument Types:**
- `QE` - Q Exactive (Orbitrap)
- `Lumos` - Orbitrap Fusion Lumos
- `timsTOF` - Bruker timsTOF

**Modifications:**
- `nrOx`: Number of oxidations (M) allowed
- Fixed mods (Carbamidomethyl on C) are implicit

**Important Notes:**
1. **Tag field:** Leave empty (`""`). Lowercase strings are interpreted as TMT labels
2. **Output format:** Use `"msp"` or `"dlib"` (CSV not supported)
3. **Prediction server:** Public Koina at `koina.wilhelmlab.org:443` (no API key needed)

## Usage

### Standalone: Generate Library from FASTA

```bash
# Create config (see above) or generate from DIA-NN config
diann-koina-adapter \
  --diann-config out-DIANN_libA/WU123_predicted.speclib.config.json \
  --fasta database.fasta \
  --output oktoberfest_config.json

# Run Oktoberfest
source .venv/bin/activate.fish
oktoberfest-docker -c oktoberfest_config.json 2>&1 | tee oktoberfest.log
```

**Expected output:**
```
2025-11-14 12:31:19 - INFO - Oktoberfest version 0.10.0
2025-11-14 12:31:20 - INFO - Digesting protein 10000
2025-11-14 12:31:22 - INFO - Digesting protein 20000
...
```

**Phases:**
1. FASTA digestion (~10,000 proteins/second)
2. Prosit intensity prediction (Koina server queries)
3. Prosit iRT prediction (Koina server queries)
4. Library assembly (MSP format)
5. Write output to `./output/` directory

### Integration with DIA-NN Workflow

Once you have an Oktoberfest library, use it for Steps B and C:

```bash
# Create workflow config for Steps B/C
diann-workflow create-config \
  --output workflow_config.json \
  --workunit-id WU123 \
  --threads 32 \
  --var-mods "35,15.994915,M"

# Step B: Quantification with refinement
diann-workflow quantification-refinement \
  --config workflow_config.json \
  --predicted-lib output/speclib.msp \
  --raw-files *.mzML

# Step C: Final quantification (if needed)
diann-workflow final-quantification \
  --config out-DIANN_quantB/WU123_refined.speclib.config.json \
  --refined-lib out-DIANN_quantB/WU123_refined.parquet \
  --raw-files *.mzML
```

### Complete Example Workflow

```bash
# 1. Generate library with Oktoberfest
oktoberfest-docker -c oktoberfest_config.json 2>&1 | tee oktoberfest.log

# 2. Create DIA-NN workflow config
diann-workflow create-config \
  --output workflow_config.json \
  --workunit-id WU123 \
  --threads 32 \
  --var-mods "35,15.994915,M"

# 3. Run quantification with Oktoberfest library
diann-workflow quantification-refinement \
  --config workflow_config.json \
  --predicted-lib output/speclib.msp \
  --raw-files sample*.mzML

# 4. Results in out-DIANN_quantB/WU123_reportB.tsv
```

## Snakemake Integration

The Snakefile supports choosing between DIA-NN and Oktoberfest for library generation.

### Configuration in params.yml

```yaml
params:
  library_predictor: "oktoberfest"  # or "diann" (default)

  oktoberfest:
    instrument_type: "QE"  # QE, Lumos, or timsTOF
    intensity_model: "Prosit_2020_intensity_HCD"
    irt_model: "Prosit_2019_irt"
    prediction_server: "koina.wilhelmlab.org:443"
    ssl: true
    fragmentation: "HCD"
    collision_energy: 30
    min_intensity: 0.0005
    nr_ox: 1
    batchsize: 10000
    format: "msp"
    digestion: "full"
    enzyme: "trypsin"
    db: "concat"
```

### Workflow Behavior

**With `library_predictor: "diann"` (default):**
1. Generate scripts for all 3 steps
2. Run DIA-NN Step A (library search)
3. Run DIA-NN Step B (quantification + refinement)
4. Run DIA-NN Step C (final quantification)

**With `library_predictor: "oktoberfest"`:**
1. Generate scripts for Steps B and C only
2. Generate Oktoberfest config from DIA-NN params
3. Run Oktoberfest library generation
4. Run DIA-NN Step B with Oktoberfest library
5. Run DIA-NN Step C (final quantification)

The workflow automatically translates all DIA-NN parameters (charges, lengths, enzyme, modifications) to Oktoberfest format.

## Docker Wrapper Implementation

The `oktoberfest-docker` wrapper:
- Detects Apple Silicon and uses `--platform linux/amd64`
- Mounts current directory to `/work` in container
- Sets `PYTHONPATH=/root` for oktoberfest module access
- Executes: `python -m oktoberfest -c <config>`

**Environment variables:**
- `OKTOBERFEST_DOCKER_IMAGE` - Override image (default: `oktoberfest:latest`)
- `OKTOBERFEST_PLATFORM` - Override platform detection
- `OKTOBERFEST_EXTRA` - Additional docker run arguments

## Output Files

After successful execution:

```
output/
├── speclib.msp              # MSP format spectral library
├── speclib.dlib             # DLIB format (if configured)
├── speclib_prosit.hdf       # Internal HDF5 format
└── peptides.csv             # Peptide list with predicted features
```

## Troubleshooting

### Common Issues

**1. "No module named oktoberfest"**
- Docker image wasn't built correctly
- Rebuild: `docker build --platform linux/amd64 -t oktoberfest:latest .`

**2. "KeyError: 'models'"**
- Config format incorrect
- Ensure `type: "SpectralLibraryGeneration"` is set
- Must have `models` dict with `intensity` and `irt` keys

**3. Tag TMT error**
- Don't use lowercase tag strings (interpreted as TMT labels)
- Use empty string: `"tag": ""`

**4. Slow execution**
- Oktoberfest queries Koina server for predictions
- Large FASTA files take 10-60 minutes (60k proteins)
- Consider reducing `batchsize` if memory issues occur

**5. Connection errors to koina.wilhelmlab.org**
- Check internet connectivity
- Koina server might be down
- Try `"ssl": false` if certificate issues occur

### Performance Comparison

**DIA-NN built-in predictor:**
- Runtime: ~15-20 minutes for 60k proteins
- Output: 4M precursors, 950MB .speclib
- Computation: Local (Docker, 12 threads)

**Oktoberfest/Koina:**
- Runtime: ~20-60 minutes for 60k proteins
- Output: 1-2M precursors (fewer, different strategy)
- Computation: Hybrid (local digest + Koina predictions)

**Factors affecting speed:**
- ✅ FASTA digestion is fast (local)
- ⚠️ Koina predictions depend on server load/network latency
- ⚠️ Batch size affects memory and network usage
- ✅ Parallel requests possible (not configured by default)

### Monitoring Progress

```bash
# Real-time monitoring
tail -f oktoberfest.log

# Search for errors
grep -i error oktoberfest.log

# Check completion
tail -20 oktoberfest.log
```

## References

- **Oktoberfest paper:** Picciani et al., PROTEOMICS 2024 - https://doi.org/10.1002/pmic.202300112
- **Koina paper:** Nature Communications 2025 - https://www.nature.com/articles/s41467-025-64870-5
- **Prosit paper:** Gessulat et al., Nature Methods 2019 - https://doi.org/10.1038/s41592-019-0426-7
- **Oktoberfest docs:** https://oktoberfest.readthedocs.io/
- **Koina server:** https://koina.wilhelmlab.org/
- **GitHub:** https://github.com/wilhelm-lab/oktoberfest
