# TODO: Protein Grouping Level (`--pg-level`) — wrong labels + wrong/inconsistent defaults

> **STATUS: FIXED (2026-06-26).** Both paths now use DIA-NN's mapping
> (`0`=isoform IDs, `1`=protein names, `2`=genes) and default to **genes
> (`--pg-level 2`)**. Enums standardized to `0_isoform_IDs` / `1_protein_names` /
> `2_genes` (numeric **prefix**; `_pg_level` reads the leading integer via
> `split("_")[0]`) in the bfabric XML (`executable_A386_DIANN_3.2.xml`) and
> `DIANNApp.rb`. apprunner behavior unchanged (already ran genes); sushi default
> flipped protein-names → genes. Also fixed `workflow.py` ctor default (`2`),
> docstring, `docs/USAGE_EXAMPLES.md`, `data/*/params.yml`, and tests. The
> analysis below is kept for the record.

`run-diann apprunner` and `run-diann sushi` are **separate entry points with
separate frontends**, so each has its **own** Protein Grouping Level default.
This writeup gives one answer per path.

---

## Shared mechanism

- `pg_level` is a **required** field with no fallback default
  (`src/diann_runner/param_core.py:114` — `FieldSpec("diann", _pg_level)`).
  So each path's effective default is **whatever its own UI pre-selects**.
- Whatever enum string is selected, `_pg_level()` takes its **leading integer**
  (numeric prefix, `split("_")[0]`, `param_core.py:66-68`) and the workflow appends it verbatim:
  `--pg-level {pg_level}` (`workflow.py:576`, `:710`).
- Both paths converge on the same `build_internal_params` core, so the *transform*
  is shared — only the **frontend vocabulary and default** differ
  (apprunner = `parse_flat_params` / B-Fabric keys; sushi = `SUSHI_TO_DRUNNER`).

### DIA-NN ground truth (`--pg-level N`)

| value | DIA-NN meaning |
|-------|----------------|
| `0`   | **isoforms** (isoform / protein-ID level) |
| `1`   | **protein names** |
| `2`   | **genes** |

DIA-NN's GUI default is **Genes** (`--pg-level 2`), the recommended/standard
choice (method optimisation, benchmarks, GSEA; most robust groups).

Sources:
- [Protein Grouping · DiaNN Discussion #107](https://github.com/vdemichev/DiaNN/discussions/107)
- [DiaNN README](https://github.com/vdemichev/DiaNN/blob/master/README.md)
- [DIA-NN protein inference · Discussion #316](https://github.com/vdemichev/DiaNN/discussions/316)

> "the `--pg-level` flag changes the definition of proteotypic from a peptide
> uniquely mapping to an isoform (0) to protein [name] (1) to gene (2)."

---

## 1. apprunner — bfabric XML executable

`diann_runner/bfabric_executable/executable_A386_DIANN_3.2.xml`

| item | value | line |
|------|-------|------|
| description | "0=genes, 1=protein names **(default)**, 2=protein IDs. DIA-NN command: --pg-level" | `:680` |
| enumerations | `genes_0`, `protein_names_1`, `protein_IDs_2` | `:682-684` |
| **default `<value>`** | `protein_IDs_2` → `--pg-level 2` | `:693` |

**Effective default:** `protein_IDs_2` → `--pg-level 2` → DIA-NN runs **genes**.

**Problems:**
- **Self-contradiction (the reported symptom):** help says default = *protein
  names*, but the selected `<value>` is `protein_IDs_2`.
- **Labels inverted vs DIA-NN:** `genes_0` → `--pg-level 0` = isoforms (not genes);
  `protein_IDs_2` → `--pg-level 2` = genes (not protein IDs). Only
  `protein_names_1` is correct.
- **Net:** at runtime apprunner does `--pg-level 2` = **genes** — which *is*
  DIA-NN's recommended default — but the label, description and stated default
  are all wrong. So behavior is accidentally right, documentation is wrong.

---

## 2. sushi — `DIANNApp.rb`

`sushi/master/lib/DIANNApp.rb:101`

```ruby
@params['protein_pg_level'] = ['protein_names_1', 'genes_0', 'isoforms_2']
```

- First array element is the SUSHI dropdown default → `protein_names_1`.
- No per-parameter help text (the `@description` heredoc at `:14` is the app
  blurb, not pg-level documentation), so no self-contradiction here.
- Maps to canonical `pg_level` via `sushi_adapter.SUSHI_TO_DRUNNER`
  (`src/diann_runner/sushi_adapter.py:65`: `"protein_pg_level": "pg_level"`).

**Effective default:** `protein_names_1` → `--pg-level 1` → DIA-NN runs
**protein names**.

**Problems:**
- **Wrong default:** protein names (1), **not** genes — differs from DIA-NN's
  recommended default *and* from what apprunner actually runs. The two products
  therefore produce **different protein groups by default** on identical data.
- **Same label inversion:** `genes_0` → isoforms; `isoforms_2` → genes. Only
  `protein_names_1` is correct.

---

## Summary

| Path | Current default value | `--pg-level` | DIA-NN actually does | == DIA-NN recommended (genes)? |
|------|----------------------|--------------|----------------------|--------------------------------|
| **apprunner** | `protein_IDs_2` | 2 | **genes** | ✅ by accident; labels/description wrong |
| **sushi** | `protein_names_1` | 1 | **protein names** | ❌ wrong default |

Other places carrying the wrong mapping text (fix alongside):
`workflow.py:91,132` (ctor default `0` + docstring), `docs/USAGE_EXAMPLES.md:321`,
`data/dia_mzml/params.yml:69`, `data/dda_mzml/params.yml:69`.

---

## Recommended fix (both paths)

Adopt DIA-NN's mapping verbatim and default to **genes (`--pg-level 2`)**.

1. **Correct enum integers** (numeric prefix) so each label matches DIA-NN behavior:
   isoform/protein-ID → `0_`, protein names → `1_`, genes → `2_`
   (i.e. `0_isoform_IDs`, `1_protein_names`, `2_genes`).
2. **apprunner** (`executable_A386_DIANN_3.2.xml`): set `<value>` (`:693`) to the
   genes enum and rewrite the description (`:680`) to the correct mapping with
   **genes** marked default.
3. **sushi** (`DIANNApp.rb:101`): put the genes enum first so it is the default.
4. Fix the supporting docs/comments and `DiannWorkflow` ctor default → `2`
   (`workflow.py:91`, docstring `:132`).
5. **Tests:** `tests/test_param_core.py:38,59` assert on the enum strings; update
   to the corrected strings/integers.

### Note
This pipeline also runs **prozor** (FASTA greedy-parsimony inference) downstream,
so `--pg-level` mainly drives DIA-NN's **native** `pg_matrix`, not the prozor
output. Genes is the safe DIA-NN-standard default; deviating is a deliberate
per-delivery choice — but the label must match the integer DIA-NN receives.

## Open question
Confirm the FGCZ default — **genes** (DIA-NN standard; recommended) — and apply it
to **both** apprunner and sushi so the two products agree.
