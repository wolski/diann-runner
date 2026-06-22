"""Normalized DIA-NN run request and parameters.

This is the caller-agnostic contract between the ``run-diann`` CLI adapters
(AppRunner / SUSHI) and the generic runner. Caller-specific parsers turn their
native files (``params.yml`` / ``sushi_params.tsv``, ``dataset.parquet`` /
``input_dataset.tsv``) into a :class:`DiannRunRequest`; the generic runner then
validates it, materializes a normalized work directory, and invokes the bundled
Snakefile.

``DIANNRunnerParams`` is a Pydantic v2 model whose typed sub-models
(``DiannParams``, ``FastaParams``) validate the nested structure produced by
:func:`diann_runner.snakemake_helpers.parse_flat_params`. :meth:`to_parsed`
reproduces that exact dict so the ``parse_flat_params`` → ``create_diann_workflow``
→ Snakefile contract is preserved; params are serialized to
``diann_runner_params.toml`` and read back by the Snakefile (dual-mode: TOML when
present, else legacy ``params.yml`` parsing).

Serialization notes:
- ``var_mods`` are ``(unimod_id, mass_delta, residues)`` tuples; ``model_dump(mode="json")``
  emits them as arrays for TOML and ``model_validate`` coerces them back to tuples.
- ``mass_acc`` / ``mass_acc_ms1`` / ``scan_window`` are ``int | Literal["AUTO"]``;
  each concrete value keeps its type natively through TOML.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Union

import pandas as pd
import tomli_w
from pydantic import BaseModel, ConfigDict

# Normalized dataset column names (decision 3: keep today's dataset.csv schema
# that prolfqua already consumes). Adapters map their native columns onto these.
COL_RELATIVE_PATH = "Relative Path"
COL_NAME = "Name"
COL_GROUPING = "Grouping Var"

# B-Fabric / SUSHI tag marking an experimental-design (grouping) column, e.g.
# "Condition [Factor]". Datasets carry the grouping under such a tagged column
# rather than literally "Grouping Var".
FACTOR_TAG = "[Factor]"


def first_factor_column(df: pd.DataFrame) -> str | None:
    """Return the first column whose name carries the B-Fabric ``[Factor]`` tag.

    SUSHI/B-Fabric datasets tag experimental-design columns like
    ``Condition [Factor]``. The first such column is used as the grouping
    variable (a UI-selectable choice may come later). Returns ``None`` when no
    factor column is present.
    """
    for col in df.columns:
        if FACTOR_TAG in str(col):
            return col
    return None


DatasetLike = Union[pd.DataFrame, Path]


VarMod = tuple[str, str, str]
IntOrAuto = int | Literal["AUTO"]  # mass_acc / mass_acc_ms1 / scan_window sentinel


class DiannParams(BaseModel):
    """Typed DIA-NN parameters — the ``diann`` sub-dict of parse_flat_params."""

    model_config = ConfigDict(extra="forbid")

    var_mods: list[VarMod] = []
    no_peptidoforms: bool
    unimod4: bool
    met_excision: bool
    min_pep_len: int
    max_pep_len: int
    min_pr_charge: int
    max_pr_charge: int
    min_pr_mz: int
    max_pr_mz: int
    min_fr_mz: int
    max_fr_mz: int
    cut: str
    missed_cleavages: int
    mass_acc: IntOrAuto
    mass_acc_ms1: IntOrAuto
    scan_window: IntOrAuto
    qvalue: float
    pg_level: int
    relaxed_prot_inf: bool
    ids_to_names: bool
    reanalyse: bool
    no_norm: bool
    export_quant: bool = False
    unrelated_runs: bool = False
    freestyle: list[str] = []
    verbose: int
    diann_bin: str
    is_dda: bool
    diann_version: str


class FastaParams(BaseModel):
    """Typed FASTA parameters — the ``fasta`` sub-dict of parse_flat_params."""

    model_config = ConfigDict(extra="forbid")

    database_path: str
    use_custom_fasta: bool


class DIANNRunnerParams(BaseModel):
    """Normalized DIA-NN parameters — the typed schema of parse_flat_params output.

    :meth:`to_parsed` reconstructs the exact nested dict the Snakefile and
    ``create_diann_workflow`` consume; :meth:`to_toml`/:meth:`from_toml` persist
    it to ``diann_runner_params.toml``. ``extra="forbid"`` makes any drift from
    the parse_flat_params contract a loud validation error.
    """

    model_config = ConfigDict(extra="forbid")

    diann: DiannParams
    fasta: FastaParams
    # Faithful mirror of parse_flat_params (a dup of diann.var_mods).
    var_mods: list[VarMod] = []
    library_predictor: str
    enable_step_c: bool
    workflow_mode: str
    raw_converter: str
    include_libs: bool

    # -- construction from / projection to the parse_flat_params() contract --

    @classmethod
    def from_parsed(cls, parsed: dict[str, Any]) -> "DIANNRunnerParams":
        """Validate and build from a ``parse_flat_params`` output dict."""
        return cls.model_validate(parsed)

    def to_parsed(self) -> dict[str, Any]:
        """Reconstruct the nested dict the Snakefile consumes (var_mods tuples preserved)."""
        return self.model_dump()

    # -- TOML round-trip ----------------------------------------------------

    def to_toml_dict(self) -> dict[str, Any]:
        """JSON-safe dict for TOML (tuples → lists)."""
        return self.model_dump(mode="json")

    @classmethod
    def from_toml_dict(cls, doc: dict[str, Any]) -> "DIANNRunnerParams":
        """Inverse of :meth:`to_toml_dict` (lists → tuples via validation)."""
        return cls.model_validate(doc)

    def to_toml(self, path: str | Path) -> None:
        """Write ``diann_runner_params.toml``."""
        with open(path, "wb") as fh:
            tomli_w.dump(self.to_toml_dict(), fh)

    @classmethod
    def from_toml(cls, path: str | Path) -> "DIANNRunnerParams":
        """Read ``diann_runner_params.toml``."""
        with open(path, "rb") as fh:
            return cls.from_toml_dict(tomllib.load(fh))


@dataclass
class DiannRunRequest:
    """Caller-agnostic DIA-NN run request.

    Carries native paths only. The runner derives the expected raw-file
    basenames from the normalized ``dataset`` and fails before Snakemake if any
    is absent from ``raw_file_dir`` (see :func:`validate_request`). It never
    stages or copies raw files (decision 5).
    """

    params: DIANNRunnerParams
    raw_file_dir: Path
    dataset: DatasetLike
    database_fasta: list[Path]
    work_dir: Path
    output_dir: Path
    cores: int
    workunit_id: str = "0"
    container_id: str = "0"
    # AppRunner writes outputs.yml and registers in B-Fabric; SUSHI does not
    # (the EzPyz wrapper delivers outputs itself). Decision 4.
    register_outputs: bool = True
    # Pin the container runtime ("docker"/"apptainer"); None auto-detects from
    # the host. Lets the caller force docker on a host with apptainer installed
    # but no SIF cache, without editing the deploy config.
    container_runtime: str | None = None

    def __post_init__(self) -> None:
        self.raw_file_dir = Path(self.raw_file_dir)
        self.work_dir = Path(self.work_dir)
        self.output_dir = Path(self.output_dir)
        self.database_fasta = [Path(f) for f in self.database_fasta]
        if not isinstance(self.dataset, pd.DataFrame):
            self.dataset = Path(self.dataset)


def load_dataset(dataset: DatasetLike) -> pd.DataFrame:
    """Return the normalized dataset as a DataFrame.

    Accepts an in-memory DataFrame or a path to ``.csv``/``.parquet``.
    """
    if isinstance(dataset, pd.DataFrame):
        return dataset
    path = Path(dataset)
    if not path.is_file():
        raise FileNotFoundError(f"Dataset file does not exist: {path}")
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix in (".csv", ".tsv"):
        return pd.read_csv(path, sep="\t" if path.suffix == ".tsv" else ",")
    raise ValueError(f"Unsupported dataset format {path.suffix!r}: {path}")


def dataset_raw_basenames(dataset: DatasetLike) -> list[str]:
    """Extract the raw-file basenames the run expects, from the dataset.

    Reads the normalized ``Relative Path`` column and returns ``Path(v).name``
    for each row (so callers may pass relative or absolute paths).
    """
    df = load_dataset(dataset)
    if COL_RELATIVE_PATH not in df.columns:
        raise KeyError(
            f"Normalized dataset is missing required column {COL_RELATIVE_PATH!r}. "
            f"Found: {list(df.columns)}"
        )
    return [Path(str(v)).name for v in df[COL_RELATIVE_PATH]]


def validate_request(request: DiannRunRequest) -> None:
    """Hard-fail before Snakemake if inputs are missing (decision 5).

    Checks, accumulating every problem before raising:
    - every raw basename listed in the dataset exists in ``raw_file_dir``
    - every FASTA in ``database_fasta`` exists on disk
    - ``raw_file_dir`` exists and is a directory

    The runner does no staging — inputs must already be on disk.
    """
    problems: list[str] = []

    if not request.raw_file_dir.is_dir():
        problems.append(f"raw_file_dir is not a directory: {request.raw_file_dir}")

    if not request.database_fasta:
        problems.append("no FASTA files provided (database_fasta is empty)")
    for fasta in request.database_fasta:
        if not fasta.is_file():
            problems.append(f"FASTA file does not exist: {fasta}")

    # Raw basenames are only checkable once raw_file_dir exists.
    if request.raw_file_dir.is_dir():
        basenames = dataset_raw_basenames(request.dataset)
        if not basenames:
            problems.append("dataset lists zero raw files")
        for name in basenames:
            if not (request.raw_file_dir / name).exists():
                problems.append(
                    f"raw file listed in dataset not found in raw_file_dir: "
                    f"{request.raw_file_dir / name}"
                )

    if problems:
        raise FileNotFoundError(
            "DiannRunRequest validation failed:\n  - " + "\n  - ".join(problems)
        )
