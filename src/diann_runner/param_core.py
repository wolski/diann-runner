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
    """``'1_protein_names'`` -> ``1`` (leading number of the enum value)."""
    return int(str(value).split("_")[0])


def _parse_var_mods(value: Any) -> list[tuple[str, str, str]]:
    """Variable-modifications string -> list of ``(unimod_id, mass, residues)`` tuples."""
    return [tuple(m) for m in parse_var_mods_string(value)]


@dataclass(frozen=True)
class FieldSpec:
    """How one canonical field is built: its section, value transform, and default.

    ``section`` is the category sub-model the field lands in — one of
    ``"pipeline" | "inputs" | "lib" | "search" | "quant" | "output" | "advanced"`` —
    or ``"_internal"`` for the no-GUI bookkeeping fields (``library_predictor``,
    ``enable_step_c``) that stay top-level on ``DIANNRunnerParams``. ``default`` is
    the FINAL typed value used when the caller omits the field; ``_MISSING`` means
    the field is required and a missing value raises ``KeyError`` (fail-fast, per
    AGENTS.md).
    """

    section: str
    transform: Callable[[Any], Any]
    default: Any = _MISSING


# Canonical internal field name -> FieldSpec. The canonical name equals the new
# GUI key with its category prefix stripped (GUI ``lib_precursor_charge_min`` ->
# canonical ``precursor_charge_min``); ``FieldSpec.section`` carries the category so
# build_internal_params can route it into the right sub-model. `default` presence
# mirrors the historical parse_flat_params behavior exactly: required fields have
# none; optional fields carry the final typed default.
DIANN_FIELDS: dict[str, FieldSpec] = {
    # pipeline / run setup
    "diann_version":    FieldSpec("pipeline", str, default="2.3.2"),
    "workflow_mode":    FieldSpec("pipeline", str, default="two_step"),
    "is_dda":           FieldSpec("pipeline", _to_bool),
    "raw_converter":    FieldSpec("pipeline", str, default="thermoraw"),
    # library generation: digestion
    "digestion_cut":              FieldSpec("lib", str),
    "digestion_missed_cleavages": FieldSpec("lib", int),
    # library generation: peptide / precursor / fragment ranges
    "peptide_min_length":  FieldSpec("lib", int),
    "peptide_max_length":  FieldSpec("lib", int),
    "precursor_charge_min": FieldSpec("lib", int),
    "precursor_charge_max": FieldSpec("lib", int),
    "precursor_mz_min":     FieldSpec("lib", int),
    "precursor_mz_max":     FieldSpec("lib", int),
    "fragment_mz_min":      FieldSpec("lib", int),
    "fragment_mz_max":      FieldSpec("lib", int),
    # library generation: modifications
    "mods_variable":        FieldSpec("lib", _parse_var_mods, default=[]),
    "mods_unimod4":         FieldSpec("lib", _to_bool),
    "mods_met_excision":    FieldSpec("lib", _to_bool),
    "mods_no_peptidoforms": FieldSpec("lib", _to_bool),
    # search & scoring: mass accuracy (AUTO sentinel or int ppm) + per-run calibration
    "mass_acc_ms1":            FieldSpec("search", _int_or_auto),
    "mass_acc_ms2":            FieldSpec("search", _int_or_auto),
    # GUI "Unrelated runs" = --individual-mass-acc --individual-windows
    "mass_acc_unrelated_runs": FieldSpec("search", _to_bool, default=False),
    # search & scoring: FDR + protein inference
    "scoring_qvalue":       FieldSpec("search", float),
    "protein_pg_level":     FieldSpec("search", _pg_level),
    "protein_ids_to_names": FieldSpec("search", _to_bool, default=False),
    # quantification
    "scan_window": FieldSpec("quant", _int_or_auto, default="AUTO"),
    "reanalyse":   FieldSpec("quant", _to_bool),
    "no_norm":     FieldSpec("quant", _to_bool),
    # output artifacts
    "fragment_quant": FieldSpec("output", _to_bool, default=False),
    "include_libs":   FieldSpec("output", _to_bool, default=False),
    "pmultiqc":       FieldSpec("output", _to_bool, default=True),
    # advanced / diagnostic (freestyle = arbitrary DIA-NN flags, quant steps B/C only)
    "freestyle": FieldSpec("advanced", _freestyle, default=[]),
    "verbose":   FieldSpec("advanced", int),
    # internal-only bookkeeping (no GUI key)
    "library_predictor": FieldSpec("_internal", str, default="diann"),
    "enable_step_c":     FieldSpec("_internal", _to_bool, default=False),
}


def build_internal_params(canonical: dict[str, Any], *, fasta: dict[str, Any]) -> dict[str, Any]:
    """Assemble the seven-category nested ``DIANNRunnerParams`` shape from canonical input.

    ``canonical`` maps canonical internal field names (e.g. ``digestion_cut``,
    ``mass_acc_ms2``) -> raw (string) values; the caller adapter has already
    translated its own GUI keys onto these names. Each field is transformed per
    :data:`DIANN_FIELDS` and routed to its category sub-dict; an omitted field
    falls back to its default, or raises ``KeyError`` when it has none. ``fasta`` is
    the caller-resolved ``{fasta_databases, fasta_use_custom}`` sub-dict (FASTA
    selection is caller-specific, so it is not part of the field table) and lands
    under ``inputs``.
    """
    categories: dict[str, dict[str, Any]] = {
        "pipeline": {},
        "inputs": {},
        "lib": {},
        "search": {},
        "quant": {},
        "output": {},
        "advanced": {},
    }
    internal: dict[str, Any] = {}
    for name, spec in DIANN_FIELDS.items():
        if name in canonical:
            value = spec.transform(canonical[name])
        elif spec.default is not _MISSING:
            # Copy mutable (list) defaults so callers never share one object.
            value = list(spec.default) if isinstance(spec.default, list) else spec.default
        else:
            raise KeyError(f"missing required DIA-NN parameter: {name!r}")
        if spec.section == "_internal":
            internal[name] = value
        else:
            categories[spec.section][name] = value

    # FASTA is caller-resolved (B-Fabric single pick + optional additional, SUSHI
    # multi-select); each frontend hands us a list (length >= 1 in practice).
    categories["inputs"]["fasta_databases"] = list(fasta["fasta_databases"])
    categories["inputs"]["fasta_use_custom"] = fasta["fasta_use_custom"]

    return {
        **categories,
        # internal-only top-level fields (no GUI key)
        "diann_bin": DIANN_BIN,
        "library_predictor": internal["library_predictor"],
        "enable_step_c": internal["enable_step_c"],
    }
