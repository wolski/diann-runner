# Plan: Separate Library Files from Results Zip

## Context

DIA-NN creates large spectral library files (`report-lib.*`) alongside result files. Currently, `zip_diann_results()` zips the entire output directory, which includes these library files. In two-step mode, the Step A predicted library (`out-DIANN_libA/`) is never zipped (good), but the refined library in quantB/quantC IS included in the results zip. In single-step mode, the library is always in the results zip. These files are huge and bloat the staged output unnecessarily.

**Goal**: Always exclude library files from the main results zip. Add an optional `include_libs` parameter (default: `false`) that, when enabled, creates a separate zip with all library files and stages it via `outputs.yml`.

## File Pattern

All DIA-NN library files contain `report-lib.` in their name:
- Step A: `WU{id}_report-lib.predicted.speclib`
- Step B/C/single: `WU{id}_report-lib.parquet`

---

## Changes

### 1. XML Executable (`bfabric_executable/executable_A386_DIANN_3.2.xml`)

Add a new BOOLEAN parameter between section 12 (Quantification) and 99 (Other Settings):

```xml
<!-- 14: Output Options -->
<parameter>
    <key>14_include_libs</key>
    <label>Include Spectral Libraries</label>
    <description>Include spectral library files (predicted and refined) as a separate zip in staged output. Libraries are large files; enable only if needed for downstream reuse.</description>
    <type>BOOLEAN</type>
    <value>false</value>
</parameter>
```

### 2. Parameter Parsing (`src/diann_runner/snakemake_helpers.py`)

**In `parse_flat_params()`** (~line 264, after `workflow_mode`):
```python
include_libs = flat_params.get('14_include_libs', 'false').lower() == 'true'
```

**Add to return dict** (~line 270):
```python
'include_libs': include_libs,
```

### 3. Exclude Libraries from Main Zip (`src/diann_runner/snakemake_helpers.py`)

**Modify `zip_diann_results()`** (~line 410) to skip files matching `report-lib.`:

```python
def zip_diann_results(output_dir: str, zip_path: str) -> None:
    ...
    for file_path in output_path.rglob('*'):
        if file_path.is_file() and 'report-lib.' not in file_path.name:
            arcname = file_path.relative_to(output_path.parent)
            zipf.write(file_path, arcname)
    ...
```

### 4. New Helper: Zip Library Files (`src/diann_runner/snakemake_helpers.py`)

Add a new function `zip_library_files()`:

```python
def zip_library_files(output_prefix: str, zip_path: str) -> None:
    """Zip all spectral library files (report-lib.*) from all output directories."""
    import zipfile
    base = Path(output_prefix).parent  # parent of "out-DIANN" → working dir
    prefix_name = Path(output_prefix).name  # "out-DIANN"

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        for out_dir in sorted(base.glob(f"{prefix_name}_*")):
            for lib_file in out_dir.glob("*report-lib.*"):
                if lib_file.is_file():
                    arcname = lib_file.relative_to(base)
                    zipf.write(lib_file, arcname)
```

### 5. Snakefile Changes (`src/diann_runner/Snakefile.DIANN3step.smk`)

**Add global** (~line 63):
```python
INCLUDE_LIBS = WORKFLOW_PARAMS.get("include_libs", False)
```

**Add import** of `zip_library_files` (~line 12).

**Add conditional rule** (after `zip_diann_result`):
```python
if INCLUDE_LIBS:
    rule zip_diann_libs:
        input:
            diann_zip = rules.zip_diann_result.output.zip
        output:
            zip = f"DIANN_Libs_WU{WORKUNITID}.zip"
        run:
            zip_library_files(OUTPUT_PREFIX, output.zip)
```

**Modify `outputsyml` rule** to conditionally include libs zip:
```python
rule outputsyml:
    input:
        qc = rules.prolfqua_qc.output.zip,
        diann = rules.zip_diann_result.output.zip,
        libs = f"DIANN_Libs_WU{WORKUNITID}.zip" if INCLUDE_LIBS else []
    output:
        yaml = "outputs.yml"
    run:
        libs_zip = input.libs if INCLUDE_LIBS else None
        write_outputs_yml(output.yaml, input.diann, input.qc, libs_zip=libs_zip)
```

### 6. Update `write_outputs_yml()` (`src/diann_runner/snakemake_helpers.py`)

Add optional `libs_zip` parameter:

```python
def write_outputs_yml(output_file: str, diann_zip: str, qc_zip: str, libs_zip: str | None = None) -> None:
    outputs = [
        {"local_path": str(Path(diann_zip).resolve()), "store_entry_path": diann_zip, "type": "bfabric_copy_resource"},
        {"local_path": str(Path(qc_zip).resolve()), "store_entry_path": qc_zip, "type": "bfabric_copy_resource"},
    ]
    if libs_zip:
        outputs.append({"local_path": str(Path(libs_zip).resolve()), "store_entry_path": libs_zip, "type": "bfabric_copy_resource"})
    data = {"outputs": outputs}
    with open(output_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
```

---

## Files Modified

| File | Change |
|------|--------|
| `bfabric_executable/executable_A386_DIANN_3.2.xml` | Add `14_include_libs` BOOLEAN parameter |
| `src/diann_runner/snakemake_helpers.py` | Parse `include_libs`; exclude `report-lib.*` from main zip; add `zip_library_files()`; update `write_outputs_yml()` |
| `src/diann_runner/Snakefile.DIANN3step.smk` | Add `INCLUDE_LIBS` global; conditional `zip_diann_libs` rule; update `outputsyml` rule inputs |

## Existing Functions Reused

- `zip_diann_results()` at `snakemake_helpers.py:410` — modified to filter out library files
- `write_outputs_yml()` at `snakemake_helpers.py:13` — extended with optional `libs_zip`
- `parse_flat_params()` at `snakemake_helpers.py:175` — extended with `include_libs`
- `get_final_quantification_outputs()` at `snakemake_helpers.py:345` — no change needed (library key stays for dependency tracking)

## Verification

1. **Unit tests**: Run `python3 -m pytest tests/` — update `test_workflow.py` if `zip_diann_results` tests exist
2. **Dry run with include_libs=false** (default): Verify main zip excludes `report-lib.*` files, no libs zip created
3. **Dry run with include_libs=true**: Verify `DIANN_Libs_WU{id}.zip` is created with all library files, and `outputs.yml` has 3 entries
4. **Check both workflow modes**: Ensure single-step and two-step both work correctly
