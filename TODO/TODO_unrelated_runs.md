# TODO: Wire the DIA-NN "freestyle" parameter through the pipeline (`13_diann_freestyle`)

Reported by Tobi (2026-06-22), workunit **WU347617**
("DIA-NN 2.6.0 QC search vs UP000005640 1-spg, unrelated runs available").
Symptom: `--unrelated-runs` was set in the freestyle field but **never appears in
the generated `step_*.sh` scripts or the DIA-NN log**.

There are **two independent problems**. Both must be addressed.

> **STATUS 2026-06-22 — IMPLEMENTED.** Freestyle is now wired to steps B/C only, and a
> dedicated `Unrelated Runs` checkbox (`05c_diann_unrelated_runs` → `--individual-mass-acc
> --individual-windows`) was added to both XML executables. Files changed: `param_core.py`
> (`_freestyle` transform + `freestyle`/`unrelated_runs` FieldSpecs), `snakemake_helpers.py`
> (BFABRIC map + `create_diann_workflow`), `sushi_adapter.py` (SUSHI map), `workflow.py`
> (ctor + `to_config_dict` + B/C builders), `request.py` (`DiannParams` fields),
> `docs/DIANN_PARAMETERS.md` (doc fix), both `executable_*.xml`. Tests: 210 passed,
> 6 skipped. Verified WU347617's real `params.yml` now yields
> `freestyle=['--unrelated-runs']`. **Still TODO: tell Tobi `--unrelated-runs` is not a
> real DIA-NN flag — re-run with the new checkbox (or freestyle
> `--individual-mass-acc --individual-windows`).**

---

## Problem 1 — the freestyle parameter is completely unwired (pipeline bug)

The value travels correctly through the early stages and is then silently dropped:

| Stage | Status | Where |
|-------|--------|-------|
| `workunit_definition.yml` → `13_diann_freestyle: --unrelated-runs` | ✅ present | bfabric |
| `work/params.yml` → `13_diann_freestyle: --unrelated-runs` | ✅ present | dispatch |
| `parse_flat_params()` keeps only keys in `BFABRIC_TO_DRUNNER` | ❌ **dropped here** | `snakemake_helpers.py:308-310` |
| `DIANN_FIELDS` transform table | ❌ no `freestyle` field | `param_core.py:77-116` |
| `DiannWorkflow.__init__` | ❌ no `freestyle`/`extra_args` arg | `workflow.py:66-101` |
| `_build_common_params()` | ❌ nothing appended | `workflow.py:293-348` |

Root cause: `13_diann_freestyle` is **not** a key in
[`BFABRIC_TO_DRUNNER`](../src/diann_runner/snakemake_helpers.py) (the map jumps from
`12b_diann_quantification_no_norm` straight to `99_other_verbose`). The dict-comprehension
adapter filters out any key not in the map, so the field never becomes a canonical
parameter and is invisible to every downstream layer.

The SUSHI path has the same gap — `sushi_adapter.py:39` explicitly documents
`freestyle` as **"unwired downstream"**, and all test fixtures carry `freestyle: None`,
which is why nobody hit this until a real value was supplied.

## Problem 2 — `--unrelated-runs` is NOT a valid DIA-NN CLI flag (value bug)

Research into the DIA-NN source (vdemichev/DiaNN) shows the **GUI "Unrelated runs"
checkbox does not emit `--unrelated-runs`**. From `GUI/GUI/Form1.cs:417`:

```csharp
if (S.unrelated_b) process.StartInfo.Arguments += " --individual-mass-acc --individual-windows";
```

The string `--unrelated-runs` appears **zero** times anywhere in the DIA-NN repo.
So even after Problem 1 is fixed, passing the literal `--unrelated-runs` would feed
DIA-NN an **unknown argument** and would not produce the intended behaviour.

### What "Unrelated runs" actually does (research summary)
- When mass accuracy / scan window are set to automatic (`0.0` / `AUTO`), DIA-NN by
  default determines tolerances from the **first run** and applies them to all runs.
- "Unrelated runs" instead determines mass accuracies and scan window **independently
  for each run** — correct when runs do not share common peptides / calibration.
- CLI equivalent: **`--individual-mass-acc --individual-windows`**.
- With MBR (`--reanalyse`): in the second MBR pass the same settings are used for all
  runs regardless.
- Our `docs/DIANN_PARAMETERS.md:136-139` lists `--unrelated-runs` as if it were a real
  flag — **that doc entry is wrong / misleading and should be corrected** to point at
  `--individual-mass-acc --individual-windows`.

### GUI behaviour of the flags (from `GUI/GUI/Form1.{cs,Designer.cs}`)
- **Default state: OFF (unchecked).** The `IndividualRunsCheck` checkbox has no
  `.Checked = true` in the Designer, so WinForms defaults it to unchecked. DIA-NN's own
  default is therefore "runs are related" (first-run calibration). → **our default must
  also be OFF**, both for freestyle (empty) and for any dedicated checkbox we add.
- **Always used together.** The two flags are emitted only at `Form1.cs:417`, as a single
  hard-coded pair driven by **one** checkbox (`unrelated_b`). Neither
  `--individual-mass-acc` nor `--individual-windows` is ever emitted independently by the
  GUI. Treat them as one inseparable logical toggle.
- Official tooltip text (verbatim): *"Different runs will be treated as unrelated, i.e.
  mass accuracy (when automatic) will be determined separately, as well as the retention
  time scan window"*.

### Recommendation
- Keep DIA-NN's default: **off** unless the user knows the runs are unrelated /
  uncalibrated relative to each other.
- Because this is a single, well-defined, commonly-wanted toggle, the cleaner long-term
  fix is a **dedicated checkbox parameter** (Section F below), not relying on freestyle.
  Freestyle still needs wiring (general fix + lets power users pass other flags), but the
  "Unrelated runs" toggle deserves a first-class boolean.

**Action item:** confirm with Tobi/Witold that the intent is the per-run calibration
behaviour, i.e. the freestyle value should be `--individual-mass-acc --individual-windows`,
not `--unrelated-runs`. The freestyle field is a free passthrough, so we should NOT
whitelist/validate flag names — but we should fix the docs and tell the requester the
correct value.

---

## Plan

### A. Decide design (do first)
- [x] **Scope: B and C only (DECIDED).** Step A (`generate_step_a_library`) is pure
      FASTA→predicted-library prediction with **no `--f` raw files**, so run-calibration
      flags have nothing to act on there (inert at best, needless risk for arbitrary
      freestyle at worst). Freestyle goes only to the steps that read spectra. →
      **Do NOT add freestyle to `_build_common_params()`** (it is shared by A/B/C).
      Instead append `self.freestyle` inside the step-B and step-C command builders,
      after their `_build_common_params()` call.
      Note: the GUI runs DIA-NN as one invocation; our 3-step split means B+C scoping
      reproduces the GUI's effective behaviour exactly (step A has no runs to calibrate).
- [ ] **Placement in command:** append freestyle tokens **last** in the step B/C command
      (after common params + step-specific flags) so a user can override earlier
      auto-generated flags if DIA-NN honours last-wins.
- [ ] **Canonical field name:** `freestyle` (keep the bfabric/sushi vocabulary word).
      Internal representation: `list[str]` of tokens.
- [ ] **Sentinel handling:** `None` / empty string → `[]` (matches existing fixtures
      `freestyle: 'None'`).
- [ ] **Tokenisation:** use `shlex.split()` so quoted args survive, not naive `.split()`.

### B. Wire it through (4 layers + config + sushi)
1. [ ] `snakemake_helpers.py` `BFABRIC_TO_DRUNNER`: add
       `"13_diann_freestyle": "freestyle"`.
2. [ ] `param_core.py`:
   - add a `_freestyle(value)` transform → `[] if str(value) in {"", "None"} else shlex.split(value)`.
   - add `"freestyle": FieldSpec("diann", _freestyle, default=[])` to `DIANN_FIELDS`
     (note: default is a fresh `[]` per call — FieldSpec default is a shared object, so
     return a new list from the transform and never mutate the default; mirror the
     `var_mods` handling which builds a fresh list).
   - surface it in `build_internal_params()` output (it already flows via the `diann`
     sub-dict since section="diann"; verify `create_diann_workflow` can read it).
3. [ ] `sushi_adapter.py` `SUSHI_TO_DRUNNER`: map the SUSHI `freestyle` key →
       `freestyle` so both callers converge (remove the "unwired downstream" note).
4. [ ] `workflow.py` `DiannWorkflow.__init__`: add `freestyle: list[str] | tuple = ()`,
       store `self.freestyle = list(freestyle)`; add to `to_config_dict()` and confirm
       `from_config_file()` round-trips (it uses `cls(**config)`).
5. [ ] `workflow.py` — **B and C only** (NOT `_build_common_params`): in the step-B and
       step-C command builders, after `cmd.extend(self._build_common_params())`, append
       `cmd.extend(self.freestyle)` (tokens already shlex-split, no extra quoting).
       Leave `generate_step_a_library` untouched.
6. [ ] `snakemake_helpers.py` `create_diann_workflow()`: pass
       `freestyle=diann_params.get("freestyle", [])` (or required-key per fail-fast policy
       once the default is guaranteed by `build_internal_params`).

### C. Docs
7. [ ] Fix `docs/DIANN_PARAMETERS.md:136-139`: `--unrelated-runs` is the **GUI label**, the
       real flags are `--individual-mass-acc --individual-windows`.

### D. Tests
8. [ ] `param_core`: `13_diann_freestyle: "--individual-mass-acc --individual-windows"`
       → canonical `freestyle == ["--individual-mass-acc", "--individual-windows"]`;
       `None` → `[]`; quoted arg survives shlex.
9. [ ] `workflow`: with `freestyle=["--individual-mass-acc","--individual-windows"]`, both
       flags appear in the generated **step B and step C** command strings and are
       **absent from step A**; empty freestyle adds nothing anywhere.
10. [ ] End-to-end-ish: feed a `params.yml`-shaped dict through
        `parse_flat_params` → `create_diann_workflow` → assert flags in `step_*.sh`.
11. [ ] Keep baseline green: `uv run python -m pytest tests/` (176 passed, 6 skipped on
        this branch — see workspace CLAUDE.md host gotchas re: `defaults_server.yml`).

### E. Validate against the real workunit
12. [ ] Re-generate scripts for a WU347617-shaped input via `./run_apprunner.sh -n`
        (dry-run) in `/scratch/wolski`, or regenerate `step_*.sh` in
        `A386_DIANN/WU347617/work/`, and confirm the freestyle flags now appear.
13. [ ] Report back to Tobi: (a) freestyle is now wired; (b) the correct value for the
        "Unrelated runs" behaviour is `--individual-mass-acc --individual-windows`, not
        `--unrelated-runs`.

### F. (Recommended) Dedicated "Unrelated runs" checkbox — first-class parameter
Rather than asking users to type `--individual-mass-acc --individual-windows` into
freestyle, add a proper boolean, following the project's "XML is source of truth" flow.
Treat the two CLI flags as one inseparable toggle (the GUI does).
- [ ] **XML** (`bfabric_executable/executable_A386_DIANN_3.2.xml` +
      `slurmworker/config/A386_DIANN_23/executable_A386_DIANN23plus.xml`): add a boolean,
      e.g. `05c_diann_unrelated_runs` (near scan-window / mass-acc params), **default
      `false`** to match DIA-NN. Reuse the official tooltip text.
- [ ] **`BFABRIC_TO_DRUNNER`**: `"05c_diann_unrelated_runs": "unrelated_runs"`.
- [ ] **`SUSHI_TO_DRUNNER`**: add the matching SUSHI key → `unrelated_runs`.
- [ ] **`param_core.DIANN_FIELDS`**: `"unrelated_runs": FieldSpec("diann", _to_bool, default=False)`.
- [ ] **`DiannWorkflow`**: `unrelated_runs: bool = False`; in **step B and C** builders,
      `if self.unrelated_runs: cmd += ["--individual-mass-acc", "--individual-windows"]`.
      Add to `to_config_dict()`.
- [ ] **Tests**: checkbox true → both flags on B and C, none on A; false → none.
- Decision needed: ship BOTH (freestyle passthrough *and* the checkbox), or checkbox
  only? Recommend BOTH — freestyle is the general escape hatch; the checkbox is the
  discoverable, mistake-proof path for this specific, common option.

---

## Open questions for Tobi / Witold
- Confirm intent = per-run mass-acc/window calibration → use
  `--individual-mass-acc --individual-windows` (NOT `--unrelated-runs`).
- **Scope: DECIDED → freestyle goes to B and C only** (step A has no runs). No longer open.
- Add the dedicated **"Unrelated runs" checkbox** (Section F) in addition to the freestyle
  fix? Recommend yes.
- Do we want any guard rails on freestyle at all, or pure passthrough? (Recommend pure
  passthrough + doc fix; no flag whitelist.)

## Key references
- DIA-NN GUI mapping: `vdemichev/DiaNN` → `GUI/GUI/Form1.cs:417`
- DIA-NN README "Unrelated runs" (LC-MS-specific parameters section)
- Local: `snakemake_helpers.py` (BFABRIC_TO_DRUNNER, parse_flat_params, create_diann_workflow),
  `param_core.py` (DIANN_FIELDS, build_internal_params), `workflow.py`
  (`__init__`, `_build_common_params`, `to_config_dict`), `sushi_adapter.py`.
