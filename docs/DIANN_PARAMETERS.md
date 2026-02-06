# DIA-NN Parameters Reference

Comprehensive guide to DIA-NN command-line parameters, compiled from the official GitHub repository, issues, and discussions.

**Repository**: https://github.com/vdemichev/DiaNN

**Last Updated**: 2026-02-06

---

## Table of Contents

- [Basic Usage](#basic-usage)
- [Input/Output](#inputoutput)
- [Mass Accuracy and Calibration](#mass-accuracy-and-calibration)
- [Modifications and PTMs](#modifications-and-ptms)
- [Spectral Library](#spectral-library)
- [Quantification](#quantification)
- [Performance and Threading](#performance-and-threading)
- [Quality Control](#quality-control)
- [Advanced Options](#advanced-options)
- [Common Issues and Solutions](#common-issues-and-solutions)

---

## Basic Usage

### Command Structure

```bash
diann.exe [options]
```

Parameters use double-dash format (`--option`) and are processed in the order supplied. Most can be organized in configuration files.

### Configuration Files

**`--cfg <filename>`**
- Load commands from configuration file
- Example: `--cfg diann_config.cfg`
- Commands in config files are processed sequentially

---

## Input/Output

### Input Files

**`--lib <library_file>`**
- **Purpose**: Specify spectral library file(s)
- **Supported formats**: `.csv`, `.tsv`, `.xls`, `.txt`, `.parquet`, `.speclib` (DIA-NN binary)
- **Example**: `--lib predicted.speclib`
- **Library-free mode**: `--lib` (with no value) — tells DIA-NN to operate without a pre-existing library. Combined with `--fasta-search --predictor` and raw files, this enables single-step workflow where library prediction and quantification happen in one invocation.
- **Note**: Multiple libraries can be specified by repeating the parameter

**`--fasta <fasta_file>`**
- **Purpose**: Provide FASTA sequence database
- **Format**: UniProt format (uncompressed) recommended for full functionality
- **Example**: `--fasta uniprot_human.fasta`
- **Usage**: Required for library generation and protein inference
- **Multiple FASTAs**: Can be specified multiple times; DIA-NN merges them internally

**`--reannotate`**
- **Purpose**: Update protein information for each precursor in the library using the provided FASTA
- **Usage**: Use when providing `--fasta` together with `--lib` in quantification steps to re-annotate protein IDs
- **Note**: Not needed in single-step mode (FASTA is used from the start). In two-step mode, use in Step B when FASTA is provided alongside the predicted library.

**`--raw <raw_file>`**
- **Purpose**: Specify raw data files to process
- **Supported formats**:
  - Sciex `.wiff`
  - Bruker `.d`
  - Thermo `.raw`
  - `.mzML`
  - `.dia`
- **Example**: `--raw sample1.mzML --raw sample2.mzML`

### Output Files

**`--out <output_file>`**
- **Purpose**: Set output file name/path for main report
- **Format**: `.parquet` (Apache Parquet format)
- **Example**: `--out report.parquet`

**`--out-lib <library_file>`**
- **Purpose**: Set explicit output path for the generated spectral library
- **Format**: `.parquet` (DIA-NN 2.3+) or `.tsv`
- **Example**: `--out-lib results/report-lib.parquet`
- **Note**: Used with `--gen-spec-lib`. If not specified, DIA-NN auto-generates the library filename from `--out` (inserting `-lib` before the extension).

**Output file types produced**:
- **Main report**: `.parquet` - Precursor and protein IDs with quantities
- **Protein matrix**: `.pg_matrix.tsv` - Protein group quantities (1% FDR, MaxLFQ normalized)
- **Gene matrix**: `.gg_matrix.tsv` - Gene group quantities
- **Unique genes**: `.unique_genes_matrix.tsv` - Proteotypic peptide quantities
- **Site report**: `.site_report.parquet` - PTM localization (when mods declared with FASTA)
- **XIC**: `.xic.parquet` - Extracted ion chromatograms
- **Stats**: `.stats.tsv` - QC metrics
- **Manifest**: `.manifest.txt` - Output file descriptions

---

## Mass Accuracy and Calibration

### MS2 Mass Tolerance

**`--mass-acc <ppm>`**
- **Purpose**: MS/MS mass tolerance for fragment matching
- **Default**: `0` (auto-optimization)
- **Recommended values by instrument**:
  - **timsTOF**: `15.0` ppm
  - **Orbitrap Astral**: `10.0` ppm
  - **TripleTOF 6600/ZenoTOF**: `20.0` ppm
- **Example**: `--mass-acc 15.0`

### MS1 Mass Tolerance

**`--ms1-accuracy <ppm>` / `--mass-acc-ms1 <ppm>`**
- **Purpose**: MS1 precursor mass tolerance
- **Recommended values by instrument**:
  - **timsTOF**: `15.0` ppm
  - **Orbitrap Astral**: `4.0` ppm
  - **TripleTOF/ZenoTOF**: `12.0` ppm
- **Example**: `--mass-acc-ms1 15.0`

### Calibration

**`--mass-acc-cal <ppm>`**
- **Purpose**: Calibration mass accuracy threshold
- **Usage**: Mass accuracy optimization and calibration

**`--ref <library_file>`**
- **Purpose**: Provide calibration library for mass/RT/IM alignment
- **Example**: `--ref calibration.speclib`

**`--unrelated-runs`**
- **Purpose**: Optimize mass accuracy across unrelated samples
- **Usage**: Use when processing samples that don't share common peptides
- **Note**: Prevents assumptions about run relatedness

---

## Modifications and PTMs

### Fixed Modifications

**`--fixed-mod <name>,<mass>,<residues>,<type>`**
- **Purpose**: Declare fixed (always-present) modifications
- **Format**: `NAME,MASS,AMINO_ACIDS,TYPE`
- **Example**: `--fixed-mod "Carbamidomethyl,57.021464,C"`
- **Common fixed mods**:
  - Carbamidomethyl (C): `57.021464`
  - TMT (K and N-term): `229.162932`

**`--lib-fixed-mod <mod_name>`**
- **Purpose**: Apply fixed modifications in silico to spectral library entries
- **Example**: `--lib-fixed-mod Carbamidomethyl`
- **Usage**: Convert library entries to include specified fixed modification

### Variable Modifications

**`--var-mod <unimod_id>,<mass>,<residues>`**
- **Purpose**: Declare variable (optional) modifications
- **Format**: `UNIMOD_ID,MASS,RESIDUES`
- **Example**: `--var-mod "35,15.994915,M"` (Oxidation on Met)
- **Common variable mods**:
  - Oxidation (M): `35,15.994915,M`
  - Phosphorylation (STY): `21,79.966331,STY`
  - Acetylation (Protein N-term): `1,42.010565,^`
- **Important**: DIA-NN has built-in detection for common PTMs

**Max Variable Modifications**:
- **Best Practice**: Start with `1` and only increase as necessary
- **Reason**: Higher values increase search space and can reduce sensitivity
- **Source**: [Issue #1738](https://github.com/vdemichev/DiaNN/issues/1738)

### Custom Modifications

**`--mod <name>,<mass>,<residues>`**
- **Purpose**: Register custom modification definitions
- **Usage**: For modifications not in UniMod database

**`--full-unimod`**
- **Purpose**: Load complete UniMod modification database
- **Usage**: Enable support for all UniMod modifications

**`--original-mods`**
- **Purpose**: Prevent automatic conversion to UniMod format
- **Usage**: Preserve original modification names from library

---

## Spectral Library

### Library Generation

**`--gen-spec-lib`**
- **Purpose**: Generate a spectral library during analysis
- **Usage**: Produces an empirical/refined library from the search results
- **Output**: Library saved alongside main report (auto-named with `-lib` inserted), or to path specified by `--out-lib`

**`--predictor`**
- **Purpose**: Use deep learning predictor for in-silico spectral library generation
- **Usage**: Required for library prediction from FASTA (both single-step and two-step workflows)

**`--fasta-search`**
- **Purpose**: Enable FASTA-based library-free search
- **Usage**: Performs in-silico digestion of FASTA and generates predicted library
- **Two-step mode**: Used alone with `--predictor` and FASTA (no raw files) to produce `.predicted.speclib`
- **Single-step mode**: Combined with `--predictor`, `--lib` (empty), FASTA, and raw files to do everything in one call

#### Workflow modes

**Single-step workflow** (one DIA-NN invocation):
- `--lib` (empty) + `--fasta-search` + `--predictor` + `--f` raw files
- Library prediction + quantification in one call
- No intermediate files

**Two-step workflow** (two DIA-NN invocations):
1. **Library prediction**: `--fasta-search --predictor --fasta db.fasta` (no raw files)
   - Outputs: `.predicted.speclib` (binary format)
2. **Quantification**: `--lib predicted.speclib --f sample.mzML --gen-spec-lib --reanalyse`
   - Generates refined empirical library + quantification results
   - Outputs: `.parquet` format library and report

### Library Prediction Parameters

**`--cut <cleavage_rules>`**
- **Purpose**: Specify protease cleavage specificity
- **Default**: `K*,R*` (trypsin)
- **Example**: `--cut "K*,R*"`
- **Note**: Asterisk indicates cleavage after the residue

### Prediction Model Fine-Tuning

**`--tune-lib <library_file>`**
- **Purpose**: Specify library for fine-tuning predictor models
- **Example**: `--tune-lib empirical.tsv`
- **Usage**: Improve predictions using experiment-specific data

**`--tune-rt`**
- **Purpose**: Fine-tune retention time prediction model
- **Usage**: Enable RT model fine-tuning

**`--tune-im`**
- **Purpose**: Fine-tune ion mobility prediction model
- **Usage**: Enable IM model fine-tuning (for timsTOF data)

**`--tune-fr`**
- **Purpose**: Fine-tune fragmentation prediction model
- **Available**: DIA-NN 2.3+
- **Usage**: Improve fragment intensity predictions

**`--tune-lr <learning_rate>`**
- **Purpose**: Adjust learning rate for model fine-tuning
- **Usage**: Control speed/stability of model training

**`--tune-restrict-layers`**
- **Purpose**: Limit fine-tuning to specific model layers
- **Usage**: Prevent overfitting by restricting trainable layers

### Custom Models

**`--tokens <dictionary_file>`**
- **Purpose**: Supply custom tokenization dictionary for predictions
- **Example**: `--tokens custom_tokens.txt`

**`--rt-model <model_file>`**
- **Purpose**: Provide custom trained RT prediction model
- **Example**: `--rt-model tuned_rt.pt`

**`--im-model <model_file>`**
- **Purpose**: Provide custom trained IM prediction model
- **Example**: `--im-model tuned_im.pt`

### Prediction Control

**`--dl-no-rt`**
- **Purpose**: Prevent replacement of library RTs with predictions
- **Usage**: Trust library RT values over predicted values

**`--dl-no-im`**
- **Purpose**: Prevent replacement of library IMs with predictions
- **Usage**: Trust library IM values over predicted values

**`--dl-no-fr`**
- **Purpose**: Prevent replacement of library spectra with predictions
- **Usage**: Trust library fragment patterns over predicted patterns

### Decoy Generation

**`--dg-keep-nterm <N>`**
- **Purpose**: Do not change the first N residues in decoy generation
- **Usage**: Preserve N-terminal modifications in decoys

**`--dg-keep-cterm <N>`**
- **Purpose**: Do not change the last N residues in decoy generation
- **Usage**: Preserve C-terminal modifications in decoys

**`--dg-min-shuffle <mass>`**
- **Purpose**: Target minimum fragment mass shift in shuffled decoys
- **Usage**: Control decoy similarity to targets

**`--dg-min-mut <mass>`**
- **Purpose**: Target minimum precursor mass shift in mutated decoys

**`--dg-max-mut <mass>`**
- **Purpose**: Target maximum precursor mass shift in mutated decoys

**`--report-decoys`**
- **Purpose**: Include decoy identifications in output
- **Usage**: For FDR validation and diagnostic purposes

---

## Quantification

### Match-Between-Runs

**`--mbr` / `--reanalyse`**
- **Purpose**: Enable match-between-runs feature
- **Usage**: Transfer identifications across runs for improved quantification
- **Note**: Essential for library refinement

### RT Profiling

**`--rt-profiling`**
- **Purpose**: Enable retention time profiling mode
- **Usage**: Improves quantification accuracy by using RT-dependent scoring. Enabled by default in the DIA-NN GUI.
- **Example**: `--rt-profiling`

### QuantUMS Parameters

**`--quant-train-runs <run_range>`**
- **Purpose**: Specify run range for QuantUMS parameter training
- **Example**: `--quant-train-runs 1-5`

**`--quant-sel-runs <N>`**
- **Purpose**: Auto-select N runs for QuantUMS training
- **Example**: `--quant-sel-runs 3`

**`--quant-params <params>`**
- **Purpose**: Supply pre-calculated QuantUMS parameters
- **Usage**: Reuse parameters from previous analysis

**`--reuse-quant` / `--use-quant`**
- **Purpose**: Reuse previously generated `.quant` files
- **Usage**: Skip re-processing in Step C when using same files from Step B
- **Note**: Significant speed improvement when applicable

**`--keep-quant-files`**
- **Purpose**: Retain `.quant` files after analysis completion
- **Usage**: Allow reuse in subsequent analyses

### MaxLFQ

**`--no-maxlfq`**
- **Purpose**: Disable MaxLFQ protein quantification
- **Default**: MaxLFQ is enabled
- **Usage**: Use when MaxLFQ normalization is not desired

### Site-Level Quantification

**`--site-ms1-quant`**
- **Purpose**: Use MS1 apex intensities for PTM site quantification
- **Usage**: Improve PTM site quantification accuracy
- **Requires**: Variable modifications declared and FASTA provided

### Matrix Filtering

**`--matrix-spec-q <threshold>`**
- **Purpose**: Run-specific protein-level FDR filter
- **Default**: `0.05` (5%)
- **Usage**: Adjust stringency of run-level protein filtering
- **Example**: `--matrix-spec-q 0.01` (1% FDR)

### Export Options

**`--export-quant`**
- **Purpose**: Export raw fragment intensity information
- **Usage**: Access detailed fragment-level data

**`--cont-quant-exclude`**
- **Purpose**: Exclude contaminants from quantification
- **Usage**: Remove known contaminants from matrices

---

## Performance and Threading

### CPU Control

**`--threads <N>`**
- **Purpose**: Control number of processing threads
- **Default**: Uses all available CPU cores
- **Example**: `--threads 32`
- **Best Practice**: Set to match your CPU core count; avoid oversubscription

**`--aff <core_list>`**
- **Purpose**: Assign processing threads to specific CPU cores
- **Example**: `--aff 0-15`
- **Usage**: Manual CPU affinity control for optimal performance

**`--auto-aff`**
- **Purpose**: Automatically optimize CPU affinity
- **Usage**: Let DIA-NN determine optimal thread placement

### Data Processing Windows

**`--scan-window <N>`**
- **Purpose**: Set approximate DIA cycles during average peptide elution
- **Typical values**: `6-10` for most instruments
- **Example**: `--scan-window 8`
- **Note**: Affects how many scans are considered during peptide detection. Can be set via Bfabric parameter `05b_diann_scan_window` (AUTO, 3, 5, 8, 12, 17, 23, 30).

**`--im-window <value>`**
- **Purpose**: Configure ion mobility filtering window width
- **Default**: `0.2`
- **Example**: `--im-window 0.2`
- **Usage**: timsTOF and ion mobility data

### XIC Extraction

**`--xic <seconds>`**
- **Purpose**: Set retention time window for chromatogram extraction
- **Default**: `10` seconds
- **Example**: `--xic 15`
- **Usage**: Extract chromatograms within N seconds from elution apex

**`--xic-theoretical-fr`**
- **Purpose**: Extract all charge 1 and 2 y/b-series theoretical fragments
- **Usage**: Comprehensive fragment extraction for diagnostics

### Speed Optimization

**`--pre-select <N>`**
- **Purpose**: Limit precursor count in InfinDIA pre-search
- **Usage**: Speed up large-scale searches

**`--pre-select-force`**
- **Purpose**: Enforce precursor selection limit
- **Usage**: Strict precursor filtering

**`--quant-tims-sum`**
- **Purpose**: Sum signals across frames for Synchro-PASEF data
- **Usage**: Reduce computational load for timsTOF data

---

## Quality Control

### Peptide Constraints

**`--min-pep-len <N>`**
- **Purpose**: Minimum peptide length
- **Default**: Typically `6`
- **Example**: `--min-pep-len 7`

**`--max-pep-len <N>`**
- **Purpose**: Maximum peptide length
- **Default**: Typically `30`
- **Example**: `--max-pep-len 35`

### Precursor Constraints

**`--min-pr-charge <N>`**
- **Purpose**: Minimum precursor charge
- **Default**: `2`
- **Example**: `--min-pr-charge 2`

**`--max-pr-charge <N>`**
- **Purpose**: Maximum precursor charge
- **Default**: `3` or `4`
- **Example**: `--max-pr-charge 4`

**`--min-pr-mz <value>`**
- **Purpose**: Minimum precursor m/z
- **Default**: `400`
- **Example**: `--min-pr-mz 350`

**`--max-pr-mz <value>`**
- **Purpose**: Maximum precursor m/z
- **Default**: `1500` or `1800`
- **Example**: `--max-pr-mz 2000`

**Important**: These are **not auto-detected from raw data**. Set them to match the precursor mass range of your DIA method. From the DIA-NN docs: *"To reduce RAM usage, make sure that the precursor mass range specified (when generating a predicted library) is not wider than the precursor mass range selected for MS/MS by the DIA method."*

### Fragment m/z Range

**`--min-fr-mz <value>`**
- **Purpose**: Minimum fragment m/z
- **Default**: `200`
- **Example**: `--min-fr-mz 150`

**`--max-fr-mz <value>`**
- **Purpose**: Maximum fragment m/z
- **Default**: `1800`
- **Example**: `--max-fr-mz 2000`

### Q-value Threshold

**`--qvalue <threshold>`**
- **Purpose**: Q-value (FDR) threshold for identifications
- **Default**: `0.01` (1% FDR)
- **Example**: `--qvalue 0.01`
- **Note**: Global q-value threshold; matrices use additional run-specific filtering

### Filtering

**`--proteotypic-only`**
- **Purpose**: Filter to proteotypic (gene-specific) peptides only
- **Usage**: Remove shared peptides from analysis

**`--missed-cleavages <N>`**
- **Purpose**: Maximum number of missed cleavages
- **Default**: `1`
- **Example**: `--missed-cleavages 2`

---

## Advanced Options

### Multiplexing (plexDIA)

**`--channels <specifications>`**
- **Purpose**: Declare mass shifts for all channels
- **Format**: `NAME,LABEL,AMINO_ACIDS,MS1_SHIFT:MS2_SHIFT`
- **Example**: `--channels "Light,K,K,0:0" --channels "Heavy,K[+8],K,8.014199:8.014199"`
- **Usage**: Non-isobaric multiplexing support

**`--channel-run-norm`**
- **Purpose**: Normalize channels within runs
- **Usage**: Pulsed SILAC applications

**`--channel-spec-norm`**
- **Purpose**: Normalize channels across samples
- **Usage**: Multiplexed independent samples

**`--decoy-channel`**
- **Purpose**: Override default decoy channel designation
- **Usage**: Manual control of decoy channel in multiplexed experiments

### Data Modes

**`--dda`**
- **Purpose**: Enable beta-stage DDA data support
- **Status**: Experimental feature
- **Usage**: Process DDA (Data-Dependent Acquisition) data

**`--mzML-exact-mass`**
- **Purpose**: Use exact mass values from mzML files
- **Usage**: Preserve exact mass information from mzML format

### Pipeline Options

**`--regex "<pattern>" "<replacement>"`**
- **Purpose**: Pattern-based file path replacement in pipelines
- **Example**: `--regex "old_path" "new_path"`
- **Usage**: Migrate file paths when moving analysis environments

**`--ignore-case`**
- **Purpose**: Case-insensitive regex matching
- **Usage**: Use with `--regex` for flexible path matching

### Logging

**`--log-level <level>`**
- **Purpose**: Control verbosity of processing log output
- **Usage**: Adjust detail level in log files

**`--verbose <N>`**
- **Purpose**: Verbosity level
- **Default**: `1`
- **Example**: `--verbose 2`

---

## Common Issues and Solutions

### Issue: Unexpected Results with Parameter Configuration

**Problem**: Results don't match expectations despite correct parameters
**Solution**:
- Verify parameter order (processed sequentially)
- Check for conflicting parameters
- Review log files for warnings
- Source: [Issue #1743](https://github.com/vdemichev/DiaNN/issues/1743)

### Issue: Fixed vs Variable Modifications

**Problem**: Confusion about whether modifications are fixed or variable
**Solution**:
- DIA-NN supports both fixed and variable modifications
- Use `--fixed-mod` for always-present modifications
- Use `--var-mod` for optional modifications
- Keep max variable modifications low (start with 1)
- Source: [Issue #1738](https://github.com/vdemichev/DiaNN/issues/1738)

### Issue: High RAM Usage

**Problem**: Out of memory errors with large datasets
**Solution**:
- Use `--quant-tims-sum` for Synchro-PASEF data
- Enable `--reuse-quant` to skip re-processing
- Process in batches if necessary
- Source: GitHub Discussions

### Issue: Mass Accuracy Optimization

**Problem**: Poor identification rates
**Solution**:
- Set instrument-specific mass accuracy values (don't rely on auto)
- Use `--unrelated-runs` for diverse sample sets
- Provide calibration library with `--ref`
- Source: GitHub Wiki

### Issue: Library Merging

**Problem**: How to combine different library types
**Solution**:
- Use empirical libraries in `.parquet` format when possible
- Fine-tune predicted libraries with `--tune-lib`
- Consult GitHub Discussions for merging strategies
- Source: GitHub Discussions

### Issue: Pre-trained Models and FDR

**Problem**: Concern about FDR inflation with pre-trained models
**Solution**:
- Use proper validation approaches
- Consider fine-tuning models to your data with `--tune-*` options
- Monitor decoy hit rates
- Source: GitHub Discussions announcement

---

## Parameter Combinations for Common Workflows

### Single-Step Workflow (Recommended)

Library prediction + quantification in one DIA-NN call:

```bash
diann.exe \
  --f sample1.raw --f sample2.raw --f sample3.raw \
  --lib \
  --fasta uniprot.fasta --fasta-search \
  --predictor --gen-spec-lib \
  --out results/report.parquet \
  --out-lib results/report-lib.parquet \
  --threads 32 --verbose 1 \
  --qvalue 0.01 --matrices \
  --met-excision --unimod4 \
  --var-mods 1 --var-mod UniMod:35,15.994915,M \
  --min-pep-len 7 --max-pep-len 30 \
  --min-pr-mz 380 --max-pr-mz 980 \
  --min-pr-charge 1 --max-pr-charge 5 \
  --min-fr-mz 150 --max-fr-mz 2000 \
  --cut K*,R* --missed-cleavages 1 \
  --reanalyse --rt-profiling
```

### Two-Step Workflow: Library Prediction

```bash
diann.exe \
  --fasta-search \
  --fasta uniprot.fasta \
  --predictor --gen-spec-lib \
  --out out-lib/report.parquet \
  --threads 32 \
  --qvalue 0.01 \
  --met-excision --unimod4 \
  --var-mods 1 --var-mod UniMod:35,15.994915,M \
  --min-pep-len 7 --max-pep-len 30 \
  --min-pr-mz 380 --max-pr-mz 980 \
  --min-pr-charge 1 --max-pr-charge 5 \
  --min-fr-mz 150 --max-fr-mz 2000 \
  --cut K*,R* --missed-cleavages 1 \
  --temp temp-lib
```

### Two-Step Workflow: Quantification

```bash
diann.exe \
  --lib out-lib/report-lib.predicted.speclib \
  --fasta uniprot.fasta --reannotate \
  --f sample1.mzML --f sample2.mzML \
  --out out-quant/report.parquet \
  --gen-spec-lib \
  --threads 32 \
  --qvalue 0.01 --matrices \
  --met-excision --unimod4 \
  --var-mods 1 --var-mod UniMod:35,15.994915,M \
  --min-pep-len 7 --max-pep-len 30 \
  --min-pr-mz 380 --max-pr-mz 980 \
  --min-pr-charge 1 --max-pr-charge 5 \
  --min-fr-mz 150 --max-fr-mz 2000 \
  --cut K*,R* --missed-cleavages 1 \
  --relaxed-prot-inf --reanalyse --rt-profiling \
  --temp temp-quant
```

### Phosphoproteomics (timsTOF)

```bash
diann.exe \
  --lib predicted.speclib \
  --fasta uniprot.fasta \
  --raw sample1.d --raw sample2.d \
  --out report.parquet \
  --threads 32 \
  --mass-acc 15.0 \
  --mass-acc-ms1 15.0 \
  --im-window 0.2 \
  --qvalue 0.01 \
  --var-mod "21,79.966331,STY" \
  --site-ms1-quant
```

---

## References

- **GitHub Repository**: https://github.com/vdemichev/DiaNN
- **Issues**: https://github.com/vdemichev/DiaNN/issues
- **Discussions**: https://github.com/vdemichev/DiaNN/discussions
- **README**: https://github.com/vdemichev/DiaNN/blob/master/README.md

---

## Notes

- All parameter names and values are case-sensitive
- Parameters are processed in the order supplied
- Configuration files can simplify complex workflows
- GUI operations display equivalent command-line syntax in logs
- Keep software updated for latest parameters and bug fixes

---

**Document Version**: 1.1
**Compiled from**: DIA-NN GitHub repository and DIA-NN 2.3.2 GUI (as of 2026-02-06)
**Maintainer**: Update regularly by checking GitHub for new parameters and issues
