#!/usr/bin/env python3
"""End-to-end integration-test driver for the DIA-NN 3-step Snakemake workflow.

Stages production-shaped bfabric inputs into a clean work directory and runs
``diann-snakemake``. Reusing the real ``params.yml`` + ``dataset.parquet`` from a
bfabric run exercises every parameter parser, every flat-key mapping, and every
workflow stage with production-shaped inputs rather than synthetic ones.

The expected work-directory layout (see Snakefile.DIANN3step.smk)::

    <work_dir>/
    ├── params.yml                   # bfabric flat-key params + registration block
    ├── input/
    │   ├── <fasta>.fasta            # resolved by resolve_fasta_path() -> input/<name>
    │   └── raw/
    │       ├── dataset.parquet      # rule dataset_csv converts this -> dataset.csv
    │       ├── sample1.raw          # or .d.zip / .mzML
    │       └── ...

Usage::

    # Dry-run (default): stage inputs, then `diann-snakemake -n`
    python tests/integration/setup_integration_test.py \
        --work-dir /tmp/diann_integration \
        --raw-url https://example.org/proteobench_raw.zip \
        --params-yml fixtures/params.yml \
        --dataset-parquet fixtures/dataset.parquet \
        --fasta fixtures/db.fasta

    # Actually execute the workflow and verify acceptance criteria
    python tests/integration/setup_integration_test.py ... --cores 32 --run

Raw inputs may be supplied either as a downloadable archive (``--raw-url``) or as
an already-fetched local file/directory (``--raw-dir``); exactly one is required.

See TODO/TODO_integration_test.md for the full plan and cross-runtime procedure.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

import yaml
from loguru import logger

# diann_runner imports are deferred into helpers so the script can still print
# --help on a machine without the package installed.


# ---------------------------------------------------------------------------
# Staging
# ---------------------------------------------------------------------------

def _extract_archive(archive: Path, dest: Path) -> None:
    """Extract a .zip / .tar / .tar.gz / .tgz archive into ``dest``."""
    name = archive.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
    elif name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2")):
        with tarfile.open(archive) as tf:
            tf.extractall(dest)
    else:
        raise ValueError(
            f"Don't know how to extract {archive.name!r} "
            "(expected .zip, .tar, .tar.gz, .tgz, or .tar.bz2)."
        )


def stage_raw_files(raw_dir: Path, *, raw_url: str | None, raw_dir_src: Path | None) -> None:
    """Populate ``<work_dir>/input/raw/`` from a URL archive or a local source.

    A local source may be a single archive, a single raw file, or a directory of
    raw files / .d.zip folders.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)

    if raw_url:
        archive = raw_dir / Path(raw_url).name
        logger.info(f"Downloading raw archive: {raw_url}")
        urlretrieve(raw_url, archive)  # noqa: S310 - trusted, test-only URL
        logger.info(f"Extracting {archive.name} -> {raw_dir}")
        _extract_archive(archive, raw_dir)
        return

    assert raw_dir_src is not None  # guaranteed by argument validation
    src = raw_dir_src
    if src.is_dir():
        logger.info(f"Copying raw files from directory {src} -> {raw_dir}")
        for item in sorted(src.iterdir()):
            target = raw_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
    elif src.suffix.lower() in {".zip", ".tar", ".tgz", ".gz", ".bz2"}:
        logger.info(f"Extracting local archive {src} -> {raw_dir}")
        _extract_archive(src, raw_dir)
    else:
        logger.info(f"Copying single raw file {src} -> {raw_dir}")
        shutil.copy2(src, raw_dir / src.name)


def stage_metadata(
    work_dir: Path,
    raw_dir: Path,
    *,
    params_yml: Path,
    dataset_parquet: Path,
    fasta: Path,
) -> None:
    """Drop params.yml, dataset.parquet and the FASTA into their expected paths."""
    input_dir = work_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Staging params.yml -> {work_dir / 'params.yml'}")
    shutil.copy2(params_yml, work_dir / "params.yml")

    logger.info(f"Staging dataset.parquet -> {raw_dir / 'dataset.parquet'}")
    shutil.copy2(dataset_parquet, raw_dir / "dataset.parquet")

    # resolve_fasta_path() forces FASTA references to input/<name>, so the file
    # must land directly under input/ (not a nested dir).
    logger.info(f"Staging FASTA -> {input_dir / fasta.name}")
    shutil.copy2(fasta, input_dir / fasta.name)


# ---------------------------------------------------------------------------
# Runtime sanity check
# ---------------------------------------------------------------------------

def check_runtime(expected: str | None) -> str:
    """Report the auto-detected container runtime and warn on a mismatch.

    Detection is automatic (apptainer wins over docker when both are present);
    ``--runtime`` is only an informational expectation for the caller.
    """
    from diann_runner.container_utils import detect_runtime

    detected = detect_runtime()
    if expected and expected != detected:
        logger.warning(
            f"Runtime mismatch: detect_runtime() == {detected!r}, "
            f"but you expected {expected!r}. The workflow uses {detected!r}."
        )
    else:
        logger.info(f"Detected container runtime: {detected}")
    return detected


# ---------------------------------------------------------------------------
# Acceptance criteria
# ---------------------------------------------------------------------------

def _read_workflow_context(work_dir: Path) -> tuple[str, bool]:
    """Return (workunit_id, enable_step_c) parsed from the staged params.yml."""
    from diann_runner.snakemake_helpers import parse_flat_params

    config = yaml.safe_load((work_dir / "params.yml").read_text())
    workunit_id = str(config["registration"]["workunit_id"])
    enable_step_c = parse_flat_params(config["params"])["enable_step_c"]
    return workunit_id, enable_step_c


def expected_outputs(work_dir: Path, workunit_id: str, enable_step_c: bool) -> list[Path]:
    """Acceptance-criteria output files (see TODO_integration_test.md)."""
    final = "out-DIANN_quantC" if enable_step_c else "out-DIANN_quantB"
    outputs = [
        work_dir / f"out-DIANN_libA/WU{workunit_id}_report-lib.predicted.speclib",
        work_dir / f"out-DIANN_quantB/WU{workunit_id}_report.parquet",
        work_dir / f"{final}/WU{workunit_id}_report.parquet",
        work_dir / f"{final}/WU{workunit_id}_report_prozor.parquet",
        work_dir / f"Result_WU{workunit_id}.zip",
        work_dir / "outputs.yml",
    ]
    # When enable_step_c is False the "final" dir is quantB, so the generic and
    # final report.parquet collapse to the same path — dedupe, preserving order.
    return list(dict.fromkeys(outputs))


def verify_outputs(work_dir: Path) -> list[Path]:
    """Return the list of missing / empty expected outputs (empty == pass)."""
    workunit_id, enable_step_c = _read_workflow_context(work_dir)
    missing: list[Path] = []
    for path in expected_outputs(work_dir, workunit_id, enable_step_c):
        if not path.exists() or path.stat().st_size == 0:
            missing.append(path)
    return missing


# ---------------------------------------------------------------------------
# Snakemake invocation
# ---------------------------------------------------------------------------

def run_snakemake(work_dir: Path, *, cores: int, target: str, run: bool) -> int:
    """Invoke ``diann-snakemake`` in ``work_dir`` (dry-run unless ``run``)."""
    cmd = ["diann-snakemake", "--cores", str(cores), target]
    if not run:
        cmd.append("-n")
    logger.info(f"Running ({'execute' if run else 'dry-run'}): {' '.join(cmd)} (cwd={work_dir})")
    return subprocess.run(cmd, cwd=work_dir).returncode


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--work-dir", required=True, type=Path,
                   help="Target work directory (created if missing).")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--raw-url", help="URL of raw archive (.zip/.tar/.tar.gz).")
    src.add_argument("--raw-dir", type=Path,
                     help="Local raw file, archive, or directory of raw files.")
    p.add_argument("--params-yml", required=True, type=Path,
                   help="bfabric flat-key params.yml (with registration block).")
    p.add_argument("--dataset-parquet", required=True, type=Path,
                   help="dataset.parquet (converted to dataset.csv by the workflow).")
    p.add_argument("--fasta", required=True, type=Path,
                   help="FASTA database referenced by params.yml.")
    p.add_argument("--runtime", choices=("docker", "apptainer"), default=None,
                   help="Expected runtime (informational; detection is automatic).")
    p.add_argument("--cores", type=int, default=8, help="Cores for snakemake.")
    p.add_argument("--target", default="all", help="Snakemake target rule.")
    p.add_argument("--run", action="store_true",
                   help="Actually execute the workflow (default: dry-run only).")
    p.add_argument("--clean", action="store_true",
                   help="Remove the work directory before staging.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Validate input files exist before doing any work.
    for label, path in (
        ("--params-yml", args.params_yml),
        ("--dataset-parquet", args.dataset_parquet),
        ("--fasta", args.fasta),
    ):
        if not path.exists():
            logger.error(f"{label} not found: {path}")
            return 2
    if args.raw_dir and not args.raw_dir.exists():
        logger.error(f"--raw-dir not found: {args.raw_dir}")
        return 2

    work_dir: Path = args.work_dir
    if args.clean and work_dir.exists():
        logger.warning(f"Removing existing work dir: {work_dir}")
        shutil.rmtree(work_dir)
    raw_dir = work_dir / "input" / "raw"

    # Stage everything.
    stage_raw_files(raw_dir, raw_url=args.raw_url, raw_dir_src=args.raw_dir)
    stage_metadata(
        work_dir, raw_dir,
        params_yml=args.params_yml,
        dataset_parquet=args.dataset_parquet,
        fasta=args.fasta,
    )

    # Report runtime (best-effort: don't abort staging if neither is installed).
    try:
        check_runtime(args.runtime)
    except Exception as exc:  # noqa: BLE001 - informational only
        logger.warning(f"Could not detect container runtime: {exc}")

    rc = run_snakemake(work_dir, cores=args.cores, target=args.target, run=args.run)
    if rc != 0:
        logger.error(f"snakemake exited with code {rc}")
        return rc

    if args.run:
        missing = verify_outputs(work_dir)
        if missing:
            logger.error("Acceptance check FAILED — missing/empty outputs:")
            for path in missing:
                logger.error(f"  - {path}")
            return 1
        logger.success("Acceptance check PASSED — all expected outputs present.")
    else:
        logger.info("Dry-run complete. Re-run with --run to execute and verify outputs.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
