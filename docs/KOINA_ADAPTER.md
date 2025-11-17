# Koina Config Adapter - Translation Layer

The `KoinaConfigAdapter` provides automatic translation between DIA-NN workflow configs and Oktoberfest configs, enabling seamless integration of Koina/Prosit predictions.

## Purpose

Instead of manually creating separate Oktoberfest configs, you can automatically generate them from your existing DIA-NN configs, ensuring parameter consistency and reducing configuration errors.

## Usage

### Command-Line Interface

```bash
python -m diann_runner.koina_adapter \
  --diann-config out-DIANN_libA/WU_TEST_predicted.speclib.config.json \
  --fasta ProteoBenchFASTA_MixedSpecies_HYE.fasta \
  --output ../oktoberfest/config.json \
  --instrument QE \
  --show-comparison
```

**Parameters:**
- `--diann-config`: Path to DIA-NN `.config.json` file (from Step A or existing workflow)
- `--fasta`: Path to FASTA file (required by Oktoberfest)
- `--output`: Where to save the generated Oktoberfest config (default: `oktoberfest_config.json`)
- `--instrument`: Instrument type - `QE`, `TIMSTOF`, or `ASTRAL` (default: `QE`)
- `--show-comparison`: Print parameter mapping table

### Python API

```python
from diann_runner import KoinaConfigAdapter

# Generate Oktoberfest config from DIA-NN config
oktoberfest_config = KoinaConfigAdapter.from_diann_config(
    diann_config_path='out-DIANN_libA/WU_TEST_predicted.speclib.config.json',
    fasta_path='ProteoBenchFASTA_MixedSpecies_HYE.fasta',
    instrument_type='QE',
)

# Save config
KoinaConfigAdapter.save_oktoberfest_config(
    oktoberfest_config,
    '../oktoberfest/config.json'
)

# Show comparison
KoinaConfigAdapter.print_comparison(
    'out-DIANN_libA/WU_TEST_predicted.speclib.config.json',
    oktoberfest_config
)
```

## Parameter Mapping

The adapter automatically translates DIA-NN parameters to Oktoberfest equivalents:

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
| Built-in predictor | `models.irt: "Prosit_..."` | RT model |

### Enzyme Mapping

The adapter recognizes common cut patterns:

```python
ENZYME_MAPPING = {
    'K*,R*': 'trypsin',      # Most common
    'K*': 'lysc',            # Lys-C
    'D*': 'aspn',            # Asp-N
    'E*': 'gluc',            # Glu-C
}
```

### Model Selection by Instrument

Different instruments use different Prosit models:

**Orbitrap QE/Exploris (HCD):**
- Intensity: `Prosit_2020_intensity_HCD`
- iRT: `Prosit_2019_irt`

**Bruker timsTOF:**
- Intensity: `Prosit_2023_intensity_timsTOF`
- iRT: `Prosit_2019_irt`
- Ion mobility: `Prosit_2023_IM`

**Thermo Astral:**
- Intensity: `Prosit_2020_intensity_HCD`
- iRT: `Prosit_2019_irt`

## Example Workflow

### 1. Run DIA-NN Step A (Built-in Predictor)

```bash
diann-workflow library-search \
  --fasta ProteoBenchFASTA_MixedSpecies_HYE.fasta \
  --workunit-id WU_TEST \
  --var-mods "35,15.994915,M"

# Output: out-DIANN_libA/WU_TEST_predicted.speclib.config.json
```

### 2. Generate Oktoberfest Config from DIA-NN Config

```bash
python -m diann_runner.koina_adapter \
  --diann-config out-DIANN_libA/WU_TEST_predicted.speclib.config.json \
  --fasta ProteoBenchFASTA_MixedSpecies_HYE.fasta \
  --output ../oktoberfest/config.json \
  --show-comparison
```

**Output:**
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

### 3. Run Oktoberfest

```bash
cd ../oktoberfest
source .venv/bin/activate.fish
oktoberfest -c config.json | tee oktoberfest.log.txt
```

### 4. Run DIA-NN Step B with Koina Library

```bash
cd ../diann_runner
diann-workflow quantification-refinement \
  --config workflow_koina.config.json \
  --predicted-lib ../oktoberfest/out/library.speclib \
  --raw-files *.mzML
```

## Advanced Usage

### Custom Models

Override default models for specific experiments:

```python
oktoberfest_config = KoinaConfigAdapter.from_diann_config(
    diann_config_path='out-DIANN_libA/WU_TEST_predicted.speclib.config.json',
    fasta_path='ProteoBenchFASTA_MixedSpecies_HYE.fasta',
    instrument_type='QE',
    intensity_model='AlphaPept_ms2_generic',  # Alternative model
    irt_model='Deeplc',                       # Chromatography-specific RT
)
```

### Different Collision Energies

```python
oktoberfest_config = KoinaConfigAdapter.from_diann_config(
    diann_config_path='config.json',
    fasta_path='db.fasta',
    collision_energy=25,  # Lower energy (default: 30)
)
```

### Alternative Output Formats

```python
oktoberfest_config = KoinaConfigAdapter.from_diann_config(
    diann_config_path='config.json',
    fasta_path='db.fasta',
    output_format='spectronaut',  # Instead of 'msp'
)
```

## Limitations

### Variable Modifications

Currently, the adapter only detects oxidation (UniMod:35) from DIA-NN's `var_mods`. Other modifications need manual config editing.

**Workaround:**
```python
# Generate base config
config = KoinaConfigAdapter.from_diann_config(...)

# Manually add phosphorylation
config['spectralLibraryOptions']['nrPhospho'] = 1

# Save
KoinaConfigAdapter.save_oktoberfest_config(config, 'config.json')
```

### Fixed Modifications

DIA-NN's `--unimod4` (Carbamidomethyl on C) is automatically assumed by Oktoberfest. No explicit configuration needed.

### Precursor m/z Range

DIA-NN's `min_pr_mz`/`max_pr_mz` parameters are not translated because:
- Oktoberfest generates all theoretical precursors
- Filtering happens during DIA-NN search, not library generation

## Integration with Workflow

The adapter is designed to integrate seamlessly with the existing workflow:

```python
from diann_runner import DiannWorkflow, KoinaConfigAdapter

# 1. Run DIA-NN Step A
workflow = DiannWorkflow(workunit_id='WU123', var_mods=[('35', '15.994915', 'M')])
workflow.generate_step_a_library(fasta_path='db.fasta')

# 2. Generate Oktoberfest config from Step A config
oktoberfest_config = KoinaConfigAdapter.from_diann_config(
    diann_config_path='out-DIANN_libA/WU123_predicted.speclib.config.json',
    fasta_path='db.fasta',
)
KoinaConfigAdapter.save_oktoberfest_config(oktoberfest_config, '../oktoberfest/config.json')

# 3. Run Oktoberfest (externally)
# ... oktoberfest -c config.json

# 4. Run Step B with Koina library
workflow_koina = DiannWorkflow.from_config_file('workflow_koina.config.json')
workflow_koina.generate_step_b_quantification_with_refinement(
    raw_files=['sample1.mzML', 'sample2.mzML'],
)
```

## Validation

The adapter performs validation:

1. **Enzyme detection**: Warns if cut pattern is not recognized
2. **Modification detection**: Logs which modifications were translated
3. **Instrument models**: Uses instrument-appropriate default models

## Future Enhancements

Planned improvements:

1. **Full modification support**: Translate all UniMod modifications
2. **Multi-enzyme support**: Handle combined enzymes
3. **Direct Oktoberfest execution**: Launch Oktoberfest from workflow
4. **Library format conversion**: Automatic MSP → speclib conversion
5. **Batch processing**: Generate configs for multiple FASTAs/experiments

## See Also

- [Koina Integration Guide](KOINA_INTEGRATION.md) - Overview of using Koina/Oktoberfest
- [Comparing Predictors](../COMPARING_PREDICTORS.md) - Running parallel workflows
- [workflow_koina.config.json](../workflow_koina.config.json) - Example config for Step B/C
