"""Caller-agnostic DIA-NN parameter core.

diann_runner is fed parameters by two sibling callers — B-Fabric/AppRunner (flat
``06a_*`` keys) and SUSHI (readable keys). Each caller owns its OWN key
vocabulary; neither should reference the other's. This module owns the shared,
caller-agnostic value transforms and defaults, keyed by diann_runner's *internal*
canonical field names (exactly the :class:`diann_runner.request.DiannParams` /
``DIANNRunnerParams`` field names).

Each caller adapter translates its own keys onto these canonical names —
``BFABRIC_TO_DRUNNER`` in :mod:`diann_runner.snakemake_helpers`,
``SUSHI_TO_DRUNNER`` in :mod:`diann_runner.sushi_adapter` — then calls
:func:`build_internal_params`. The transforms and defaults live here once, so the
two callers converge on identical internal params without sharing vocabulary.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Any, Callable

# The DIA-NN binary is not caller-derived — always the docker wrapper.
DIANN_BIN = "diann-docker"

# Sentinel: "the caller did not supply this canonical field".
_MISSING = object()


def parse_var_mods_string(var_mods_str):
    """Parse a variable-modifications string into (unimod_id, mass, residues) tuples.

    Example: ``'--var-mods 1 --var-mod UniMod:35,15.994915,M'`` -> ``[('35', '15.994915', 'M')]``.
    Empty / ``'None'`` input yields ``[]``.
    """
    if not var_mods_str or var_mods_str == "None":
        return []
    pattern = r"--var-mod UniMod:(\d+),([0-9.]+),([A-Z^]+)"
    return [(unimod_id, mass, residues) for unimod_id, mass, residues in re.findall(pattern, var_mods_str)]


def _to_bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def _freestyle(value: Any) -> list[str]:
    """Tokenise the freestyle passthrough string into DIA-NN CLI args.

    Empty / ``'None'`` input yields ``[]``. ``shlex.split`` so quoted arguments
    survive intact, e.g. ``'--mass-acc 10 --foo "a b"'`` -> ``['--mass-acc', '10',
    '--foo', 'a b']``. Always returns a fresh list (never the shared default).
    """
    s = str(value).strip()
    if not s or s == "None":
        return []
    return shlex.split(s)


def _int_or_auto(value: Any) -> int | str:
    """``'AUTO'`` sentinel passes through; anything else becomes an int (ppm/window)."""
    s = str(value).strip()
    return "AUTO" if s == "AUTO" else int(s)


def _pg_level(value: Any) -> int:
    """``'protein_names_1'`` -> ``1`` (trailing number of the enum value)."""
    return int(str(value).split("_")[-1])


@dataclass(frozen=True)
class FieldSpec:
    """How one canonical field is built: its section, value transform, and default.

    ``section`` is ``"diann"`` (lands in the nested ``diann`` sub-dict) or ``"top"``
    (a top-level workflow control). ``default`` is the FINAL typed value used when
    the caller omits the field; ``_MISSING`` means the field is required and a
    missing value raises ``KeyError`` (fail-fast, per AGENTS.md).
    """

    section: str
    transform: Callable[[Any], Any]
    default: Any = _MISSING


# Canonical internal field name -> FieldSpec. `default` presence mirrors the
# historical parse_flat_params behavior exactly: fields it read via flat[...] are
# REQUIRED here (no default); fields it read via flat.get(..., d) carry default d
# (as the final typed value). `var_mods` is handled explicitly in
# build_internal_params (mutable default + top-level mirror), not via this table.
DIANN_FIELDS: dict[str, FieldSpec] = {
    # modifications
    "no_peptidoforms":  FieldSpec("diann", _to_bool),
    "unimod4":          FieldSpec("diann", _to_bool),
    "met_excision":     FieldSpec("diann", _to_bool),
    # peptide constraints
    "min_pep_len":      FieldSpec("diann", int),
    "max_pep_len":      FieldSpec("diann", int),
    "min_pr_charge":    FieldSpec("diann", int),
    "max_pr_charge":    FieldSpec("diann", int),
    "min_pr_mz":        FieldSpec("diann", int),
    "max_pr_mz":        FieldSpec("diann", int),
    "min_fr_mz":        FieldSpec("diann", int),
    "max_fr_mz":        FieldSpec("diann", int),
    # digestion
    "cut":              FieldSpec("diann", str),
    "missed_cleavages": FieldSpec("diann", int),
    # mass accuracy (AUTO sentinel or int ppm)
    "mass_acc":         FieldSpec("diann", _int_or_auto),
    "mass_acc_ms1":     FieldSpec("diann", _int_or_auto),
    "scan_window":      FieldSpec("diann", _int_or_auto, default="AUTO"),
    # scoring + protein inference
    "qvalue":           FieldSpec("diann", float),
    "pg_level":         FieldSpec("diann", _pg_level),
    "ids_to_names":     FieldSpec("diann", _to_bool, default=False),
    # quantification
    "reanalyse":        FieldSpec("diann", _to_bool),
    "no_norm":          FieldSpec("diann", _to_bool),
    "export_quant":     FieldSpec("diann", _to_bool, default=False),
    # per-run calibration: GUI "Unrelated runs" = --individual-mass-acc --individual-windows
    "unrelated_runs":   FieldSpec("diann", _to_bool, default=False),
    # freestyle passthrough (arbitrary DIA-NN flags, applied to quant steps B/C only)
    "freestyle":        FieldSpec("diann", _freestyle, default=[]),
    # other
    "verbose":          FieldSpec("diann", int),
    "is_dda":           FieldSpec("diann", _to_bool),
    "diann_version":    FieldSpec("diann", str, default="2.3.2"),
    # top-level workflow controls
    "workflow_mode":     FieldSpec("top", str, default="two_step"),
    "raw_converter":     FieldSpec("top", str, default="thermoraw"),
    "library_predictor": FieldSpec("top", str, default="diann"),
    "enable_step_c":     FieldSpec("top", _to_bool, default=False),
    "include_libs":      FieldSpec("top", _to_bool, default=False),
}


def build_internal_params(canonical: dict[str, Any], *, fasta: dict[str, Any]) -> dict[str, Any]:
    """Assemble the nested ``parse_flat_params``-shaped param dict from canonical input.

    ``canonical`` maps canonical internal field names -> raw (string) values; the
    caller adapter has already translated its own keys onto these names. Each
    field is transformed per :data:`DIANN_FIELDS`; an omitted field falls back to
    its default, or raises ``KeyError`` when it has none. ``fasta`` is the
    caller-resolved ``{database_path, use_custom_fasta}`` sub-dict (FASTA selection
    is caller-specific, so it is not part of the field table).
    """
    diann: dict[str, Any] = {"diann_bin": DIANN_BIN}
    top: dict[str, Any] = {}
    for name, spec in DIANN_FIELDS.items():
        if name in canonical:
            value = spec.transform(canonical[name])
        elif spec.default is not _MISSING:
            value = spec.default
        else:
            raise KeyError(f"missing required DIA-NN parameter: {name!r}")
        (diann if spec.section == "diann" else top)[name] = value

    # var_mods: a list of tuples, mirrored at the top level (kept distinct so the
    # default is a fresh list, never a shared mutable).
    var_mods = [tuple(m) for m in parse_var_mods_string(canonical.get("var_mods", ""))]
    diann["var_mods"] = var_mods

    return {
        "diann": diann,
        "fasta": fasta,
        "var_mods": list(var_mods),
        "library_predictor": top["library_predictor"],
        "enable_step_c": top["enable_step_c"],
        "workflow_mode": top["workflow_mode"],
        "raw_converter": top["raw_converter"],
        "include_libs": top["include_libs"],
    }
