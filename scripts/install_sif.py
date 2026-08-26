#!/usr/bin/env python3
"""Install staged SIFs to the shared FGCZ container export.

``deploy.smk all_sif`` builds into ``deploy.sif_staging_dir`` (node-local
scratch) with the installed filenames already applied. It deliberately does not
write the shared location: ``/misc/container/exp`` is a privileged NFS export
that compute nodes mount read-only, so the SIF has to be copied to the NFS
host's export path instead (slurmworker ``docs/apptainer-build.md``).

This script is that copy, kept separate and explicit because it writes to
shared production storage. For each SIF it validates the image, refuses to
overwrite an installed one (the version in the filename is the reproducibility
anchor — bump it, never replace it), then scp's it into the per-app directory.

Run it from a host that reaches the NFS host directly, with write access to the
export (``ls -ld`` the target dir to see who that is).

Usage:
    python3 scripts/install_sif.py --dry-run        # show what would be copied
    python3 scripts/install_sif.py                  # install every staged SIF
    python3 scripts/install_sif.py diann-2.6.1.sif  # just one
"""

import os
import shutil
import subprocess
from pathlib import Path

import cyclopts
import yaml
from loguru import logger

app = cyclopts.App(name="install-sif", help=__doc__)

CONFIG = Path(__file__).resolve().parent.parent / "src" / "diann_runner" / "config" / "defaults_server.yml"


def _deploy_settings() -> dict:
    """The ``deploy:`` block, which carries the staging dir and install target."""
    return yaml.safe_load(CONFIG.read_text())["deploy"]


def app_name_for(sif: str) -> str:
    """Per-app directory for a SIF, from its ``<app>-<version>.sif`` filename.

    Splits on the *first* hyphen, not the last: pwiz's version is a capture date
    (``pwiz-2026-08-26.sif``), so splitting from the right yields ``pwiz-2026-08``.
    This assumes no app name contains a hyphen, which holds for all of diann,
    thermorawfileparser, pwiz and prolfquapp.
    """
    stem = Path(sif).stem
    if "-" not in stem:
        raise ValueError(
            f"{sif!r} is not named <app>-<version>.sif, so its target directory "
            f"cannot be derived"
        )
    return stem.split("-", 1)[0]


def validate(path: Path) -> None:
    """Fail unless the file is a SIF apptainer can read."""
    if not shutil.which("apptainer"):
        raise RuntimeError("apptainer not on PATH; cannot validate before installing")
    subprocess.run(["apptainer", "inspect", str(path)], check=True, capture_output=True)


def installed(host: str, remote: str) -> bool:
    """True when ``remote`` already exists on ``host``."""
    return subprocess.run(
        ["ssh", host, "test", "-e", remote], capture_output=True
    ).returncode == 0


@app.default
def install(
    sifs: list[str] | None = None,
    staging_dir: Path | None = None,
    dry_run: bool = False,
) -> None:
    """Copy staged SIFs to the shared export, skipping any already installed.

    Args:
        sifs: filenames to install; if omitted, every ``*.sif`` in the staging dir.
        staging_dir: override ``deploy.sif_staging_dir``.
        dry_run: report what would happen without copying.
    """
    deploy = _deploy_settings()
    host = deploy["sif_install_host"]
    root = deploy["sif_install_root"].rstrip("/")
    staging = staging_dir or Path(os.path.expandvars(deploy["sif_staging_dir"]))

    names = sifs or sorted(p.name for p in staging.glob("*.sif"))
    if not names:
        raise FileNotFoundError(f"no SIFs to install in {staging}")

    copied, skipped = [], []
    for name in names:
        local = staging / name
        if not local.exists():
            raise FileNotFoundError(f"staged SIF not found: {local}")
        remote = f"{root}/{app_name_for(name)}/{name}"

        if installed(host, remote):
            logger.info(f"{name}: already installed at {host}:{remote} — skipping")
            skipped.append(name)
            continue

        if dry_run:
            logger.info(f"{name}: would install to {host}:{remote}")
            copied.append(name)
            continue

        validate(local)
        logger.info(f"{name}: installing to {host}:{remote}")
        subprocess.run(["ssh", host, "mkdir", "-p", f"{root}/{app_name_for(name)}"], check=True)
        subprocess.run(["scp", str(local), f"{host}:{remote}"], check=True)
        copied.append(name)

    verb = "would install" if dry_run else "installed"
    logger.info(f"{verb} {len(copied)}, skipped {len(skipped)} already present")
    if copied and not dry_run:
        logger.info(
            "update images.apptainer in defaults_server.yml if any path changed, "
            "and keep the previous SIF until the new one is validated in a run"
        )


if __name__ == "__main__":
    app()
