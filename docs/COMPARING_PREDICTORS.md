# Comparing DIA-NN vs Koina/Oktoberfest Predictors

This document explains how to run parallel workflows with different library predictors and avoid output directory conflicts.

## Problem

When running DIA-NN workflows with different predicted libraries (DIA-NN built-in vs Koina/Oktoberfest), we need separate output directories to:
1. **Prevent overwriting results** from different predictors
2. **Enable side-by-side comparison** of quantification results
3. **Track which predictor generated which outputs**

## Solution: Separate Config Files

The workflow uses `output_base_dir` and `temp_dir_base` parameters in the config to control output locations:

```json
{
  "output_base_dir": "out-DIANN",    // → out-DIANN_libA, out-DIANN_quantB, out-DIANN_quantC
  "temp_dir_base": "temp-DIANN"      // → temp-DIANN_libA, temp-DIANN_quantB, temp-DIANN_quantC
}
```

By creating separate configs with different base directories, workflows run independently.

## Directory Structure

### Workflow 1: DIA-NN Built-in Predictor

**Config:** `out-DIANN_libA/WU_TEST_predicted.speclib.config.json`

```
out-DIANN_libA/
├── WU_TEST_predicted.speclib         # DIA-NN predicted library
└── WU_TEST_predicted.speclib.config.json

out-DIANN_quantB/
├── WU_TEST_refined.parquet           # Refined library
├── WU_TEST_reportB.tsv               # Quantification results
├── WU_TEST_reportB.pg_matrix.tsv     # Protein matrix
└── WU_TEST_refined.parquet.config.json

temp-DIANN_libA/
temp-DIANN_quantB/
```

### Workflow 2: Koina/Oktoberfest Predictor

**Config:** `workflow_koina.config.json`

```
out-KOINA_quantB/
├── WU_TEST_refined.parquet           # Refined library (from Oktoberfest)
├── WU_TEST_reportB.tsv               # Quantification results
├── WU_TEST_reportB.pg_matrix.tsv     # Protein matrix
└── WU_TEST_refined.parquet.config.json

temp-KOINA_quantB/
```

**Note:** No `out-KOINA_libA/` directory because Oktoberfest generates the predicted library externally.

## Step-by-Step Workflow

### Workflow 1: DIA-NN Predictor (Already Completed)

```bash
# Step A: Generate predicted library with DIA-NN
diann-workflow library-search \
  --fasta ProteoBenchFASTA_MixedSpecies_HYE.fasta \
  --workunit-id WU_TEST \
  --var-mods "35,15.994915,M"

# Step B: Quantification with refinement
diann-workflow quantification-refinement \
  --config out-DIANN_libA/WU_TEST_predicted.speclib.config.json \
  --predicted-lib out-DIANN_libA/WU_TEST_predicted.predicted.speclib \
  --raw-files *.mzML
```

**Results:** `out-DIANN_quantB/WU_TEST_reportB.tsv`

### Workflow 2: Koina/Oktoberfest Predictor (To Be Run)

```bash
# Step 0: Generate predicted library with Oktoberfest (running in ../oktoberfest/)
cd ../oktoberfest
oktoberfest -c config.json
# Output: out/library.msp

# Convert MSP to DIA-NN format
cd ../diann_runner
diann-docker --lib ../oktoberfest/out/library.msp --convert
# Output: ../oktoberfest/out/library.speclib

# Step B: Quantification with refinement using Koina library
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

**Results:** `out-KOINA_quantB/WU_TEST_reportB.tsv`

## Config File Details

### workflow_koina.config.json

```json
{
  "workunit_id": "WU_TEST",
  "output_base_dir": "out-KOINA",      ← Changed from "out-DIANN"
  "temp_dir_base": "temp-KOINA",       ← Changed from "temp-DIANN"
  "diann_bin": "diann-docker",
  "var_mods": [["35", "15.994915", "M"]],
  "threads": 12,
  "qvalue": 0.01,
  "min_pep_len": 6,
  "max_pep_len": 30,
  "min_pr_charge": 2,
  "max_pr_charge": 3,
  "min_pr_mz": 400,
  "max_pr_mz": 1500,
  "missed_cleavages": 1,
  "cut": "K*,R*",
  "mass_acc": 20,
  "mass_acc_ms1": 15,
  "verbose": 1,
  "pg_level": 0,
  "is_dda": true,
  "unimod4": true,
  "met_excision": true
}
```

**Key changes from DIA-NN config:**
- `"output_base_dir": "out-KOINA"` (instead of `"out-DIANN"`)
- `"temp_dir_base": "temp-KOINA"` (instead of `"temp-DIANN"`)

All other parameters remain identical to ensure fair comparison.

## Comparison Metrics

After both workflows complete, compare:

| Metric | DIA-NN Predictor | Koina/Oktoberfest |
|--------|------------------|-------------------|
| **File path** | `out-DIANN_quantB/WU_TEST_reportB.tsv` | `out-KOINA_quantB/WU_TEST_reportB.tsv` |
| **Precursors identified** | TBD | TBD |
| **Proteins identified** | TBD | TBD |
| **Library size (predicted)** | 4,018,631 precursors | TBD |
| **Library size (refined)** | 61,109 target precursors | TBD |
| **Quantification runtime** | ~121 min (6 files) | TBD |
| **Total workflow runtime** | Step A: 17:40 min<br/>Step B: 121 min | Oktoberfest: TBD<br/>Step B: TBD |

### Analysis Commands

```bash
# Count precursors identified at 1% FDR
wc -l out-DIANN_quantB/WU_TEST_reportB.tsv
wc -l out-KOINA_quantB/WU_TEST_reportB.tsv

# Count proteins in matrix
wc -l out-DIANN_quantB/WU_TEST_reportB.pg_matrix.tsv
wc -l out-KOINA_quantB/WU_TEST_reportB.pg_matrix.tsv

# Compare library sizes
ls -lh out-DIANN_quantB/WU_TEST_refined.parquet
ls -lh out-KOINA_quantB/WU_TEST_refined.parquet

# Check logs for runtime
grep "Elapsed time" out-DIANN_quantB/diann_quantB.log.txt
grep "Elapsed time" out-KOINA_quantB/diann_quantB.log.txt
```

## Alternative: Using Different Workunit IDs

Instead of changing `output_base_dir`, you could also use different `workunit_id` values:

```json
// DIA-NN predictor
{"workunit_id": "WU_TEST_DIANN", "output_base_dir": "out-DIANN"}

// Koina predictor
{"workunit_id": "WU_TEST_KOINA", "output_base_dir": "out-DIANN"}
```

**Pros:**
- All outputs in same directory structure
- Easy to compare by workunit ID

**Cons:**
- Harder to visually distinguish predictor workflows
- Mixing results in same base directory

**Recommendation:** Use separate `output_base_dir` for clearer organization.

## Future Enhancement: CLI Parameter

Currently, `output_base_dir` can only be changed via config file. A future enhancement could add:

```bash
diann-workflow quantification-refinement \
  --config workflow.config.json \
  --output-dir out-KOINA \           # Override config
  --predicted-lib library.speclib \
  --raw-files *.mzML
```

This would allow dynamic output directory specification without modifying config files.

## Implementation in workflow.py

The `output_base_dir` parameter is defined in `DiannWorkflow.__init__()`:

```python
def __init__(
    self,
    workunit_id: str,
    output_base_dir: str = 'out-DIANN',  # ← Controls output location
    var_mods: List[Tuple[str, str, str]] = None,
    # ... other parameters
):
```

It's used to construct directory names:

```python
self.lib_dir = f"{output_base_dir}_libA"      # e.g., out-KOINA_libA
self.quant_b_dir = f"{output_base_dir}_quantB"  # e.g., out-KOINA_quantB
self.quant_c_dir = f"{output_base_dir}_quantC"  # e.g., out-KOINA_quantC
```

## Best Practices

1. **Use descriptive base directory names** that indicate the predictor:
   - `out-DIANN` for DIA-NN built-in predictor
   - `out-KOINA` for Koina/Prosit models
   - `out-ALPHAPEPT` for AlphaPept models
   - `out-MS2PIP` for MS2PIP models

2. **Match temp directory naming** to output directory:
   - `temp-DIANN` with `out-DIANN`
   - `temp-KOINA` with `out-KOINA`

3. **Keep workunit_id consistent** across predictor comparisons for easier tracking

4. **Document predictor parameters** in config or README to track what was compared

## Summary

✅ **Problem solved:** Use separate config files with different `output_base_dir` values to prevent conflicts

✅ **Created:** `workflow_koina.config.json` with `output_base_dir: "out-KOINA"`

✅ **Result:** DIA-NN and Koina workflows can run independently without overwriting results

✅ **Next:** Run Oktoberfest → Convert library → Run Step B with Koina config → Compare results
