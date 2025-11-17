# Oktoberfest Library Generation - Step-by-Step Documentation

## Date: 2025-11-13

## Overview

This document records the complete process of setting up and running Oktoberfest to generate a predicted spectral library using Koina/Prosit models as an alternative to DIA-NN's built-in predictor.

## Motivation

Compare DIA-NN's built-in deep learning predictor against Prosit models accessed via Koina server:
- **DIA-NN predictor**: Fast, integrated, optimized for DIA-NN workflow
- **Prosit via Koina**: Latest published models (Nature Methods 2019), GPU-accelerated, widely validated

## Step 1: Directory Setup

Created a separate directory for Oktoberfest at the same level as `diann_runner`:

```bash
cd /Users/wolski/projects/slurmworker/config/A386_DIANN_23
mkdir oktoberfest
cd oktoberfest
```

**Location:** `/Users/wolski/projects/slurmworker/config/A386_DIANN_23/oktoberfest/`

## Step 2: Python Environment Setup

Oktoberfest requires Python >=3.10 and <3.14 (due to numba dependency). Our main environment has Python 3.14, so we created a separate venv.

### Created Python 3.11 Virtual Environment

```bash
uv venv --python 3.11
```

**Result:**
- UV found Python 3.11.14 at `/opt/homebrew/opt/python@3.11/bin/python3.11`
- Virtual environment created at `.venv/`

### Activated Environment (Fish Shell)

```bash
source .venv/bin/activate.fish
```

## Step 3: Install Dependencies

### Install CMake (Required for llvmlite)

Oktoberfest depends on numba → llvmlite → cmake (build dependency).

```bash
brew install cmake
```

**Version installed:** CMake 4.1.2

### Install Oktoberfest

```bash
uv pip install oktoberfest
```

**Result:** Installed 67 packages including:
- `oktoberfest==0.10.0`
- `koinapy==0.0.10` (Koina API client)
- `spectrum-fundamentals==0.9.0`
- `spectrum-io==0.8.0`
- `pyopenms==3.4.0`
- `mokapot==0.10.0` (FDR estimation)
- `numba==0.62.1` (JIT compiler)
- `pandas==2.3.3`
- `numpy==2.3.4`
- Plus scientific stack (scipy, scikit-learn, matplotlib, etc.)

**Installation time:** ~4 minutes (downloading + building native extensions)

## Step 4: Copy FASTA File

Copied the same FASTA used in DIA-NN Step A:

```bash
cp ../diann_runner/ProteoBenchFASTA_MixedSpecies_HYE.fasta .
```

**FASTA details:**
- **File:** ProteoBenchFASTA_MixedSpecies_HYE.fasta
- **Species:** Human, Yeast, E. coli (mixed species)
- **Proteins:** 63,681 sequences
- **Source:** ProteoBench dataset PXD028735

## Step 5: Configuration File

### Understanding Oktoberfest Config Format

Oktoberfest uses **its own JSON config format**, different from DIA-NN's config. Key differences:

| Aspect | DIA-NN | Oktoberfest |
|--------|--------|-------------|
| Config format | JSON (workflow state) | JSON (job specification) |
| Modifications | UniMod CLI args | Structured dict in config |
| Models | Built-in predictor | Specify Koina models |
| Output format | .speclib | .msp (can convert) |

### Created config.json

**Location:** `/Users/wolski/projects/slurmworker/config/A386_DIANN_23/oktoberfest/config.json`

```json
{
    "type": "SpectralLibraryGeneration",
    "tag": "",
    "inputs": {
        "library_input": "ProteoBenchFASTA_MixedSpecies_HYE.fasta",
        "library_input_type": "fasta",
        "instrument_type": "QE"
    },
    "output": "./out",
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
        "minIntensity": 5e-4,
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

### Parameter Mapping: DIA-NN Step A ↔ Oktoberfest

| Parameter | DIA-NN Step A | Oktoberfest Config |
|-----------|---------------|-------------------|
| **FASTA file** | `ProteoBenchFASTA_MixedSpecies_HYE.fasta` | `inputs.library_input` |
| **Enzyme** | `--cut "K*,R*"` (Trypsin) | `fastaDigestOptions.enzyme: "trypsin"` |
| **Missed cleavages** | `--missed-cleavages 1` | `fastaDigestOptions.missedCleavages: 1` |
| **Min peptide length** | `--min-pep-len 6` | `fastaDigestOptions.minLength: 6` |
| **Max peptide length** | `--max-pep-len 30` | `fastaDigestOptions.maxLength: 30` |
| **Min precursor charge** | `--min-pr-charge 2` | `spectralLibraryOptions.precursorCharge: [2, ...]` |
| **Max precursor charge** | `--max-pr-charge 3` | `spectralLibraryOptions.precursorCharge: [..., 3]` |
| **Variable mod: Oxidation** | `--var-mod UniMod:35,15.994915,M` | `spectralLibraryOptions.nrOx: 1` |
| **Fixed mod: Carbamidomethyl** | `--unimod4` (C) | Default in Oktoberfest |
| **Instrument** | Orbitrap QE (implicit) | `inputs.instrument_type: "QE"` |
| **Fragmentation** | HCD (implicit) | `spectralLibraryOptions.fragmentation: "HCD"` |
| **Collision energy** | N/A (predicted) | `spectralLibraryOptions.collisionEnergy: 30` |
| **Precursor m/z range** | `--min-pr-mz 400 --max-pr-mz 1500` | Not directly specified |
| **Mass accuracy** | `--mass-acc 20 --mass-acc-ms1 15` | Not applicable (in silico) |
| **DDA mode** | `--dda` | Not applicable (library generation) |

### Important Configuration Notes

1. **Tag field:** Initially set to `"WU_TEST_koina"` but caused error:
   - Error: "tag wu_test_koina requires TMT model, but Prosit_2020_intensity_HCD is incompatible"
   - **Fix:** Changed `"tag"` to empty string `""`
   - **Reason:** Oktoberfest interprets lowercase tag strings as TMT labels

2. **Modifications:**
   - `nrOx: 1` = Allow up to 1 oxidation on Methionine (M)
   - Carbamidomethyl on Cysteine (C) is default and not explicitly set

3. **Prediction server:**
   - Using public Koina server: `koina.wilhelmlab.org:443`
   - SSL enabled for secure communication
   - No API key required for public server

4. **Output format:**
   - MSP (NIST format) is standard spectral library format
   - Will need conversion to DIA-NN's `.speclib` format using `diann --lib --convert`

## Step 6: Run Oktoberfest

### Command Executed

```bash
cd /Users/wolski/projects/slurmworker/config/A386_DIANN_23/oktoberfest
fish -c "source .venv/bin/activate.fish && oktoberfest -c config.json" 2>&1 | tee oktoberfest.log.txt
```

**Run in background:** Yes (using `run_in_background: true`)

**Started:** 2025-11-13 17:09:36

### Initial Output (First 30 seconds)

```
2025-11-13 17:09:36,468 - INFO - oktoberfest.runner::run_job Oktoberfest version 0.10.0
Copyright 2025, Wilhelmlab at Technical University of Munich

2025-11-13 17:09:37,386 - INFO - spectrum_io.spectral_library.digest::get_peptide_to_protein_map Digesting protein 10000
2025-11-13 17:09:38,247 - INFO - spectrum_io.spectral_library.digest::get_peptide_to_protein_map Digesting protein 20000
2025-11-13 17:09:39,136 - INFO - spectrum_io.spectral_library.digest::get_peptide_to_protein_map Digesting protein 30000
2025-11-13 17:09:40,866 - INFO - spectrum_io.spectral_library.digest::get_peptide_to_protein_map Digesting protein 50000
2025-11-13 17:09:41,333 - INFO - spectrum_io.spectral_library.digest::get_peptide_to_protein_map Digesting protein 60000
```

**Status:** Running, currently digesting FASTA file

**Progress:** Processing ~10,000 proteins per second

**Expected phases:**
1. **FASTA digestion** - Generate theoretical peptides (currently running)
2. **Prosit intensity prediction** - Query Koina server for fragment intensities
3. **Prosit iRT prediction** - Query Koina server for retention times
4. **Library assembly** - Combine predictions into MSP format
5. **Write output** - Save to `./out/` directory

## Step 7: Monitor Progress

### Real-time Monitoring

```bash
tail -f oktoberfest.log.txt
```

### Check Status Programmatically

Background process ID: `c33449`

```bash
# Via Claude Code's BashOutput tool
BashOutput(bash_id="c33449")
```

## Expected Outputs

### Output Directory Structure

```
out/
├── library.msp              # Main spectral library (MSP format)
├── library_metadata.csv     # Peptide metadata
└── [processing logs]        # Intermediate files
```

### Library Statistics (Expected)

Based on DIA-NN Step A results:
- **Input proteins:** 63,681
- **Expected peptides:** ~500,000 - 1,000,000 (with charge states)
- **Expected precursors:** ~1,000,000 - 2,000,000 (charges 2-3, oxidation variants)

**Note:** Oktoberfest may generate fewer precursors than DIA-NN if:
- Different decoy strategy
- Different handling of protein isoforms
- Stricter filtering criteria

## Comparison to DIA-NN Step A

### DIA-NN Step A Results (Reference)

- **Runtime:** 17:40 minutes (1,060 seconds)
- **Generated precursors:** 4,018,631
- **Output file size:** 949 MB (.speclib format)
- **Computation:** Local (Docker container, 12 threads, 32GB RAM)

### Oktoberfest Expected Performance

- **Runtime:** TBD (likely 20-60 minutes depending on Koina server load)
- **Generated precursors:** TBD (estimate: 1-2M, fewer due to different strategies)
- **Output file size:** TBD (MSP is text format, may be larger)
- **Computation:** Hybrid (local digest + Koina server predictions)

**Factors affecting Oktoberfest speed:**
- ✅ FASTA digestion is fast (local)
- ⚠️  Koina predictions depend on server load and network latency
- ⚠️  Batch size = 10,000 precursors per request
- ✅ Parallel requests possible (not configured)

## Next Steps (After Completion)

### 1. Verify Output

```bash
cd /Users/wolski/projects/slurmworker/config/A386_DIANN_23/oktoberfest
ls -lh out/
head -n 50 out/library.msp
```

### 2. Convert MSP to DIA-NN Format

```bash
cd ../diann_runner
diann-docker --lib ../oktoberfest/out/library.msp --convert
# Output: library.speclib
```

### 3. Use Separate Config to Avoid Directory Conflicts

**Important:** To prevent overwriting DIA-NN predictor results, use a separate config with different output directories.

**Created:** `workflow_koina.config.json` with:
- `output_base_dir: "out-KOINA"` (instead of `out-DIANN`)
- `temp_dir_base: "temp-KOINA"` (instead of `temp-DIANN`)

This ensures:
- DIA-NN predictor results → `out-DIANN_quantB/`, `out-DIANN_quantC/`
- Koina/Oktoberfest results → `out-KOINA_quantB/`, `out-KOINA_quantC/`

### 4. Run DIA-NN Step B with Oktoberfest Library

```bash
cd ../diann_runner
diann-workflow quantification-refinement \
  --config workflow_koina.config.json \
  --predicted-lib ../oktoberfest/out/library.speclib \
  --raw-files LFQ_Orbitrap_DDA_Condition_A_Sample_Alpha_01.mzML \
  --raw-files LFQ_Orbitrap_DDA_Condition_A_Sample_Alpha_02.mzML \
  --raw-files LFQ_Orbitrap_DDA_Condition_A_Sample_Alpha_03.mzML \
  --raw-files LFQ_Orbitrap_DDA_Condition_B_Sample_Alpha_01.mzML \
  --raw-files LFQ_Orbitrap_DDA_Condition_B_Sample_Alpha_02.mzML \
  --raw-files LFQ_Orbitrap_DDA_Condition_B_Sample_Alpha_03.mzML
```

**Output:** `out-KOINA_quantB/` directory with:
- `WU_TEST_refined.parquet` - Refined library
- `WU_TEST_reportB.tsv` - Quantification results
- `WU_TEST_reportB.pg_matrix.tsv` - Protein group matrix
- `WU_TEST_reportB.pr_matrix.tsv` - Precursor matrix
- Config saved to `WU_TEST_refined.parquet.config.json`

### 4. Compare Results

**Metrics to compare:**
- Number of identified precursors
- Number of identified proteins
- Quantification reproducibility (CV between replicates)
- Library size (predicted vs refined)
- Runtime (DIA-NN predictor vs Koina/Prosit)

**Expected location of results:**
- **DIA-NN predictor:** `diann_runner/out-DIANN_quantB/WU_TEST_reportB.tsv`
- **Koina predictor:** `diann_runner/out-DIANN_quantB_koina/WU_TEST_reportB.tsv`

## Troubleshooting

### Issue 1: Python Version Incompatibility

**Error:** `Cannot install on Python version 3.14.0; only versions >=3.10,<3.14 are supported`

**Solution:** Created separate venv with Python 3.11 using `uv venv --python 3.11`

### Issue 2: Missing CMake

**Error:** `FileNotFoundError: [Errno 2] No such file or directory: 'cmake'`

**Cause:** llvmlite (numba dependency) requires cmake to build

**Solution:** `brew install cmake`

### Issue 3: TMT Tag Error

**Error:** `You specified the tag wu_test_koina but the chosen intensity model Prosit_2020_intensity_HCD is incompatible`

**Cause:** Oktoberfest interprets lowercase tag as TMT label (e.g., "tmt6plex")

**Solution:** Changed `"tag": "WU_TEST_koina"` to `"tag": ""`

## Key Insights

1. **Oktoberfest uses separate config format** - Not compatible with DIA-NN's workflow config
2. **Prosit models accessed via Koina** - Network-based predictions vs local DIA-NN predictor
3. **MSP format output** - Requires conversion step for DIA-NN compatibility
4. **Different peptide generation strategies** - May result in different library sizes
5. **Fixed modifications implicit** - Carbamidomethyl (C) is default in proteomics

## References

- **Oktoberfest paper:** Picciani et al., PROTEOMICS 2024 - https://doi.org/10.1002/pmic.202300112
- **Koina paper:** Nature Communications 2025 - https://www.nature.com/articles/s41467-025-64870-5
- **Prosit paper:** Gessulat et al., Nature Methods 2019 - https://doi.org/10.1038/s41592-019-0426-7
- **Oktoberfest docs:** https://oktoberfest.readthedocs.io/
- **Koina server:** https://koina.wilhelmlab.org/
- **GitHub:** https://github.com/wilhelm-lab/oktoberfest

## Files Created

1. `/Users/wolski/projects/slurmworker/config/A386_DIANN_23/oktoberfest/config.json` - Oktoberfest configuration
2. `/Users/wolski/projects/slurmworker/config/A386_DIANN_23/oktoberfest/oktoberfest.log.txt` - Execution log
3. `/Users/wolski/projects/slurmworker/config/A386_DIANN_23/oktoberfest/README.md` - Setup and usage guide
4. `/Users/wolski/projects/slurmworker/config/A386_DIANN_23/oktoberfest/OKTOBERFEST.md` - This document

## Current Status

**Status:** ✅ Running successfully

**Phase:** FASTA digestion (proteins 60,000+)

**Next phase:** Koina predictions (intensity + iRT)

**Monitoring:** `tail -f oktoberfest.log.txt`
