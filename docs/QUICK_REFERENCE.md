# DIA-NN Workflow - Quick Reference

## Basic Setup

```python
from diann_workflow import DiannWorkflow

workflow = DiannWorkflow(
    workunit_id='WU123',
    var_mods=[('35', '15.994915', 'M')],  # Oxidation
    threads=64,
    qvalue=0.01,
)
```

## Three Usage Patterns

### 1. Simple: Same files everywhere
```python
files = ['s1.mzML', 's2.mzML', 's3.mzML']

workflow.generate_all_scripts(
    fasta_path='/db.fasta',
    raw_files_step_b=files,
    raw_files_step_c=files  # Optional - defaults to step_b
)
```

### 2. Fast: Subset library → Full quantification
```python
workflow.generate_all_scripts(
    fasta_path='/db.fasta',
    raw_files_step_b=['s1.mzML', 's2.mzML'],      # 2 files: FAST
    raw_files_step_c=['s1.mzML', ..., 's50.mzML'], # 50 files: FULL
    quantify_step_b=False  # Skip quantification in B
)
```

### 3. Manual: Full control
```python
# Generate each step individually
workflow.generate_step_a_library(
    fasta_path='/db.fasta'
)

workflow.generate_step_b_quantification_with_refinement(
    raw_files=['pilot1.mzML', 'pilot2.mzML'],
    quantify=False
)

workflow.generate_step_c_final_quantification(
    raw_files=all_files
)
```

## Key Parameters

### In DiannWorkflow.__init__()
- `workunit_id` - Required, for output naming
- `var_mods` - Variable modifications list
- `threads` - CPU threads (default 64)
- `qvalue` - FDR threshold (default 0.01)
- `is_dda` - Set True for DDA data (default False)
- `pg_level` - Protein grouping: 0=genes, 1=names, 2=IDs

### In generate_step_b_quantification_with_refinement()
- `raw_files` - Files to process (can be subset)
- `quantify` - Generate matrices? (default True)
- `predicted_lib_path` - Override library location (optional)

### In generate_step_c_final_quantification()
- `raw_files` - Files to process (can be different than B)
- `refined_lib_path` - Override library location (optional)

## Common Modifications

```python
var_mods = [
    ('35', '15.994915', 'M'),      # Oxidation (Met)
    ('4', '57.021464', 'C'),       # Carbamidomethyl (Cys)  
    ('1', '42.010565', 'K'),       # Acetyl (Lys)
    ('21', '79.966331', 'STY'),    # Phospho (Ser/Thr/Tyr)
]
```

## Output Structure

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

## When to Use What

### Use `quantify=False` in Step B when:
- ✓ You have 50+ files
- ✓ Only want final quantification
- ✓ Testing library building strategies
- ✓ Want to save time/disk space

### Use different files for B vs C when:
- ✓ Building library: use diverse representative samples
- ✓ Full analysis: include all experimental samples
- ✓ Pilot → production workflow
- ✓ Different batches or instruments

## Run the Scripts

```bash
bash step_A_library_search.sh
bash step_B_quantification_refinement.sh  
bash step_C_final_quantification.sh
```

## Main Results

The files you care about most:
- `out-DIANN_quantC/WU123_reportC.tsv` - Main report
- `out-DIANN_quantC/WU123_reportC.pg_matrix.tsv` - Protein matrix for R/Python

## Tips

1. **Always run in order:** A → B → C
2. **Don't delete .quant files** between B and C
3. **Use subset in B** for large datasets (10-20 diverse files)
4. **Set `quantify=False`** if you only want the refined library
5. **Different files B/C** is totally fine and often beneficial
