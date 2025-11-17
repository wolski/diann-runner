# DIA-NN Workflow - Usage Examples

## Overview

The refactored `DiannWorkflow` class provides maximum flexibility by separating:
- **Shared parameters** (in `__init__`): instrument settings, modifications, threading, etc.
- **Step-specific parameters** (in method calls): FASTA, raw files lists

## Key Design Decisions

### 1. FASTA is Step A only
FASTA is only needed for library generation (Step A), not for quantification (Steps B & C).

### 2. Different raw files for B vs C
You can use **different file lists** for:
- **Step B**: Small subset for fast library refinement
- **Step C**: Full dataset for comprehensive quantification

### 3. Optional quantification in Step B
Use `quantify=False` in Step B to skip matrices generation and only build the refined library (faster).

## Usage Patterns

### Pattern 1: Standard Workflow (Same Files Throughout)

```python
from diann_workflow import DiannWorkflow

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

## Common Parameter Reference

### Variable Modifications
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

## Workflow Outputs

### Step A outputs:
- `out-DIANN_libA/WU336182_predicted.speclib` - Predicted spectral library

### Step B outputs:
- `out-DIANN_quantB/WU336182_reportB.tsv` - Report (if quantify=True)
- `out-DIANN_quantB/WU336182_refined.speclib` - Refined empirical library
- `out-DIANN_quantB/WU336182_reportB.pg_matrix.tsv` - Protein matrix (if quantify=True)
- `out-DIANN_quantB/WU336182_reportB.pr_matrix.tsv` - Precursor matrix (if quantify=True)

### Step C outputs:
- `out-DIANN_quantC/WU336182_reportC.tsv` - Final report
- `out-DIANN_quantC/WU336182_final.speclib` - Final library
- `out-DIANN_quantC/WU336182_reportC.pg_matrix.tsv` - Protein matrix
- `out-DIANN_quantC/WU336182_reportC.pr_matrix.tsv` - Precursor matrix

## Best Practices

### 1. Library Building Strategy
- **Small datasets (<10 files)**: Use all files in Steps B and C
- **Medium datasets (10-50 files)**: Use 5-10 representative files in Step B
- **Large datasets (>50 files)**: Use 10-20 diverse files in Step B, set `quantify=False`

### 2. When to Skip Step B Quantification
Set `quantify_step_b=False` when:
- You have many files and only want final quantification
- You're testing different library building strategies
- You want to save time and disk space

### 3. File Selection for Step B
Choose files that:
- Represent different conditions/batches
- Have good quality (not failed runs)
- Cover the expected proteome diversity

### 4. Reusing Libraries
You can reuse:
- Predicted libraries across similar experiments (same organism, same modifications)
- Refined libraries for new batches with identical acquisition settings
- Never reuse libraries if LC gradient or mass spec settings changed

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
