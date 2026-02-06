# Should We Remove Step C (Three-Step Workflow)?

## Status

Step C is **already disabled in production** — the `02_workflow_enable_step_c` parameter is commented out in the Bfabric XML executable with a default of `false`. We never use the three-step workflow.

## What Step C Does

The three-step workflow allows using different file sets for library refinement (Step B) and final quantification (Step C). The use case is: build a refined library from a small pilot set in Step B, then quantify a larger set (50+ files) in Step C.

In practice, we always run Step A (predicted library) + Step B (refinement + quantification) as a two-step workflow.

## Code Overhead: ~316 lines (~14% of core codebase)

| Module | Total Lines | Step C Lines | % |
|--------|------------|-------------|---|
| `workflow.py` | 695 | ~134 | 19% |
| `Snakefile.DIANN3step.smk` | 392 | ~39 | 10% |
| `snakemake_helpers.py` | 611 | ~36 | 6% |
| `test_workflow.py` | 570 | ~107 | 19% |
| **Total** | **2,268** | **~316** | **14%** |

### Breakdown by component

**workflow.py (~134 lines):**
- `generate_step_c_final_quantification()` method (~46 lines)
- `generate_all_scripts()` orchestration method (~68 lines)
- `self.quant_c_dir` attribute and related init (~5 lines)
- Conditional logic inside shared `generate_quantification_step()` (~15 lines)

**Snakefile.DIANN3step.smk (~39 lines):**
- `rule run_diann_step_c` (~27 lines)
- Step C output specs in `rule diann_generate_scripts` (~7 lines)
- `ENABLE_STEP_C` global variable and helper wrapper (~5 lines)

**snakemake_helpers.py (~36 lines):**
- `get_final_quantification_outputs()` routing function (~32 lines)
- `enable_step_c` parsing in `parse_flat_params()` (~4 lines)

**test_workflow.py (~107 lines):**
- `test_step_c_generation()` (~27 lines)
- `test_different_files_b_vs_c()` (~32 lines)
- Step C assertions in DDA mode, protein grouping, log file, and custom library tests (~48 lines)

## What Removal Would Look Like

1. Delete `generate_step_c_final_quantification()` from `workflow.py`
2. Simplify `generate_all_scripts()` to only generate Steps A + B
3. Remove Step C conditional logic from `generate_quantification_step()`
4. Remove `rule run_diann_step_c` from the Snakefile
5. Remove `get_final_quantification_outputs()` from `snakemake_helpers.py`
6. Drop `enable_step_c` parameter from helpers, XML, and config
7. Remove Step C test cases
8. Consider renaming `Snakefile.DIANN3step.smk` to `Snakefile.DIANN.smk`

**Estimated savings:** ~280-320 lines removed.

## Arguments for Removing

- Dead code in production (already disabled in Bfabric XML)
- 14% less code to maintain, read, and reason about
- Simpler mental model for contributors
- Fewer test cases to maintain
- Could simplify `generate_all_scripts()` significantly

## Arguments for Keeping

- Architecturally clean and isolated (gated behind single `enable_step_c` flag)
- Zero runtime cost when disabled
- No scattered conditionals making the code confusing
- Removal is low-risk but also low-reward
- Could be useful if workflow requirements change in the future

## Decision

- [ ] Remove Step C support
- [ ] Keep Step C support
