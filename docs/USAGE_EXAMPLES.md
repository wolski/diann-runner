# DIA-NN Workflow - Usage Guide

This guide explains how to use the `DiannWorkflow` python class to generate DIA-NN scripts. This is primarily used internally by the Snakemake workflow, but can also be used for custom scripting.

## Quick Reference

### Basic Setup
```python
from diann_runner.workflow import DiannWorkflow

workflow = DiannWorkflow(
    workunit_id='WU123',
    var_mods=[('35', '15.994915', 'M')],  # Oxidation
    threads=64,
    qvalue=0.01,
    scan_window=0, # 0 = auto
)
```

### Three Common Patterns

**1. Simple: Same files everywhere**
```python
files = ['s1.mzML', 's2.mzML', 's3.mzML']

workflow.generate_all_scripts(
    fasta_path='/db.fasta',
    raw_files_step_b=files,
    raw_files_step_c=files  # Optional - defaults to step_b
)
```

**2. Fast: Subset library → Full quantification**
```python
workflow.generate_all_scripts(
    fasta_path='/db.fasta',
    raw_files_step_b=['s1.mzML', 's2.mzML'],      # 2 files: FAST
    raw_files_step_c=['s1.mzML', ..., 's50.mzML'], # 50 files: FULL
    quantify_step_b=False  # Skip quantification in B
)
```

**3. Manual: Full control**
```python
# Generate each step individually
workflow.generate_step_a_library(fasta_path='/db.fasta')
workflow.generate_step_b_quantification_with_refinement(raw_files=['pilot1.mzML', 'pilot2.mzML'], quantify=False)
workflow.generate_step_c_final_quantification(raw_files=all_files)
```

### Output Structure

```
out-DIANN_libA/
  └── WU123_predicted.speclib        # Step A output

out-DIANN_quantB/
  ├── WU123_reportB.tsv              # Step B report
  ├── WU123_refined.speclib          # Step B library
  ├── WU123_reportB.pg_matrix.tsv    # Protein matrix
  └── diann_quantB.log.txt           # Log

out-DIANN_quantC/
  ├── WU123_reportC.tsv              # Final report ⭐
  ├── WU123_final.speclib            # Final library
  ├── WU123_reportC.pg_matrix.tsv    # Protein matrix ⭐
  ├── WU123_reportC.pr_matrix.tsv    # Precursor matrix ⭐
  └── diann_quantC.log.txt           # Log
```

### Run the Scripts

```bash
bash step_A_library_search.sh
bash step_B_quantification_refinement.sh
bash step_C_final_quantification.sh
```

---

## Overview

The `DiannWorkflow` class provides maximum flexibility by separating:
- **Shared parameters** (in `__init__`): instrument settings, modifications, threading, etc.
- **Step-specific parameters** (in method calls): FASTA, raw files lists

### Key Design Decisions

**1. FASTA is Step A only**
FASTA is only needed for library generation (Step A), not for quantification (Steps B & C).

**2. Different raw files for B vs C**
You can use **different file lists** for:
- **Step B**: Small subset for fast library refinement
- **Step C**: Full dataset for comprehensive quantification

**3. Optional quantification in Step B**
Use `quantify=False` in Step B to skip matrices generation and only build the refined library (faster).

## Detailed Usage Patterns

### Pattern 1: Standard Workflow (Same Files Throughout)

```python
from diann_runner.workflow import DiannWorkflow

# Initialize with shared parameters
workflow = DiannWorkflow(
    workunit_id='WU336182',
    output_base_dir='out-DIANN',
    var_mods=[('35', '15.994915', 'M')],  # Oxidation
    threads=64,
    qvalue=0.01,
)

# All files
all_files = [
    'sample01.mzML',
    'sample02.mzML',
    'sample03.mzML',
    'sample04.mzML',
]

# Generate all three scripts
workflow.generate_all_scripts(
    fasta_path='/path/to/database.fasta',
    raw_files_step_b=all_files,
    raw_files_step_c=all_files,  # Can omit - defaults to step_b files
)
```

**Result:**
- Step A: Generates predicted library from FASTA
- Step B: Quantifies all 4 files + builds refined library
- Step C: Re-quantifies all 4 files with refined library

---

### Pattern 2: Fast Library Building (Subset → Full)

```python
# Use subset to build library quickly
subset_files = [
    'sample01.mzML',
    'sample02.mzML',
]

# Then quantify all files
all_files = [
    'sample01.mzML',
    'sample02.mzML',
    'sample03.mzML',
    'sample04.mzML',
    'sample05.mzML',
    'sample06.mzML',
]

workflow.generate_all_scripts(
    fasta_path='/path/to/database.fasta',
    raw_files_step_b=subset_files,      # Just 2 files
    raw_files_step_c=all_files,         # All 6 files
    quantify_step_b=True                # Still quantify the subset
)
```

**Result:**
- Step A: Generates predicted library
- Step B: Quantifies 2 files + builds refined library (FAST)
- Step C: Quantifies all 6 files with refined library

**Benefit:** Faster library refinement, comprehensive quantification

---

### Pattern 3: Library-Only Building (No Step B Quantification)

```python
# Just use a few files to build the refined library
library_files = [
    'representative01.mzML',
    'representative02.mzML',
]

# All samples for final quantification
analysis_files = [
    'sample01.mzML',
    'sample02.mzML',
    'sample03.mzML',
    # ... 20+ more files
]

workflow.generate_all_scripts(
    fasta_path='/path/to/database.fasta',
    raw_files_step_b=library_files,     # Small set
    raw_files_step_c=analysis_files,    # Large set
    quantify_step_b=False               # No matrices in B!
)
```

**Result:**
- Step A: Generates predicted library
- Step B: Uses 2 files to build refined library **only** (no quantification matrices)
- Step C: Quantifies 20+ files with refined library

**Benefit:**
- Skip unnecessary quantification in Step B
- Save time when you only care about final results
- Useful when testing library quality before full analysis

---

### Pattern 4: Manual Step-by-Step Control

```python
# Maximum flexibility - call each step individually

# Step A: Generate predicted library
workflow.generate_step_a_library(
    fasta_path='/path/to/database.fasta',
    script_name='01_generate_library.sh'
)

# Step B: Build refined library with 3 files, no quantification
workflow.generate_step_b_quantification_with_refinement(
    raw_files=[
        'pilot01.mzML',
        'pilot02.mzML',
        'pilot03.mzML',
    ],
    quantify=False,
    script_name='02_refine_library.sh'
)

# Step C: Full analysis with all files
workflow.generate_step_c_final_quantification(
    raw_files=[
        'pilot01.mzML',
        'pilot02.mzML',
        'pilot03.mzML',
        'batch1_01.mzML',
        'batch1_02.mzML',
        'batch2_01.mzML',
        'batch2_02.mzML',
        # ... more files
    ],
    script_name='03_final_quantification.sh'
)
```

**Benefit:** Complete control over file naming and file selection per step

---

### Pattern 5: Reusing Libraries from Previous Runs

```python
# If you already have a predicted library from a previous run
workflow.generate_step_b_quantification_with_refinement(
    raw_files=['new_sample.mzML'],
    predicted_lib_path='/previous/run/WU123_predicted.speclib',  # Reuse!
    quantify=True
)

# Or reuse a refined library
workflow.generate_step_c_final_quantification(
    raw_files=['new_batch01.mzML', 'new_batch02.mzML'],
    refined_lib_path='/previous/run/WU123_refined.speclib'  # Reuse!
)
```

**Benefit:** Don't regenerate libraries if you already have good ones

---

## Parameter Reference

### DiannWorkflow.__init__() Parameters

**Required:**
- `workunit_id` - Workunit identifier for output naming

**Optional (with defaults):**
- `var_mods` - Variable modifications list (default: `[]`)
- `threads` - CPU threads (default: `64`)
- `qvalue` - FDR threshold (default: `0.01`)
- `is_dda` - Set `True` for DDA data (default: `False`)
- `pg_level` - Protein grouping: `0`=genes, `1`=names, `2`=IDs (default: `0`)
- `min_pep_len` - Minimum peptide length (default: `6`)
- `max_pep_len` - Maximum peptide length (default: `30`)
- `min_pr_charge` - Minimum precursor charge (default: `2`)
- `max_pr_charge` - Maximum precursor charge (default: `3`)
- `min_pr_mz` - Minimum precursor m/z (default: `400`)
- `max_pr_mz` - Maximum precursor m/z (default: `1500`)
- `missed_cleavages` - Maximum missed cleavages (default: `1`)
- `cut` - Protease specificity (default: `"K*,R*"` for trypsin)
- `mass_acc` - MS2 mass accuracy in ppm (default: `20`)
- `mass_acc_ms1` - MS1 mass accuracy in ppm (default: `15`)
- `scan_window` - Scan window radius (default: `0` / auto)

### Step B Parameters

- `raw_files` - Files to process (can be subset)
- `quantify` - Generate matrices? (default: `True`)
- `predicted_lib_path` - Override library location (optional)

### Step C Parameters

- `raw_files` - Files to process (can be different than B)
- `refined_lib_path` - Override library location (optional)

### Common Modifications

```python
var_mods = [
    ('35', '15.994915', 'M'),      # Oxidation (Met)
    ('4', '57.021464', 'C'),       # Carbamidomethyl (Cys)
    ('1', '42.010565', 'K'),       # Acetyl (Lys)
    ('21', '79.966331', 'STY'),    # Phosphorylation (Ser/Thr/Tyr)
]
```

### DDA vs DIA

```python
# For DIA data (default)
workflow = DiannWorkflow(..., is_dda=False)

# For DDA data
workflow = DiannWorkflow(..., is_dda=True)
```

### Protein Grouping

```python
# Group by genes (default, most aggregated)
workflow = DiannWorkflow(..., pg_level=0)

# Group by protein names (intermediate)
workflow = DiannWorkflow(..., pg_level=1)

# Group by protein IDs (most detailed)
workflow = DiannWorkflow(..., pg_level=2)
```

## Best Practices

### 1. Library Building Strategy

- **Small datasets (<10 files)**: Use all files in Steps B and C
- **Medium datasets (10-50 files)**: Use 5-10 representative files in Step B
- **Large datasets (>50 files)**: Use 10-20 diverse files in Step B, set `quantify=False`

### 2. When to Skip Step B Quantification

Set `quantify_step_b=False` when:
- ✓ You have 50+ files
- ✓ Only want final quantification
- ✓ Testing library building strategies
- ✓ Want to save time/disk space

### 3. File Selection for Step B

Choose files that:
- Represent different conditions/batches
- Have good quality (not failed runs)
- Cover the expected proteome diversity

### 4. When to Use Different Files B vs C

Use different file lists when:
- ✓ Building library: use diverse representative samples
- ✓ Full analysis: include all experimental samples
- ✓ Pilot → production workflow
- ✓ Different batches or instruments

### 5. Reusing Libraries

You can reuse:
- Predicted libraries across similar experiments (same organism, same modifications)
- Refined libraries for new batches with identical acquisition settings

Never reuse libraries if:
- LC gradient changed
- Mass spec settings changed
- Different instrument used

## Key Tips

1. **Always run in order:** A → B → C
2. **Don't delete .quant files** between B and C (needed for faster Step C)
3. **Use subset in B** for large datasets (10-20 diverse files)
4. **Set `quantify=False`** if you only want the refined library
5. **Different files B/C** is totally fine and often beneficial

## Troubleshooting

### Error: "Library not found"

Make sure you run steps in order: A → B → C

### Error: ".quant files not found" in Step C

The .quant files must exist next to the raw files from Step B. Don't delete them!

### Warning: "use-quant with mass accuracy optimization"

This is expected. The mass accuracies are fixed in the parameters (`mass_acc`, `mass_acc_ms1`).

### Step B is too slow

Try:
- Reducing `raw_files_step_b` to fewer files
- Setting `quantify_step_b=False` to skip matrix generation
