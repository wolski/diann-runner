#!/usr/bin/env python3
"""End-to-end integration-test driver for the DIA-NN 3-step Snakemake workflow.

Stages production-shaped bfabric inputs into a clean work directory and runs
``diann-snakemake``. Reusing the real ``params.yml`` + ``dataset`` from a bfabric
run exercises every parameter parser, every flat-key mapping, and every workflow
stage with production-shaped inputs rather than synthetic ones.

The expected work-directory layout (see Snakefile.DIANN3step.smk)::

    <work_dir>/
    ├── params.yml                   # bfabric flat-key params + registration block
    ├── input/
    │   ├── <fasta>.fasta            # resolve_fasta_path() forces references to input/<name>
    │   └── raw/
    │       ├── dataset.parquet      # rule dataset_csv converts this -> dataset.csv
    │       ├── sample1.raw          # or .d.zip / .mzML
    │       └── ...

Input options (see tests/integration/README.md for the WU346549 / ProteoBench recipe):

* params:  ``--params-yml``
* dataset: ``--dataset-parquet`` OR ``--dataset-csv`` (csv is converted to parquet)
* FASTA:   ``--fasta`` (one or more files -> input/<name>) OR ``--fasta-zip``
           (a zip that already contains an ``input/...fasta`` layout)
* raw:     ``--raw-url`` (single archive) | ``--raw-dir`` (local file/archive/dir)
           | ``--raw-manifest`` (newline-separated URLs; resumable, skip-if-present)

Usage::

    python tests/integration/setup_integration_test.py \
        --work-dir /tmp/diann_integration \
        --params-yml params.yml \
        --dataset-csv dataset.csv \
        --fasta-zip fastas.zip \
        --raw-manifest proteobench_PXD028735_dia_aif.txt \
        --cores 32 --run

Dry-run is the default; pass ``--run`` to execute and verify acceptance criteria.

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
from urllib.request import Request, urlopen, urlretrieve

import pandas as pd
import yaml
from loguru import logger

# diann_runner imports are deferred into helpers so the script can still print
# --help on a machine without the package installed.

_ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2")


# ---------------------------------------------------------------------------
# Archive / download helpers
# ---------------------------------------------------------------------------

def _is_archive(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in _ARCHIVE_SUFFIXES)


def _extract_archive(archive: Path, dest: Path) -> None:
    """Extract a .zip / .tar / .tar.gz / .tgz / .tar.bz2 archive into ``dest``."""
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
            f"(expected one of {_ARCHIVE_SUFFIXES})."
        )


def _remote_size(url: str) -> int | None:
    """Return Content-Length for ``url`` via a HEAD request, or None if unknown."""
    try:
        req = Request(url, method="HEAD")  # noqa: S310 - trusted, test-only URL
        with urlopen(req, timeout=30) as resp:  # noqa: S310
            length = resp.headers.get("Content-Length")
            return int(length) if length is not None else None
    except Exception:  # noqa: BLE001 - HEAD is best-effort
        return None


def download_resumable(url: str, dest: Path) -> None:
    """Download ``url`` to ``dest``, resuming and skipping already-complete files.

    Raw spectrometry files are ~1.5 GB each, so a plain one-shot download is a
    poor fit. Prefer ``curl -C -`` (resume); skip entirely when the local file
    already matches the remote Content-Length.
    """
    remote = _remote_size(url)
    if dest.exists() and remote is not None and dest.stat().st_size == remote:
        logger.info(f"skip (already complete): {dest.name}")
        return

    if shutil.which("curl"):
        logger.info(f"Downloading (curl, resumable): {dest.name}")
        subprocess.run(["curl", "-fL", "-C", "-", "-o", str(dest), url], check=True)
    else:
        logger.info(f"Downloading (urlretrieve): {dest.name}")
        urlretrieve(url, dest)  # noqa: S310 - trusted, test-only URL


def _parse_manifest(manifest: Path) -> list[str]:
    """Return the list of URLs in a manifest (one per line; ``#`` comments, blanks ignored)."""
    urls: list[str] = []
    for line in manifest.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


# ---------------------------------------------------------------------------
# Staging
# ---------------------------------------------------------------------------

def stage_raw_files(
    raw_dir: Path,
    *,
    raw_url: str | None = None,
    raw_dir_src: Path | None = None,
    raw_manifest: Path | None = None,
) -> None:
    """Populate ``<work_dir>/input/raw/`` from a manifest, URL archive, or local source."""
    raw_dir.mkdir(parents=True, exist_ok=True)

    if raw_manifest:
        urls = _parse_manifest(raw_manifest)
        logger.info(f"Fetching {len(urls)} raw file(s) from manifest {raw_manifest.name}")
        for url in urls:
            # Keep exact filenames (ProteoBench: "do not rename the files").
            fname = Path(url.split("?", 1)[0]).name.replace("%5F", "_").replace("%5f", "_")
            download_resumable(url, raw_dir / fname)
        return

    if raw_url:
        archive = raw_dir / Path(raw_url).name
        download_resumable(raw_url, archive)
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
    elif _is_archive(src):
        logger.info(f"Extracting local archive {src} -> {raw_dir}")
        _extract_archive(src, raw_dir)
    else:
        logger.info(f"Copying single raw file {src} -> {raw_dir}")
        shutil.copy2(src, raw_dir / src.name)


def stage_params(work_dir: Path, params_yml: Path) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Staging params.yml -> {work_dir / 'params.yml'}")
    shutil.copy2(params_yml, work_dir / "params.yml")


def stage_dataset(raw_dir: Path, *, dataset_parquet: Path | None, dataset_csv: Path | None) -> None:
    """Place ``input/raw/dataset.parquet`` (the upstream input of rule dataset_csv)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / "dataset.parquet"
    if dataset_parquet:
        logger.info(f"Staging dataset.parquet -> {target}")
        shutil.copy2(dataset_parquet, target)
    else:
        assert dataset_csv is not None
        logger.info(f"Converting {dataset_csv.name} -> {target}")
        pd.read_csv(dataset_csv).to_parquet(target, index=False)


def stage_fastas(work_dir: Path, *, fastas: list[Path] | None, fasta_zip: Path | None) -> None:
    """Stage FASTA(s).

    ``resolve_fasta_path()`` forces every FASTA reference to ``input/<name>``, so
    individual ``--fasta`` files are copied there. A ``--fasta-zip`` is expected
    to already carry the ``input/...fasta`` layout and is extracted at the
    work-dir root.
    """
    input_dir = work_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    if fasta_zip:
        logger.info(f"Extracting FASTA zip {fasta_zip.name} -> {work_dir}")
        _extract_archive(fasta_zip, work_dir)
        return

    assert fastas is not None
    for fasta in fastas:
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
    missing: list[Path] = []
    workunit_id, enable_step_c = _read_workflow_context(work_dir)
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
    p.add_argument("--params-yml", required=True, type=Path,
                   help="bfabric flat-key params.yml (with registration block).")

    ds = p.add_mutually_exclusive_group(required=True)
    ds.add_argument("--dataset-parquet", type=Path,
                    help="dataset.parquet (the upstream input of rule dataset_csv).")
    ds.add_argument("--dataset-csv", type=Path,
                    help="dataset.csv (converted to dataset.parquet during staging).")

    fa = p.add_mutually_exclusive_group(required=True)
    fa.add_argument("--fasta", type=Path, nargs="+",
                    help="One or more FASTA files (copied to input/<name>).")
    fa.add_argument("--fasta-zip", type=Path,
                    help="Zip already containing an input/...fasta layout.")

    raw = p.add_mutually_exclusive_group(required=True)
    raw.add_argument("--raw-url", help="URL of a single raw archive (.zip/.tar/...).")
    raw.add_argument("--raw-dir", type=Path,
                     help="Local raw file, archive, or directory of raw files.")
    raw.add_argument("--raw-manifest", type=Path,
                     help="File of raw-file URLs (one per line; resumable download).")

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

    # Validate provided inputs exist before doing any work.
    must_exist: list[tuple[str, Path | None]] = [
        ("--params-yml", args.params_yml),
        ("--dataset-parquet", args.dataset_parquet),
        ("--dataset-csv", args.dataset_csv),
        ("--fasta-zip", args.fasta_zip),
        ("--raw-dir", args.raw_dir),
        ("--raw-manifest", args.raw_manifest),
    ]
    for fasta in args.fasta or []:
        must_exist.append(("--fasta", fasta))
    for label, path in must_exist:
        if path is not None and not path.exists():
            logger.error(f"{label} not found: {path}")
            return 2

    work_dir: Path = args.work_dir
    if args.clean and work_dir.exists():
        logger.warning(f"Removing existing work dir: {work_dir}")
        shutil.rmtree(work_dir)
    raw_dir = work_dir / "input" / "raw"

    # Stage everything.
    stage_params(work_dir, args.params_yml)
    stage_dataset(raw_dir, dataset_parquet=args.dataset_parquet, dataset_csv=args.dataset_csv)
    stage_fastas(work_dir, fastas=args.fasta, fasta_zip=args.fasta_zip)
    stage_raw_files(
        raw_dir,
        raw_url=args.raw_url,
        raw_dir_src=args.raw_dir,
        raw_manifest=args.raw_manifest,
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
