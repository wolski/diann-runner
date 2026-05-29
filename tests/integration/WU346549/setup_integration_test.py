#!/usr/bin/env python3
"""Zero-argument setup for the WU346549 DIA-NN integration test.

Run it with no arguments::

    ./setup_integration_test.py

The small inputs are committed in this directory at their real work-tree
positions (``params.yml``, ``inputs.yml``, ``input/order.fasta``,
``input/raw/dataset.parquet``) — see ``tree.txt``. This script only fetches the
large inputs that are *not* committed:

* FASTA  — ProteoBench triple-proteome HYE database (~16.7 MB),
           https://proteobench.cubimed.rub.de/fasta/  (saved under the FGCZ name
           the production params.yml references).
* raws   — 6 ProteoBench DIA Orbitrap AIF files (~9.2 GB total, ~1.5 GB each),
           PRIDE / ProteomeXchange accession PXD028735.

Downloads are resumable and skip any file already present at full size, so this
script is safe to re-run. Afterwards, launch the workflow with ``./run.sh``.

(The root ``dataset.csv`` is *not* committed — snakemake's ``dataset_csv`` rule
generates it from ``input/raw/dataset.parquet`` at run time.)
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

# --- ProteoBench triple-proteome HYE FASTA (downloaded, saved under FGCZ name) ---
FASTA_ZIP_URL = "https://proteobench.cubimed.rub.de/fasta/ProteoBenchFASTA%5FMixedSpecies%5FHYE.zip"
FASTA_MEMBER = "ProteoBenchFASTA_MixedSpecies_HYE.fasta"
# params.yml references /misc/fasta/<this name>; resolve_fasta_path() -> input/<name>.
FASTA_TARGET_NAME = "p34486_Proteobench_TripleProteome_20240614.fasta"

# --- ProteoBench DIA Orbitrap AIF raw files (PRIDE PXD028735) ---
# IMPORTANT: do NOT rename these files (ProteoBench requirement).
PRIDE_BASE = "https://ftp.pride.ebi.ac.uk/pride/data/archive/2022/02/PXD028735/"
RAW_FILES = [
    "LFQ_Orbitrap_AIF_Condition_A_Sample_Alpha_01.raw",
    "LFQ_Orbitrap_AIF_Condition_A_Sample_Alpha_02.raw",
    "LFQ_Orbitrap_AIF_Condition_A_Sample_Alpha_03.raw",
    "LFQ_Orbitrap_AIF_Condition_B_Sample_Alpha_01.raw",
    "LFQ_Orbitrap_AIF_Condition_B_Sample_Alpha_02.raw",
    "LFQ_Orbitrap_AIF_Condition_B_Sample_Alpha_03.raw",
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
    """Download the ProteoBench HYE FASTA and save it under the FGCZ name."""
    target = BASE / "input" / FASTA_TARGET_NAME
    if target.exists() and target.stat().st_size > 0:
        logger.info(f"skip (already present): input/{FASTA_TARGET_NAME}")
        return
    zip_path = BASE / "input" / "_ProteoBenchFASTA_MixedSpecies_HYE.zip"
    download(FASTA_ZIP_URL, zip_path)
    logger.info(f"extracting {FASTA_MEMBER} -> input/{FASTA_TARGET_NAME}")
    with zipfile.ZipFile(zip_path) as zf, open(target, "wb") as out:
        out.write(zf.read(FASTA_MEMBER))
    zip_path.unlink()


def download_raw_files() -> None:
    """Download the 6 ProteoBench DIA Orbitrap AIF raw files from PRIDE."""
    raw = BASE / "input" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    logger.info(f"downloading {len(RAW_FILES)} raw file(s) (~9.2 GB total) from PXD028735")
    for name in RAW_FILES:
        # PRIDE encodes underscores as %5F in the path.
        download(PRIDE_BASE + name.replace("_", "%5F"), raw / name)


def main() -> int:
    logger.info(f"setting up WU346549 integration test in {BASE}")
    download_database_fasta()
    download_raw_files()
    logger.success("setup complete — run the workflow with ./run.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
