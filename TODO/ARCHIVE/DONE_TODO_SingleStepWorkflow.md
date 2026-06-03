# Add Single-Step DIA-NN Workflow

## Goal

Add a `workflow_mode` parameter (`single_step` / `two_step`). Single-step combines library prediction + quantification in one DIA-NN call. Two-step is the existing A + B flow. Both write final outputs to the **same directory** (`out-DIANN_quantB/`), so downstream rules are untouched.

Step C removal is a separate task (see `TODO_Shall_we_keep_step_3.md`).

## Single-step DIA-NN command (from DIA-NN 2.3.2 GUI)

```
diann.exe --f sample1.raw --f sample2.raw ... \
  --lib --fasta database.fasta --fasta-search --predictor \
  --gen-spec-lib --out-lib C:\Temp\report-lib.parquet \
  --out results/report.parquet --temp temp/ \
  --threads 32 --qvalue 0.01 --matrices --pg-level 1 \
  --cut K*,R* --missed-cleavages 1 --min-pep-len 7 --max-pep-len 30 \
  --min-pr-mz 380 --max-pr-mz 980 --min-pr-charge 1 --max-pr-charge 5 \
  --min-fr-mz 150 --max-fr-mz 2000 \
  --met-excision --unimod4 --var-mods 1 --var-mod UniMod:35,15.994915,M \
  --relaxed-prot-inf --reanalyse --rt-profiling --verbose 1
```

## Parameters: identical for both modes

All user-configurable parameters are the same. `_build_common_params()` is reused as-is (plus new `rt_profiling`). The only differences are structural flags set by the code:

| Flag | Single-step | Two-step (lib prediction) | Two-step (quantification) |
|------|------------|---------------------------|---------------------------|
| `--lib` | empty | n/a | path to predicted lib |
| `--fasta-search` | yes | yes | no |
| `--predictor` | yes | yes | no |
| `--out-lib` | explicit path | no | no |
| `--reannotate` | no | no | yes |
| `--f` raw files | yes | **no** | yes |

m/z ranges (`--min-pr-mz` etc.) are required in both modes — DIA-NN does not auto-detect them from raw data.

## Changes by file

### 1. `workflow.py` — add `generate_single_step()` (~50 lines added, 0 deleted)

Add `rt_profiling: bool = False` to `__init__` (line 98), `self.rt_profiling` assignment (after line 171), `to_config_dict()` (after line 216).

Add to `_build_common_params()` (after line 298):
```python
if self.rt_profiling:
    params.append("--rt-profiling")
```

Add new method (after `generate_step_b_quantification_with_refinement`, line 579):
```python
def generate_single_step(
    self,
    fasta_paths: str | list[str],
    raw_files: list[str],
    script_name: str = 'run_diann.sh',
) -> str:
    """Generate single DIA-NN invocation: predict library + quantify."""
    if isinstance(fasta_paths, str):
        fasta_paths = [fasta_paths]

    output_dir = self.quant_b_dir              # same dir as two-step quantification
    temp_dir = f"{self.temp_dir_base}_quantB"
    output_file = f"{output_dir}/{self.workunit_id}_report.parquet"
    output_lib = f"{output_dir}/{self.workunit_id}_report-lib.parquet"
    log_file = f"{output_dir}/diann_quantB.log.txt"

    cmd = [f'"{self.diann_bin}"']
    if self.docker_image:
        cmd.append(f'--image {self.docker_image}')
    cmd.append('--')

    # Library-free mode
    cmd.append("--lib")
    # FASTA + prediction
    cmd.append("--fasta-search")
    for fasta_path in fasta_paths:
        cmd.append(f'--fasta "{fasta_path}"')
    cmd.append("--predictor")
    # Raw files
    for f in raw_files:
        cmd.append(f"--f {f}")
    # Shared params
    cmd.extend(self._build_common_params())
    # Quantification
    cmd.append("--matrices")
    cmd.append(f"--pg-level {self.pg_level}")
    if self.relaxed_prot_inf:
        cmd.append("--relaxed-prot-inf")
    if self.reanalyse:
        cmd.append("--reanalyse")
    if self.no_norm:
        cmd.append("--no-norm")
    if self.is_dda:
        cmd.append("--dda")
    # Library output
    cmd.append("--gen-spec-lib")
    cmd.append(f'--out-lib "{output_lib}"')
    # Output
    cmd.append(f'--out "{output_file}"')
    cmd.append(f'--temp "{temp_dir}"')

    self._write_shell_script(
        script_path=script_name, commands=cmd,
        temp_dirs=[temp_dir], output_dirs=[output_dir], log_file=log_file,
    )
    self.save_config(f"{output_dir}/{self.workunit_id}_quantB")
    return script_name
```

### 2. `snakemake_helpers.py` — add parsing (~5 lines added, 0 deleted)

In `parse_flat_params()`, after line 263:
```python
workflow_mode = flat_params.get('02_workflow_mode', 'two_step')
rt_profiling = flat_params.get('13_diann_rt_profiling', 'false').lower() == 'true'
```

Add to return dict (line 270):
```python
'workflow_mode': workflow_mode,
'rt_profiling': rt_profiling,
```

In `create_diann_workflow()`, add `rt_profiling` param from `diann_params`:
```python
rt_profiling=diann_params.get("rt_profiling", False),
```

### 3. `Snakefile.DIANN3step.smk` — conditional rules (~25 lines added, 0 deleted)

After line 62 (`FINAL_QUANT_OUTPUTS = ...`), add:
```python
WORKFLOW_MODE = WORKFLOW_PARAMS.get("workflow_mode", "two_step")
```

Replace the DIA-NN rules section (lines 135–253) with a conditional block. Existing two-step rules go inside `else:` unchanged. New single-step branch:

```python
if WORKFLOW_MODE == "single_step":

    rule diann_generate_script:
        """Generate single-step DIA-NN script."""
        input:
            mzml_files = [get_converted_file(sample) for sample in SAMPLES],
            fasta_files = FASTA_PATHS,
        output:
            script = "run_diann.sh",
            config = f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_quantB.config.json"
        run:
            fasta_paths = [str(f) for f in input.fasta_files]
            workflow = create_diann_workflow(
                WORKUNITID, OUTPUT_PREFIX, DIANNTEMP,
                fasta_paths[0], WORKFLOW_PARAMS["var_mods"],
                WORKFLOW_PARAMS["diann"], deploy_dict
            )
            raw_files = [str(f) for f in input.mzml_files]
            workflow.generate_single_step(fasta_paths=fasta_paths, raw_files=raw_files)

    rule run_diann:
        """Execute single-step DIA-NN: library prediction + quantification."""
        input:
            script = rules.diann_generate_script.output.script
        output:
            speclib = f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report-lib.parquet",
            report = f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report.parquet",
            pg_matrix = f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report.pg_matrix.tsv",
            stats = f"{OUTPUT_PREFIX}_quantB/WU{WORKUNITID}_report.stats.tsv",
            runlog = f"{OUTPUT_PREFIX}_quantB/diann_quantB.log.txt"
        params:
            copy_fasta_cmd = lambda wildcards: copy_fasta_if_missing(
                f"{OUTPUT_PREFIX}_quantB", fasta_config["database_path"])
        shell:
            """
            bash {input.script}
            {params.copy_fasta_cmd}
            """

else:  # two_step — existing rules unchanged

    rule diann_generate_scripts:
        ...  # lines 139-178 unchanged

    rule run_diann_step_a:
        ...  # lines 184-202 unchanged

    rule run_diann_step_b:
        ...  # lines 204-225 unchanged

    rule run_diann_step_c:
        ...  # lines 227-253 unchanged
```

Downstream rules (lines 255–393) are **completely unchanged** — they reference `FINAL_QUANT_OUTPUTS` which already points to `out-DIANN_quantB/` when `enable_step_c=False`.

### 4. Bfabric XML — add parameters (~10 lines)

Add `workflow_mode` and `rt_profiling` parameters.

## Why this is minimal

| What | Lines added | Lines deleted | Lines modified |
|------|-----------|---------------|----------------|
| `workflow.py`: `generate_single_step()` + `rt_profiling` | ~55 | 0 | 0 |
| `snakemake_helpers.py`: parsing | ~5 | 0 | ~2 |
| `Snakefile`: conditional + single-step rules | ~30 | 0 | ~2 (indent existing into else) |
| Bfabric XML | ~10 | 0 | 0 |
| Tests | ~40 | 0 | 0 |
| **Total** | **~140** | **0** | **~4** |

- Existing two-step code is untouched (just wrapped in `else:`)
- `_build_common_params()` reused as-is (+ 2 lines for `rt_profiling`)
- `_write_shell_script()`, `save_config()` reused as-is
- Output directory is `out-DIANN_quantB/` in both modes — downstream rules unchanged
- `FINAL_QUANT_OUTPUTS` works as-is (already points to quantB when `enable_step_c=False`)
- Step C removal is deferred to a separate task

## Implementation order

1. Add `rt_profiling` to `DiannWorkflow.__init__`, `to_config_dict()`, `_build_common_params()`
2. Add `generate_single_step()` method to `DiannWorkflow`
3. Add `workflow_mode` + `rt_profiling` parsing in `snakemake_helpers.py`
4. Add conditional rules in Snakefile
5. Add Bfabric XML parameters
6. Add tests for `generate_single_step()`

## Open questions

- [ ] **`--rt-profiling` default?** DIA-NN GUI enables it. Default `true` or `false`?
- [ ] **`--lib` (empty) via Docker?** Verify `diann-docker` passes `--lib` with no value correctly.
- [ ] **`--out-lib` path?** Current plan: output dir. DIA-NN GUI example uses temp. Keep in output dir so library is preserved alongside results.
