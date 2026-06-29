"""SUSHI input adapters for ``run-diann sushi``.

SUSHI's ``DIANNApp.rb`` emits the unified param keys (``lib_mods_variable``,
``lib_peptide_min_length``, ``input_fasta_databases``, ``input_fasta_use_custom``,
…) and an ``input_dataset.tsv`` with a ``Thermo RAW [File]`` column. The dataset
shape differs from the AppRunner side (``dataset.parquet``), so the SUSHI path
needs its **own** adapters even though both frontends now share one key vocabulary.

This is the ``SUSHI_TO_DRUNNER`` adapter: it maps the SUSHI readable keys
**directly** onto diann_runner's canonical internal field names (never via the
sibling B-Fabric vocabulary) and hands them to the shared transform core
:func:`diann_runner.param_core.build_internal_params`. So the SUSHI and AppRunner
(``BFABRIC_TO_DRUNNER`` = :func:`parse_flat_params`) paths converge on identical
``DIANNRunnerParams`` while sharing no key vocabulary.

FASTA is handled separately (SUSHI carries ``fasta_databases`` — a comma-joined
path list — not the B-Fabric ``03_*`` keys); the dataset adapter normalizes the
``Thermo RAW`` column and derives the single raw-file directory from it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from diann_runner.param_core import build_internal_params
from diann_runner.request import (
    COL_GROUPING,
    COL_NAME,
    COL_RELATIVE_PATH,
    first_factor_column,
)

# SUSHI readable param name -> diann_runner canonical internal field name. Only
# the fields build_internal_params consumes are listed; SUSHI-framework params
# (cores, mail, name, …) and the FASTA keys are ignored.
SUSHI_TO_DRUNNER: dict[str, str] = {
    "pipeline_diann_version": "diann_version",
    "pipeline_workflow_mode": "workflow_mode",
    "pipeline_is_dda": "is_dda",
    "pipeline_raw_converter": "raw_converter",
    "lib_digestion_cut": "digestion_cut",
    "lib_digestion_missed_cleavages": "digestion_missed_cleavages",
    "lib_peptide_min_length": "peptide_min_length",
    "lib_peptide_max_length": "peptide_max_length",
    "lib_precursor_charge_min": "precursor_charge_min",
    "lib_precursor_charge_max": "precursor_charge_max",
    "lib_precursor_mz_min": "precursor_mz_min",
    "lib_precursor_mz_max": "precursor_mz_max",
    "lib_fragment_mz_min": "fragment_mz_min",
    "lib_fragment_mz_max": "fragment_mz_max",
    "lib_mods_variable": "mods_variable",
    "lib_mods_unimod4": "mods_unimod4",
    "lib_mods_met_excision": "mods_met_excision",
    "lib_mods_no_peptidoforms": "mods_no_peptidoforms",
    "search_mass_acc_ms1": "mass_acc_ms1",
    "search_mass_acc_ms2": "mass_acc_ms2",
    "search_mass_acc_unrelated_runs": "mass_acc_unrelated_runs",
    "search_scoring_qvalue": "scoring_qvalue",
    "search_protein_pg_level": "protein_pg_level",
    "search_protein_ids_to_names": "protein_ids_to_names",
    "quant_scan_window": "scan_window",
    "quant_reanalyse": "reanalyse",
    "quant_no_norm": "no_norm",
    "output_fragment_quant": "fragment_quant",
    "output_include_libs": "include_libs",
    "output_pmultiqc": "pmultiqc",
    "advanced_freestyle": "freestyle",
    "advanced_verbose": "verbose",
    # workflow control (no DIA-NN GUI param; not category-prefixed)
    "enable_step_c": "enable_step_c",
}

# SUSHI selects FASTA out-of-band via `input_fasta_databases` (-> fasta_paths_from_sushi,
# the request's fasta list), so the `inputs` FASTA fields are a placeholder that
# run_diann_cli._apply_fasta overwrites with the real path list before validation.
_SUSHI_FASTA_PLACEHOLDER = {"fasta_databases": [], "fasta_use_custom": False}

# SUSHI raw-file column candidates (FGCZ tags + un-suffixed fallbacks), in order.
SUSHI_RAW_COLUMNS = ("Thermo RAW [File]", "Thermo RAW", "RAW [File]", "RAW")

_EMPTY_SENTINELS = frozenset({"", "NONE", "NULL"})


def _is_unset(value: Any) -> bool:
    """True for None or a case-folded ''/NONE/NULL sentinel."""
    if value is None:
        return True
    return str(value).strip().upper() in _EMPTY_SENTINELS


def _load_flat(params_file: str | Path) -> dict[str, Any]:
    """Load the SUSHI params file (YAML flat mapping or a ``params:`` block)."""
    doc = yaml.safe_load(Path(params_file).read_text())
    if not isinstance(doc, dict):
        raise ValueError(f"SUSHI params file did not parse as a mapping: {params_file}")
    return doc.get("params", doc) if "params" in doc else doc


def fasta_paths_from_sushi(flat: dict[str, Any]) -> list[Path]:
    """Extract the FASTA paths the run should use, from the SUSHI params.

    ``input_fasta_databases`` is a comma-joined list of paths (the DIANNApp multi-select).
    ``input_fasta_use_custom`` is a checkbox today (no path) and is ignored until wired.
    """
    raw = flat.get("input_fasta_databases", "")
    if _is_unset(raw):
        return []
    return [Path(p.strip()) for p in str(raw).split(",") if not _is_unset(p)]


def parse_sushi_params(
    params_file: str | Path,
) -> tuple[dict[str, Any], list[Path], str | None]:
    """Parse a SUSHI ``sushi_params.yml`` into (workflow_params, fasta_paths, data_root).

    The readable keys are mapped directly onto canonical internal names
    (:data:`SUSHI_TO_DRUNNER`) and assembled by the shared
    :func:`diann_runner.param_core.build_internal_params`, so the SUSHI path yields
    the same nested params AppRunner does (guarded by
    ``test_matches_apprunner_for_equivalent_keys``). FASTA comes from
    ``fasta_databases``; ``data_root`` is the ``dataRoot`` key SUSHI's run_PyApp
    adds (used by :func:`parse_sushi_dataset` to resolve relative raw paths),
    ``None`` when absent.
    """
    flat = _load_flat(params_file)
    canonical = {
        SUSHI_TO_DRUNNER[k]: v for k, v in flat.items() if k in SUSHI_TO_DRUNNER
    }
    workflow_params = build_internal_params(canonical, fasta=dict(_SUSHI_FASTA_PLACEHOLDER))
    return workflow_params, fasta_paths_from_sushi(flat), flat.get("dataRoot")


def parse_sushi_dataset(
    dataset_file: str | Path, data_root: str | Path | None = None
) -> tuple[pd.DataFrame, Path]:
    """Parse a SUSHI ``input_dataset.tsv`` into (normalized_dataset, raw_dir).

    Maps the raw-file column (``Thermo RAW [File]`` / fallbacks) onto
    ``Relative Path`` and keeps ``Name``. The grouping variable is carried as
    ``Grouping Var`` when present, else from the first B-Fabric ``[Factor]``
    column (e.g. ``Condition [Factor]``); when neither exists it is left out and
    prolfquapp QC falls back to a single group. The
    raw paths are relative to ``data_root`` (SUSHI's ``dataRoot``); they are
    resolved under it to derive the single raw-file directory (common parent).
    Absolute paths are used as-is. Errors if the dataset spans more than one
    directory (``run-diann`` mounts one raw dir).
    """
    df = pd.read_csv(dataset_file, sep="\t")
    raw_col = next((c for c in SUSHI_RAW_COLUMNS if c in df.columns), None)
    if raw_col is None:
        raise KeyError(
            f"SUSHI dataset {dataset_file} has no raw-file column "
            f"(looked for {', '.join(SUSHI_RAW_COLUMNS)}). Found: {list(df.columns)}"
        )
    if COL_NAME not in df.columns:
        raise KeyError(f"SUSHI dataset {dataset_file} missing required 'Name' column.")

    def resolve(value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() or data_root is None else Path(data_root) / p

    parents = sorted({str(resolve(str(v)).parent) for v in df[raw_col]})
    if len(parents) != 1:
        raise ValueError(
            "run-diann needs all raw files in one directory; the SUSHI dataset "
            f"spans {len(parents)}: {parents}"
        )
    raw_dir = Path(parents[0])

    out = pd.DataFrame({COL_RELATIVE_PATH: df[raw_col], COL_NAME: df[COL_NAME]})
    # Carry the grouping forward: an explicit "Grouping Var" wins; otherwise map
    # the first B-Fabric "[Factor]" column (e.g. "Condition [Factor]") onto it.
    # If neither exists, grouping is left absent and prolfquapp QC supplies a
    # single dummy group.
    if COL_GROUPING in df.columns:
        out[COL_GROUPING] = df[COL_GROUPING]
    else:
        factor_col = first_factor_column(df)
        if factor_col is not None:
            out[COL_GROUPING] = df[factor_col]
    return out, raw_dir
