# TODO: Entrapment ("no digestion") search support + ProteoBench Astral run

## Origin (Slack request)

> Hi @channel, could anyone with access to or experience with additional DIA
> search engines run some on the DIA Entrapment data? So far we have DIA-NN and
> FragPipe. Mostly thinking about Spectronaut, PEAKS, alphaDIA etc.
>
> - FASTA: https://proteobench.cubimed.rub.de/fasta/ProteoBenchFASTA_Entrapment_Human_with_contaminants_entrapment_pep.zip
> - Raws:  https://proteobench.cubimed.rub.de/raws/DIA-astral/human/
>
> **Important: the FASTA is already digested, so you have to turn off the search
> engine digestion.** For now no variable modifications, or only methionine
> oxidation. Any FDR is fine.

Our own goal:
- **Part 1** — add a "no digestion" (pre-digested / peptide-list FASTA) mode to
  the DIA-NN app across all layers: `diann-runner`, the AppRunner / B-Fabric
  executable, and the SUSHI app.
- **Part 2** — use that implementation to run the ProteoBench Astral human
  entrapment data on `/scratch`, across all supported DIA-NN versions and a small
  parameter sweep, **from the CLI (no B-Fabric / SUSHI GUI clicking)** — then
  submit to ProteoBench.

---

## Background: how DIA-NN disables digestion

DIA-NN performs in-silico digestion of the FASTA during library prediction
(Step A). To use a FASTA whose entries are **already peptides** (the entrapment
FASTA, `..._entrapment_pep`), digestion must be turned off so each FASTA record
is taken verbatim as a precursor candidate.

The mechanism is an **empty `--cut`**: `--cut ''` (no cleavage specificity)
disables enzymatic digestion. `--missed-cleavages` then becomes meaningless and
must be pinned to `0`. Peptide length / m/z / charge range filters still apply as
plain filters on the supplied peptide list.

Good news: the engine already emits `--cut '{self.cut}'`
([workflow.py:324](../src/diann_runner/workflow.py#L324)), so an **empty** cut
value already produces the correct `--cut ''`. The gap is purely that nothing
upstream can *express* "empty / off", and that missed-cleavages is not forced to
`0`.

---

## Part 1 — Implementation plan (diann-runner + AppRunner/B-Fabric + SUSHI)

### Design decision: sentinel

Introduce a GUI enumeration value **`no digestion`** that maps to an empty cut
string internally. Rationale: keeps the DIA-NN-native `--cut` semantics, adds no
new boolean to the API surface, and reads clearly in the GUI. (Existing sentinel
convention: `AUTO` for "auto-determine"; this is the analogous "off" value for
`cut`.)

`no digestion` → internal `digestion_cut = ""` → `--cut ''` + forced
`--missed-cleavages 0`.

> Alternative considered: a separate boolean `no_digestion`. Rejected — extra API
> surface for something a cut sentinel already expresses (CLAUDE.md: keep
> interfaces minimal).

### Parameter flow (both frontends converge on the shared core)

Both frontends rename `lib_digestion_cut` → canonical `digestion_cut` and hand it
to the shared transform core in `param_core.py`; the sentinel→`""` transform lives
there **once**, so a single change covers AppRunner and SUSHI:

```text
AppRunner / B-Fabric executable enum "no digestion"
  → params.yml (lib_digestion_cut) → parse_flat_params()  [BFABRIC_TO_DRUNNER]
                                                            ─┐
SUSHI DIANNApp.rb enum "no digestion"                        ├→ digestion_cut
  → sushi_params.yml → parse_sushi_params()  [SUSHI_TO_DRUNNER]┘
  → param_core._digestion_cut ("no digestion" → "")
  → DiannWorkflow(cut="")  → --cut '' + forced --missed-cleavages 0
```

This answers "does the plan cover AppRunner?" directly: yes, via the executable
YAML + `parse_flat_params()` + `param_core`, the same chain SUSHI uses.

### Layer-by-layer changes

**1. Shared param core — [`src/diann_runner/param_core.py`](../src/diann_runner/param_core.py)**
- Replace the plain `str` transform on `digestion_cut`
  ([:107](../src/diann_runner/param_core.py#L107)) with a `_digestion_cut`
  transform that maps the GUI sentinel `"no digestion"` (and defensively
  `"none"`/empty) to `""`. Any real cut spec passes through unchanged.
- This is the single root-cause layer for both callers (both adapters delegate to
  `build_internal_params()`).

**2. Engine — [`src/diann_runner/workflow.py`](../src/diann_runner/workflow.py)**
- `_build_common_params()` around [:324](../src/diann_runner/workflow.py#L324):
  `--cut '{self.cut}'` already emits `--cut ''` for an empty cut. **Force**
  `--missed-cleavages 0` when `self.cut == ""`
  ([:333](../src/diann_runner/workflow.py#L333)); a normal cut keeps emitting the
  configured missed-cleavages.
- No new constructor arg — reuse the existing `cut` param (empty = off). Update
  the `cut` docstring to note "empty string = digestion off".

**3. Adapters — no key change needed.** Both
[`sushi_adapter.py:45`](../src/diann_runner/sushi_adapter.py#L45)
(`SUSHI_TO_DRUNNER["lib_digestion_cut"] = "digestion_cut"`) and
[`snakemake_helpers.py:254`](../src/diann_runner/snakemake_helpers.py#L254)
(`BFABRIC_TO_DRUNNER["lib_digestion_cut"] = "digestion_cut"`) already rename to
`digestion_cut`; the transform in `param_core` covers both entry paths. Add
adapter-level tests (below) so this stays true.

**4. AppRunner / B-Fabric executable YAML — required in BOTH copies**
- [`bfabric_executable/executable_A386_DIANN_3.2.yaml`](../bfabric_executable/executable_A386_DIANN_3.2.yaml)
  `lib_digestion_cut` enum ([:181-189](../bfabric_executable/executable_A386_DIANN_3.2.yaml#L181)):
  add `no digestion` to the enumeration; update the description to explain it
  disables digestion for pre-digested / peptide-list FASTAs.
- Mirror the identical enum + description edit in the deployed slurmworker copy
  `../slurmworker/config/A386_DIANN_23/executable_A386_DIANN23plus.yaml`. This is
  **required, not "likely both"** — `tests/test_executable_contract.py` asserts the
  two copies are identical (`test_slurmworker_mirror_identical`).
- **Pre-existing drift note:** the mirror test already fails today because the two
  copies' `input_fasta_databases` enumerations differ (slurmworker carries newer
  2026 FASTA paths; diann_runner carries 2023 ones). That FASTA sync is a separate
  problem, orthogonal to this feature — do **not** guess-reconcile the FASTA lists
  here. Keep the `lib_digestion_cut` section byte-identical between the two so this
  change introduces no *new* divergence.

**5. SUSHI app — [`gstore/sushi/master/lib/DIANNApp.rb`](../../sushi/master/lib/DIANNApp.rb#L69)**
- `@params['lib_digestion_cut']` ([:69](../../sushi/master/lib/DIANNApp.rb#L69)):
  **Decision (resolved):** align SUSHI's cut list to the YAML (the source of truth
  per AGENTS.md) plus the sentinel. `['K*,R*', 'K*', 'R*']` →
  `['K*,R*', 'K*,R*,!*P', 'no digestion']`. Both frontends now expose the identical
  cut enum. (SUSHI's standalone `K*` / `R*` presets are dropped in favor of the
  YAML set; the hard requirement — both expose the literal `no digestion` sentinel —
  is satisfied.)

**6. Tests — [`tests/`](../tests/)** (engine + core + BOTH caller paths)
- `tests/test_param_core.py`: `_digestion_cut` maps `no digestion`, `none`, and
  empty string to `""`; a real cut (`K*,R*`) passes through.
- `tests/test_workflow.py`: `DiannWorkflow(cut="", missed_cleavages=2)` emits
  `--cut ''` **and** `--missed-cleavages 0`; assert this on both a Step A script
  and the single-step path (shared `_build_common_params()` contract), and a
  negative control that a normal cut keeps the configured missed-cleavages.
- `tests/test_snakemake_helpers.py`: AppRunner `parse_flat_params({..., "lib_digestion_cut": "no digestion"})`
  yields `params["lib"]["digestion_cut"] == ""`.
- `tests/test_run_diann_cli.py`: SUSHI `parse_sushi_params()` with
  `lib_digestion_cut: no digestion` yields the same internal `""`.
- `tests/test_create_workflow_mapping.py`: with `lib_digestion_cut="no digestion"`,
  the nested params still reach `DiannWorkflow.cut == ""` and the generated command
  shows `--cut ''` + `--missed-cleavages 0`.
- `tests/test_executable_contract.py`: executable YAML defaults parse, enum strings
  are valid; the slurmworker mirror check remains (already xfail-y due to the
  pre-existing FASTA drift above).
- Per AGENTS.md: tests use the exact strings the executable defines (`no digestion`).

### Downstream considerations
- **Prozor / protein inference** ([`prozor_diann.py`](../src/diann_runner/prozor_diann.py)):
  a peptide-list FASTA makes protein grouping degenerate. **Decision (resolved):
  bypass prozor for no-digestion runs — DONE.** Driven by the same `digestion_cut
  == ""` state (no new boolean). Implemented in the Snakefile:
  `NO_DIGESTION` gates the `run_prozor_inference` consumers so the rule drops out
  of the DAG demand-driven (`zip_diann_result` / `result_index` request `[]`
  instead of the prozor parquet), and `write_result_index(include_prozor=...)`
  omits the prozor link. Verified by a `snakemake -n` DAG test: prozor is present
  for a normal cut, absent for `no digestion`.
- **QC report / grandchild datasets**: prolfqua QC + pmultiqc read the native
  `WU{id}_report.parquet` directly (not the prozor output), so they run unchanged
  on a no-digestion result. No stripped-down mode needed.
- **Oktoberfest contrib** ([`snakemake_helpers.py:837`](../src/diann_runner/snakemake_helpers.py#L837)):
  `cut.replace("*","").replace(",","")` yields `""` for an empty cut — harmless
  (optional, non-default predictor path), no change needed.
- Contaminants are already digested into the FASTA — no extra handling.

---

## Part 2 — Run the ProteoBench benchmark from the CLI

Goal: no GUI. Drive it with `run-diann` / `diann-snakemake` on an FGCZ compute
node, data staged on `/scratch`.

### CLI benchmark input dialect (explicit)
- This is **not** clicking the SUSHI GUI. `run-diann sushi` is a CLI adapter that
  reads a readable-key params file — it is chosen only because those keys are
  easier to hand-author, not because SUSHI is involved.
- Generate `sushi_params.yml` with readable keys (`lib_digestion_cut: no digestion`)
  + `input_dataset.tsv`, then `run-diann sushi ...`.
- If the goal is specifically to validate the AppRunner path too, also include one
  dry-run using an AppRunner-shaped `params.yml` (flat `lib_*` keys) through
  `parse_flat_params()`.

### Fixed inputs (per the Slack brief)
- FASTA: `ProteoBenchFASTA_Entrapment_Human_with_contaminants_entrapment_pep`
  (pre-digested peptides + contaminants).
- Raws: ProteoBench DIA-Astral human set.
- Digestion: **off** (`no digestion`).
- Mods: two arms — (a) no var-mods, (b) Met-oxidation only
  (`--var-mods 1 --var-mod UniMod:35,15.994915,M`).
- FDR: `0.01` (any is allowed; keep the default).

### Sweep
- DIA-NN versions: `2.5.1`, `2.5.0`, `2.3.2` (the three supported container
  images — see `pipeline_diann_version` in DIANNApp.rb).
- × mods arm (no-mods / Met-ox).
- Mass accuracy: `AUTO` first; consider a fixed Astral value (e.g. ms1/ms2 `4-7`
  ppm) as a second arm if AUTO underperforms.

### Harness — ✅ built as an integration case: [`tests/integration/entrapment/`](../tests/integration/entrapment/)
Mirrors `tests/integration/WU346549/` (setup script + run.sh + Makefile + README),
driven by `run-diann sushi` (readable keys, `register_outputs=False` — no B-Fabric).
- `setup_integration_test.py` downloads the entrapment FASTA (~48 MB zip → ~190 MB
  peptide-list fasta) + the 6 DIA-Astral raws (~21 GB) into `input/` (idempotent).
- `run.sh` exposes **VERSION** and **MODS** (`metox`/`nomods`): it generates a
  per-combo `sushi_params.yml` (`lib_digestion_cut: no digestion`,
  `pipeline_diann_version: $VERSION`, mods arm) and runs each combo in its own
  clearly-named folder `runs/diann-<version>-<mods>/` (work dir + outputs +
  `Result_WU<version>_<mods>.zip`). Raws read natively (`.raw`, no msconvert),
  shared read-only across combos.
- Self-contained: run from the case dir (`cd tests/integration/entrapment`) with
  `make setup` / `make run` / `make sweep` (not wired into the package-root Makefile).
  `make sweep` runs every VERSIONS(`2.3.2 2.5.0 2.5.1`) × MODS(`nomods metox`) combo.
  Verified: all 6 combos build the DAG, version+mods propagate to outputs, and
  prozor is bypassed.

**Remaining (manual, from the collected `runs/` outputs):**
- Run the sweep on an FGCZ node with the container runtime + scratch for ~21 GB raws.
- Convert each `WU{id}_report.parquet` to ProteoBench's DIA-NN input format and
  submit; keep a results table (version, mods, #precursors, entrapment FDR).

### Open questions
- Which compute node / how to stage (`fgcz-c-050`? a genomics node?) and disk
  budget for the Astral raw set.
- ProteoBench submission format specifics for the DIA-NN module (verify the
  expected report columns before generating final outputs).

---

## Order of work
1. ✅ Part 1: `param_core` transform + engine missed-cleavages force + tests
   (self-contained, verifiable locally).
2. ✅ Part 1: executable YAML (both copies) + SUSHI enum alignment + adapter/contract
   tests.
3. ✅ Prozor bypass for no-digestion runs (Snakefile + `write_result_index` + DAG test).
4. ✅ Part 2 harness — `tests/integration/entrapment/` (version × mods sweep, self-contained
   `make setup`/`run`/`sweep` in the case dir). Remaining: run it on an FGCZ node + ProteoBench submission.

> Pre-existing, out of scope: `test_slurmworker_mirror_identical` fails on the
> `input_fasta_databases` drift between the two YAML copies (unrelated to this
> feature; the `lib_digestion_cut` edit is byte-identical in both). Reconcile the
> FASTA lists as a separate sync task.
