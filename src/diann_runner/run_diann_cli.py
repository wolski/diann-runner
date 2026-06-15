"""``run-diann`` — the user-facing DIA-NN runner with caller-specific adapters.

Two subcommands parse their native inputs into the same normalized
:class:`~diann_runner.request.DiannRunRequest`, then hand off to the generic
runner (:func:`diann_runner.prepare.run_request`):

    run-diann apprunner --raw-dir input/raw --dataset input/raw/dataset.parquet \\
        --params params.yml --fasta input/db.fasta --work-dir . --output-dir .

    run-diann sushi --raw-dir /scratch/staged_raw --dataset input_dataset.tsv \\
        --params sushi_params.yml --fasta /path/db.fasta --work-dir /scratch/work \\
        --output-dir /scratch/work --workunit-id 123 --container-id 456

The adapters only normalize inputs; they do not stage files (decision 5) or
register outputs beyond the AppRunner default. ``diann-snakemake`` remains the
low-level passthrough for developers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import cyclopts
import yaml
from loguru import logger

from diann_runner import prepare
from diann_runner.request import DIANNRunnerParams, DiannRunRequest
from diann_runner.snakemake_helpers import parse_flat_params
from diann_runner.sushi_adapter import parse_sushi_dataset, parse_sushi_params

app = cyclopts.App(
    name="run-diann",
    help="Run the DIA-NN workflow from AppRunner or SUSHI native inputs.",
)


def _load_flat_params(path: Path) -> tuple[dict, dict]:
    """Load a params file → (flat_params, registration).

    Accepts a doc with a top-level ``params:`` block (AppRunner ``params.yml``,
    SUSHI template) or a bare flat mapping. ``registration`` is empty when absent.
    """
    doc = yaml.safe_load(Path(path).read_text())
    if not isinstance(doc, dict):
        raise ValueError(f"Params file {path} did not parse as a mapping.")
    if "params" in doc:
        return doc["params"], doc.get("registration", {}) or {}
    return doc, {}


def _apply_fasta(workflow_params: dict, fastas: list[Path], work_dir: Path) -> list[Path]:
    """Reconcile the explicit --fasta list with ``workflow_params['fasta']``.

    When FASTA paths are given, they are authoritative: the first is the database
    FASTA, the rest mark custom sequences (use_custom_fasta). When none are given,
    derive the staged locations from the parsed params (input/<name> and, if
    use_custom_fasta, input/order.fasta) — the AppRunner default where app_runner
    has already staged them. Returns the database_fasta list for the request.
    """
    fasta_cfg = workflow_params["fasta"]
    if fastas:
        fasta_cfg["database_path"] = str(fastas[0])
        fasta_cfg["use_custom_fasta"] = len(fastas) > 1
        return list(fastas)

    db_name = Path(fasta_cfg["database_path"]).name
    derived = [work_dir / "input" / db_name]
    if fasta_cfg.get("use_custom_fasta"):
        derived.append(work_dir / "input" / "order.fasta")
    return derived


def _build_request(
    *,
    workflow_params: dict,
    dataset,
    raw_dir: Path,
    fastas: list[Path],
    work_dir: Path,
    output_dir: Path | None,
    cores: int,
    workunit_id: str,
    container_id: str,
    register_outputs: bool,
) -> DiannRunRequest:
    database_fasta = _apply_fasta(workflow_params, fastas, work_dir)
    return DiannRunRequest(
        params=DIANNRunnerParams.from_parsed(workflow_params),
        raw_file_dir=raw_dir,
        dataset=dataset,
        database_fasta=database_fasta,
        work_dir=work_dir,
        output_dir=output_dir if output_dir is not None else work_dir,
        cores=cores,
        workunit_id=str(workunit_id),
        container_id=str(container_id),
        register_outputs=register_outputs,
    )


@app.command
def apprunner(
    *,
    raw_dir: Annotated[Path, cyclopts.Parameter(name=["--raw-dir"])] = Path("input/raw"),
    dataset: Annotated[Path, cyclopts.Parameter(name=["--dataset"])] = Path("input/raw/dataset.parquet"),
    params: Annotated[Path, cyclopts.Parameter(name=["--params"])] = Path("params.yml"),
    fasta: Annotated[tuple[Path, ...], cyclopts.Parameter(name=["--fasta"])] = (),
    work_dir: Annotated[Path, cyclopts.Parameter(name=["--work-dir"])] = Path("."),
    output_dir: Annotated[Path | None, cyclopts.Parameter(name=["--output-dir"])] = None,
    cores: int = 64,
    dry_run: Annotated[bool, cyclopts.Parameter(name=["--dry-run", "-n"])] = False,
) -> int:
    """Run DIA-NN from AppRunner-staged inputs (params.yml + dataset.parquet)."""
    flat, registration = _load_flat_params(params)
    workflow_params = parse_flat_params(flat)
    request = _build_request(
        workflow_params=workflow_params,
        dataset=dataset,
        raw_dir=raw_dir,
        fastas=list(fasta),
        work_dir=work_dir,
        output_dir=output_dir,
        cores=cores,
        workunit_id=registration.get("workunit_id", "0"),
        container_id=registration.get("container_id", "0"),
        register_outputs=True,
    )
    logger.info(f"run-diann apprunner: WU{request.workunit_id}, {len(request.database_fasta)} FASTA")
    return prepare.run_request(request, dry_run=dry_run)


@app.command
def sushi(
    *,
    params: Annotated[Path, cyclopts.Parameter(name=["--params"])],
    dataset: Annotated[Path, cyclopts.Parameter(name=["--dataset"])],
    raw_dir: Annotated[Path | None, cyclopts.Parameter(name=["--raw-dir"])] = None,
    data_root: Annotated[Path | None, cyclopts.Parameter(name=["--data-root"])] = None,
    fasta: Annotated[tuple[Path, ...], cyclopts.Parameter(name=["--fasta"])] = (),
    work_dir: Annotated[Path, cyclopts.Parameter(name=["--work-dir"])] = Path("."),
    output_dir: Annotated[Path | None, cyclopts.Parameter(name=["--output-dir"])] = None,
    cores: int = 64,
    workunit_id: Annotated[str, cyclopts.Parameter(name=["--workunit-id"])] = "0",
    container_id: Annotated[str, cyclopts.Parameter(name=["--container-id"])] = "0",
    dry_run: Annotated[bool, cyclopts.Parameter(name=["--dry-run", "-n"])] = False,
) -> int:
    """Run DIA-NN from SUSHI/EzPyz inputs.

    Only ``--params`` (the SUSHI ``sushi_params.yml`` with readable keys) and
    ``--dataset`` (the SUSHI ``input_dataset.tsv``) are required — the SUSHI
    adapters in :mod:`diann_runner.sushi_adapter` derive everything else:

    - the FASTA list from the params' ``fasta_databases`` (``--fasta`` overrides),
    - ``dataRoot`` from the params, used to resolve the dataset's relative raw
      paths (``--data-root`` overrides),
    - the raw-file directory from those resolved paths (``--raw-dir`` overrides).

    Outputs are not registered in B-Fabric (the EzPyz wrapper delivers them).
    """
    workflow_params, fasta_paths, params_data_root = parse_sushi_params(params)
    effective_data_root = data_root if data_root is not None else params_data_root
    normalized, derived_raw_dir = parse_sushi_dataset(dataset, data_root=effective_data_root)
    request = _build_request(
        workflow_params=workflow_params,
        dataset=normalized,
        raw_dir=raw_dir if raw_dir is not None else derived_raw_dir,
        fastas=list(fasta) or fasta_paths,
        work_dir=work_dir,
        output_dir=output_dir,
        cores=cores,
        workunit_id=workunit_id,
        container_id=container_id,
        register_outputs=False,
    )
    logger.info(
        f"run-diann sushi: WU{request.workunit_id}, {len(normalized)} samples, "
        f"{len(request.database_fasta)} FASTA, raw_dir={request.raw_file_dir}"
    )
    return prepare.run_request(request, dry_run=dry_run)


if __name__ == "__main__":
    app()
