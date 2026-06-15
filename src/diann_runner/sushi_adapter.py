"""SUSHI input adapters for ``run-diann sushi``.

SUSHI's ``DIANNApp.rb`` emits **readable** param names (``mods_variable``,
``peptide_min_length``, ``fasta_databases``, ``order_fasta``, …) and an
``input_dataset.tsv`` with a ``Thermo RAW [File]`` column. Both differ from the
AppRunner side (B-Fabric XML keys ``06a_diann_*`` and ``dataset.parquet``), so
the SUSHI path needs its **own** adapters.

To stay consistent with AppRunner — same effective ``DIANNRunnerParams`` — these
adapters do *not* reimplement the parameter transformation. They:

1. alias the SUSHI readable keys onto the B-Fabric keys (:data:`SUSHI_TO_BFABRIC`),
2. merge them over a bundled template (which supplies the keys SUSHI doesn't
   carry, e.g. ``03_fasta_database_path``) via :func:`assemble_params`, and
3. run the shared :func:`parse_flat_params`.

FASTA is handled separately (SUSHI carries ``fasta_databases`` — a comma-joined
path list — not the B-Fabric ``03_*`` keys); the dataset adapter normalizes the
``Thermo RAW`` column and derives the single raw-file directory from it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from diann_runner.request import COL_GROUPING, COL_NAME, COL_RELATIVE_PATH
from diann_runner.snakemake_helpers import parse_flat_params
from diann_runner.sushi_params import assemble_params

# SUSHI readable param name -> B-Fabric flat key consumed by parse_flat_params.
# Only the keys parse_flat_params reads are listed; SUSHI-framework params
# (cores, mail, …) and the FASTA keys are handled elsewhere / ignored.
SUSHI_TO_BFABRIC: dict[str, str] = {
    "workflow_mode": "02_workflow_mode",
    "is_dda": "05_diann_is_dda",
    "scan_window": "05b_diann_scan_window",
    "mods_variable": "06a_diann_mods_variable",
    "mods_no_peptidoforms": "06b_diann_mods_no_peptidoforms",
    "mods_unimod4": "06c_diann_mods_unimod4",
    "mods_met_excision": "06d_diann_mods_met_excision",
    "peptide_min_length": "07_diann_peptide_min_length",
    "peptide_max_length": "07_diann_peptide_max_length",
    "peptide_precursor_charge_min": "07_diann_peptide_precursor_charge_min",
    "peptide_precursor_charge_max": "07_diann_peptide_precursor_charge_max",
    "peptide_precursor_mz_min": "07_diann_peptide_precursor_mz_min",
    "peptide_precursor_mz_max": "07_diann_peptide_precursor_mz_max",
    "peptide_fragment_mz_min": "07_diann_peptide_fragment_mz_min",
    "peptide_fragment_mz_max": "07_diann_peptide_fragment_mz_max",
    "digestion_cut": "08_diann_digestion_cut",
    "digestion_missed_cleavages": "08_diann_digestion_missed_cleavages",
    "mass_acc_ms1": "09_diann_mass_acc_ms1",
    "mass_acc_ms2": "09_diann_mass_acc_ms2",
    "scoring_qvalue": "10_diann_scoring_qvalue",
    "protein_pg_level": "11a_diann_protein_pg_level",
    "protein_relaxed_prot_inf": "11b_diann_protein_relaxed_prot_inf",
    "quantification_reanalyse": "12a_diann_quantification_reanalyse",
    "quantification_no_norm": "12b_diann_quantification_no_norm",
    "freestyle": "13_diann_freestyle",
    "raw_converter": "97_raw_converter",
    "verbose": "99_other_verbose",
}

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

    ``fasta_databases`` is a comma-joined list of paths (the DIANNApp multi-select).
    ``order_fasta`` is a checkbox today (no path) and is ignored until wired.
    """
    raw = flat.get("fasta_databases", "")
    if _is_unset(raw):
        return []
    return [Path(p.strip()) for p in str(raw).split(",") if not _is_unset(p)]


def parse_sushi_params(
    params_file: str | Path,
) -> tuple[dict[str, Any], list[Path], str | None]:
    """Parse a SUSHI ``sushi_params.yml`` into (workflow_params, fasta_paths, data_root).

    The readable keys are aliased to B-Fabric keys and merged over the template
    named by ``paramsTemplate`` (default ``default-DIA``); ``customParamsYml``,
    when set, fully replaces the template. The result runs through the shared
    :func:`parse_flat_params`, so the SUSHI path yields the same nested params
    AppRunner does. ``data_root`` is the ``dataRoot`` key SUSHI's run_PyApp adds
    (used by :func:`parse_sushi_dataset` to resolve relative raw paths); ``None``
    when absent.
    """
    flat = _load_flat(params_file)
    template = str(flat.get("paramsTemplate") or "default-DIA")
    aliased = {
        SUSHI_TO_BFABRIC[k]: v for k, v in flat.items() if k in SUSHI_TO_BFABRIC
    }
    merged = assemble_params(
        template=template, overrides=aliased, custom_params=flat.get("customParamsYml")
    )
    workflow_params = parse_flat_params(merged)
    data_root = flat.get("dataRoot")
    return workflow_params, fasta_paths_from_sushi(flat), data_root


def parse_sushi_dataset(
    dataset_file: str | Path, data_root: str | Path | None = None
) -> tuple[pd.DataFrame, Path]:
    """Parse a SUSHI ``input_dataset.tsv`` into (normalized_dataset, raw_dir).

    Maps the raw-file column (``Thermo RAW [File]`` / fallbacks) onto
    ``Relative Path`` and keeps ``Name`` (+ ``Grouping Var`` when present). The
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
    if COL_GROUPING in df.columns:
        out[COL_GROUPING] = df[COL_GROUPING]
    return out, raw_dir
