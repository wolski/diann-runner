"""SUSHI DIA-NN parameter assembly.

The DIA-NN parameter keys (``06a_diann_mods_variable`` etc.) are **B-Fabric**
parameters — defined by the B-Fabric XML executable, the single source of truth.
:func:`diann_runner.snakemake_helpers.parse_flat_params` already encodes exactly
which of those keys the workflow consumes, so there is **no separate allow-list
here**: callers hand over their raw parameter values and parse_flat_params selects
the B-Fabric keys it knows, ignoring SUSHI-framework params (cores, ram, mail, …).

This module owns the DIA-NN parameter *templates* (known-good presets) and the
merge of ``template defaults + caller overrides`` (or a full custom replacement),
so the SUSHI app carries no DIA-NN parameter knowledge.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import Any

import yaml

# Sentinel values meaning "caller did not supply a value" (case-folded).
_EMPTY_SENTINELS = frozenset({"", "NONE", "NULL"})


def _is_unset(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().upper() in _EMPTY_SENTINELS


def load_template(template: str) -> dict[str, Any]:
    """Return the ``params:`` block of bundled ``DIANN_params_<template>.yml``.

    Templates ship with diann_runner (``diann_runner/templates/``). Raises a
    clear error listing the available templates when the name is unknown.
    """
    template_file = importlib.resources.files("diann_runner.templates").joinpath(
        f"DIANN_params_{template}.yml"
    )
    if not template_file.is_file():
        available = sorted(
            p.name
            for p in importlib.resources.files("diann_runner.templates").iterdir()
            if p.name.startswith("DIANN_params_")
        )
        raise FileNotFoundError(
            f"Unknown params template {template!r}. Bundled: {', '.join(available)}"
        )
    loaded = yaml.safe_load(template_file.read_text())
    if not isinstance(loaded, dict) or "params" not in loaded:
        raise ValueError(f"Template {template_file} is missing a top-level `params:` block.")
    return loaded["params"]


def assemble_params(
    *,
    template: str = "default-DIA",
    overrides: dict[str, Any] | None = None,
    custom_params: str | Path | None = None,
) -> dict[str, Any]:
    """Assemble the flat DIA-NN params block for the SUSHI path.

    Priority (low → high):
      1. defaults from ``template`` (default-DIA / default-DDA)
      2. ``overrides`` merged on top, **unfiltered** — parse_flat_params later
         selects the B-Fabric keys it knows and ignores the rest (so no
         allow-list is needed); unset/sentinel values are dropped. Values are
         coerced to ``str`` to match the template's all-string shape.
      3. ``custom_params`` — a YAML file with a full ``params:`` block that
         *replaces* 1+2 entirely (the SUSHI "customParamsYml" escape hatch).

    Returns the merged flat mapping to feed to ``parse_flat_params``.
    """
    if not _is_unset(custom_params):
        path = Path(str(custom_params).strip())
        if not path.is_file():
            raise FileNotFoundError(f"custom_params file does not exist: {path}")
        loaded = yaml.safe_load(path.read_text())
        if not isinstance(loaded, dict) or "params" not in loaded:
            raise ValueError(f"custom_params {path} has no top-level `params:` block.")
        return loaded["params"]

    base = dict(load_template(template))
    merged = {
        k: str(v)
        for k, v in (overrides or {}).items()
        if not _is_unset(v)
    }
    return {**base, **merged}
