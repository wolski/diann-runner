# DIA-NN Runner Documentation

## Configuration Files

### default_config.json

This is an example default configuration file for DIA-NN workflow parameters. You can use this as a template to create your own configuration files.

**Parameters:**

All `DiannWorkflow` initialization parameters are supported in the config:

- `workunit_id`: Workunit identifier for naming outputs
- `output_base_dir`: Base directory for all output files (default: `"out-DIANN"`)
- `var_mods`: List of variable modifications in format `[unimod_id, mass, residues]`
  - Example: `["35", "15.994915", "M"]` = Oxidation of Methionine
  - Common modifications:
    - `["35", "15.994915", "M"]` - Oxidation (M)
    - `["21", "79.966331", "STY"]` - Phosphorylation (S, T, Y)
    - `["4", "57.021464", "C"]` - Carbamidomethylation (C) - usually fixed
- `diann_bin`: Path to DIA-NN binary (default: `"diann-docker"`)
- `threads`: Number of CPU threads to use (default: `64`)
- `qvalue`: FDR threshold (default: `0.01` = 1%)
- `min_pep_len`: Minimum peptide length (default: `6`)
- `max_pep_len`: Maximum peptide length (default: `30`)
- `min_pr_charge`: Minimum precursor charge (default: `2`)
- `max_pr_charge`: Maximum precursor charge (default: `3`)
- `min_pr_mz`: Minimum precursor m/z (default: `400`)
- `max_pr_mz`: Maximum precursor m/z (default: `1500`)
- `missed_cleavages`: Maximum number of missed cleavages (default: `1`)
- `cut`: Protease specificity (default: `"K*,R*"` for trypsin)
- `mass_acc`: MS2 mass accuracy in ppm (default: `20`)
- `mass_acc_ms1`: MS1 mass accuracy in ppm (default: `15`)
- `verbose`: Verbosity level (default: `1`)
- `pg_level`: Protein grouping level (default: `0` = genes)
  - `0` = gene names
  - `1` = protein names
  - `2` = protein IDs
- `is_dda`: Set to `true` for DDA data (default: `false`)
- `temp_dir_base`: Base name for temporary directories (default: `"temp-DIANN"`)
- `unimod4`: Enable Carbamidomethyl (C) fixed modification (default: `true`)
- `met_excision`: Enable N-terminal methionine excision (default: `true`)

**Usage:**

```bash
# Use the default config with your specific files
diann-workflow library-search \
  --config-defaults docs/default_config.json \
  --fasta /path/to/your.fasta

# Create your own custom config
diann-workflow create-config \
  --output my_project_config.json \
  --workunit-id MY_PROJECT \
  --var-mods "35,15.994915,M" "21,79.966331,STY" \
  --threads 32

# Use your custom config
diann-workflow all-stages \
  --config-defaults my_project_config.json \
  --fasta your_database.fasta \
  --raw-files *.mzML
```

**Overriding Config Values:**

Command-line arguments always override config file values:

```bash
# Use config defaults but override threads
diann-workflow library-search \
  --config-defaults docs/default_config.json \
  --fasta db.fasta \
  --threads 128
```

## Common Modifications

Here are some commonly used variable modifications for DIA-NN:

| Modification | UniMod ID | Mass Delta | Residues | Description |
|--------------|-----------|------------|----------|-------------|
| Oxidation | 35 | 15.994915 | M | Methionine oxidation |
| Phosphorylation | 21 | 79.966331 | STY | Phosphorylation on Ser/Thr/Tyr |
| Acetylation | 1 | 42.010565 | K | Lysine acetylation |
| Acetylation (N-term) | 1 | 42.010565 | ^* | N-terminal acetylation |
| Deamidation | 7 | 0.984016 | NQ | Asparagine/Glutamine deamidation |

*Note: `^*` represents protein N-terminus in DIA-NN*

## Workflow Overview

The DIA-NN workflow consists of three stages:

1. **Step A: Library Search** - Generate predicted spectral library from FASTA
2. **Step B: Quantification with Refinement** - Refine library using real data
3. **Step C: Final Quantification** - Quantify all samples with refined library

Each step saves a `.config.json` file alongside its outputs to ensure parameter consistency across the workflow.

