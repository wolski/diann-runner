"""Materialize a normalized work directory from a DiannRunRequest and run it.

The generic runner: it validates the request, writes the normalized work-dir
contents the Snakefile reads (``diann_runner_params.toml``, ``dataset.csv``, and
copied FASTA under ``input/``), then invokes the bundled Snakefile with config
describing the raw-file source. It never stages/copies raw files (decision 5) —
raw files are read in place from ``raw_file_dir`` (bind-mounted read-only into
the containers when external; see :mod:`diann_runner.diann_docker`).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from loguru import logger

from diann_runner.request import (
    COL_NAME,
    COL_RELATIVE_PATH,
    DiannRunRequest,
    load_dataset,
    validate_request,
)
from diann_runner.snakemake_cli import get_snakefile_path

PARAMS_TOML = "diann_runner_params.toml"
DATASET_CSV = "dataset.csv"
# Conversion outputs and FASTA copies live under the work dir; this is where an
# external raw_file_dir's converted .mzML / extracted .d are written.
CONVERTED_SUBDIR = "input/raw"
RAW_MOUNT_TARGET = "/raw"


def prepare_work_dir(request: DiannRunRequest) -> None:
    """Write the normalized work-dir contents the Snakefile consumes.

    Materializes ``diann_runner_params.toml``, ``dataset.csv`` (today's schema),
    and copies the FASTA files into ``work_dir/input/``. Does not copy raw files.
    """
    work = request.work_dir
    input_dir = work / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    request.params.to_toml(work / PARAMS_TOML)
    _write_dataset(request, work / DATASET_CSV)
    _stage_fastas(request, input_dir)
    logger.info(f"Prepared work dir {work}")


def _write_dataset(request: DiannRunRequest, out_csv: Path) -> None:
    """Write the normalized dataset.csv (Relative Path / Name / factors)."""
    df = load_dataset(request.dataset)
    for required in (COL_RELATIVE_PATH, COL_NAME):
        if required not in df.columns:
            raise KeyError(
                f"Normalized dataset is missing required column {required!r}. "
                f"Found: {list(df.columns)}"
            )
    df.to_csv(out_csv, index=False)


def _copy_if_needed(src: Path, dst: Path) -> None:
    """Copy ``src`` → ``dst`` unless they are already the same file.

    AppRunner pre-stages FASTAs into ``input/`` (so src == dst); the SUSHI/CLI
    path passes external sources that must be copied in.
    """
    src, dst = Path(src), Path(dst)
    if src.resolve() == dst.resolve():
        return
    shutil.copy2(src, dst)


def _stage_fastas(request: DiannRunRequest, input_dir: Path) -> None:
    """Copy FASTA files into ``input/`` where the Snakefile resolves them.

    The database FASTA is copied to ``input/<database_path name>`` (matching
    ``resolve_fasta_path``); the optional custom FASTA, when use_custom_fasta is
    set, is copied to ``input/order.fasta`` (matching ``get_fasta_paths``).
    """
    fasta = request.params.fasta
    db_name = Path(fasta.database_path).name
    _copy_if_needed(request.database_fasta[0], input_dir / db_name)
    if fasta.use_custom_fasta and len(request.database_fasta) > 1:
        _copy_if_needed(request.database_fasta[1], input_dir / "order.fasta")


def build_snakemake_config(request: DiannRunRequest) -> dict[str, str]:
    """Build the Snakemake ``--config`` mapping describing the raw-file source.

    When ``raw_file_dir`` is inside ``work_dir`` (AppRunner-style), it is passed
    relative and no extra container mount is needed. When it is external, it is
    passed absolute with a ``/raw`` mount target and conversion outputs are
    redirected under the work dir.
    """
    raw_dir = request.raw_file_dir.resolve()
    work = request.work_dir.resolve()
    cfg: dict[str, str] = {
        "workunit_id": str(request.workunit_id),
        "container_id": str(request.container_id),
        "register_outputs": "True" if request.register_outputs else "False",
    }
    if raw_dir == work or raw_dir.is_relative_to(work):
        cfg["raw_file_dir"] = str(raw_dir.relative_to(work)) or "."
    else:
        cfg["raw_file_dir"] = str(raw_dir)
        cfg["raw_mount_target"] = RAW_MOUNT_TARGET
        cfg["converted_dir"] = CONVERTED_SUBDIR
    return cfg


def build_snakemake_command(
    request: DiannRunRequest,
    *,
    dry_run: bool = False,
    extra_args: list[str] | None = None,
) -> list[str]:
    """Build the ``snakemake`` argv for this request (no explicit target → ``all``)."""
    cmd = [
        "snakemake",
        "-s",
        get_snakefile_path(),
        "--directory",
        str(request.work_dir),
        "--cores",
        str(request.cores),
        "-p",
    ]
    if dry_run:
        cmd.append("-n")
    cmd += list(extra_args or [])
    cmd.append("--config")
    cmd += [f"{k}={v}" for k, v in build_snakemake_config(request).items()]
    return cmd


def deliver_outputs(request: DiannRunRequest) -> None:
    """Copy final deliverables to ``output_dir`` when it differs from ``work_dir``.

    Decision 4: DIA-NN writes everything under ``work_dir``; the Result zip and
    ``qc_result`` are copied to ``output_dir`` only when they are not already the
    same directory (AppRunner has output_dir == work_dir, so this is a no-op).
    """
    work = request.work_dir.resolve()
    out = request.output_dir.resolve()
    if out == work:
        return
    out.mkdir(parents=True, exist_ok=True)
    result_zip = work / f"Result_WU{request.workunit_id}.zip"
    if result_zip.is_file():
        shutil.copy2(result_zip, out / result_zip.name)
    qc_dir = work / "qc_result"
    if qc_dir.is_dir():
        dst = out / "qc_result"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(qc_dir, dst)
    logger.info(f"Delivered outputs to {out}")


def run_request(
    request: DiannRunRequest,
    *,
    dry_run: bool = False,
    extra_args: list[str] | None = None,
) -> int:
    """Validate, materialize the work dir, and invoke Snakemake. Returns exit code."""
    validate_request(request)
    prepare_work_dir(request)
    cmd = build_snakemake_command(request, dry_run=dry_run, extra_args=extra_args)
    logger.info("Running: " + " ".join(cmd))
    returncode = subprocess.run(cmd, check=False).returncode
    if returncode == 0 and not dry_run:
        deliver_outputs(request)
    return returncode
