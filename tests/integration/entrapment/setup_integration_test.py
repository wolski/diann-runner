#!/usr/bin/env python3
"""Zero-argument setup for the ProteoBench DIA-Astral *entrapment* integration test.

Run it with no arguments::

    ./setup_integration_test.py

Downloads the large inputs the no-digestion workflow needs (nothing here is
committed except the driver scripts and ``input_dataset.tsv``):

* FASTA  — ProteoBench entrapment database, **already digested** (each record is a
           peptide, e.g. ``>sp|PSLDQLAAHPWMLGADGGVPESCDLR_target|...``), so the
           search must run with digestion off (``lib_digestion_cut: no digestion``).
           https://proteobench.cubimed.rub.de/fasta/  (~48 MB zip, ~190 MB fasta).
* raws   — 6 ProteoBench DIA-Astral files (~3.6 GB each, ~21 GB total),
           https://proteobench.cubimed.rub.de/raws/DIA-astral/ .

Downloads are resumable and skip any file already present at full size, so this
script is safe to re-run. Afterwards, launch a run with ``./run.sh`` (or the
Makefile targets — ``make dry`` / ``make run`` / ``make sweep``).

The raw filenames must NOT be renamed (ProteoBench requirement); ``input_dataset.tsv``
references them verbatim.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen, urlretrieve

from loguru import logger

BASE = Path(__file__).resolve().parent

# --- ProteoBench entrapment FASTA (pre-digested peptide list + contaminants) ---
FASTA_ZIP_URL = (
    "https://proteobench.cubimed.rub.de/fasta/"
    "ProteoBenchFASTA_Entrapment_Human_with_contaminants_entrapment_pep.zip"
)
FASTA_MEMBER = "ProteoBenchFASTA_Entrapment_Human_with_contaminants_entrapment_pep.fasta"
# run.sh points --fasta at input/<this name>.
FASTA_TARGET_NAME = FASTA_MEMBER

# --- ProteoBench DIA-Astral raw files ---
# IMPORTANT: do NOT rename these files (ProteoBench requirement).
RAW_BASE = "https://proteobench.cubimed.rub.de/raws/DIA-astral/"
RAW_FILES = [
    "LFQ_Astral_DIA_15min_50ng_Condition_A_REP1.raw",
    "LFQ_Astral_DIA_15min_50ng_Condition_A_REP2.raw",
    "LFQ_Astral_DIA_15min_50ng_Condition_A_REP3.raw",
    "LFQ_Astral_DIA_15min_50ng_Condition_B_REP1.raw",
    "LFQ_Astral_DIA_15min_50ng_Condition_B_REP2.raw",
    "LFQ_Astral_DIA_15min_50ng_Condition_B_REP3.raw",
]


def _remote_size(url: str) -> int | None:
    """Content-Length for ``url`` via HEAD, or None if unknown."""
    try:
        with urlopen(Request(url, method="HEAD"), timeout=30) as resp:  # noqa: S310
            length = resp.headers.get("Content-Length")
            return int(length) if length is not None else None
    except Exception:  # noqa: BLE001 - HEAD is best-effort
        return None


def download(url: str, dest: Path) -> None:
    """Download ``url`` to ``dest``, resuming and skipping already-complete files."""
    remote = _remote_size(url)
    if dest.exists() and remote is not None and dest.stat().st_size == remote:
        logger.info(f"skip (already complete): {dest.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("curl"):
        logger.info(f"downloading (curl, resumable): {dest.name}")
        subprocess.run(["curl", "-fL", "-C", "-", "-o", str(dest), url], check=True)
    else:
        logger.info(f"downloading (urlretrieve): {dest.name}")
        urlretrieve(url, dest)  # noqa: S310


def download_database_fasta() -> None:
    """Download the ProteoBench entrapment FASTA and extract the peptide-list fasta."""
    target = BASE / "input" / FASTA_TARGET_NAME
    if target.exists() and target.stat().st_size > 0:
        logger.info(f"skip (already present): input/{FASTA_TARGET_NAME}")
        return
    zip_path = BASE / "input" / "_entrapment_pep.zip"
    download(FASTA_ZIP_URL, zip_path)
    logger.info(f"extracting {FASTA_MEMBER} -> input/{FASTA_TARGET_NAME}")
    with zipfile.ZipFile(zip_path) as zf, open(target, "wb") as out:
        out.write(zf.read(FASTA_MEMBER))
    zip_path.unlink()


def download_raw_files() -> None:
    """Download the 6 ProteoBench DIA-Astral raw files (~21 GB total)."""
    raw = BASE / "input" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    logger.info(f"downloading {len(RAW_FILES)} DIA-Astral raw file(s) (~21 GB total)")
    for name in RAW_FILES:
        download(RAW_BASE + name, raw / name)


def main() -> int:
    logger.info(f"setting up entrapment integration test in {BASE}")
    download_database_fasta()
    download_raw_files()
    logger.success("setup complete — run with ./run.sh (or make dry / make run / make sweep)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
