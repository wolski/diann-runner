#!/usr/bin/env python3
"""Pin the prolfquapp container image in the deploy configs to a published version.

Discovers the newest semver tag of the prolfquapp image on Docker Hub (or takes
an explicit ``--version``) and rewrites ``prolfquapp_image`` — both the docker
tag and the apptainer SIF path — in ``defaults_server.yml`` and
``defaults_local.yml``. The configs stay pinned to a concrete version (so runs
are reproducible); this script just automates the bump instead of hand-editing.

Workflow: run this on the dev box, commit the config change, ``git pull`` on the
server. At run time ``docker run`` pulls the pinned image if it is not present
locally (see diann_runner.container_utils), so no separate pull step is needed.

Usage:
    python3 scripts/bump_prolfquapp_version.py             # pin to newest published
    python3 scripts/bump_prolfquapp_version.py --version 2.3.5
    python3 scripts/bump_prolfquapp_version.py --dry-run
"""

import json
import re
import urllib.request
from pathlib import Path

import cyclopts
from loguru import logger

app = cyclopts.App(name="bump-prolfquapp", help=__doc__)

DEFAULT_REPO = "prolfqua/prolfquapp"
CONFIG_FILES = ("defaults_server.yml", "defaults_local.yml")
_SEMVER = re.compile(r"\d+\.\d+\.\d+")


def _fetch_tags(repo: str) -> list[str]:
    """Return all tag names for a Docker Hub repository (following pagination)."""
    url = f"https://hub.docker.com/v2/repositories/{repo}/tags?page_size=100"
    tags: list[str] = []
    while url:
        req = urllib.request.Request(url, headers={"User-Agent": "diann-runner-bump"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        tags.extend(t["name"] for t in data.get("results", []))
        url = data.get("next")
    return tags


def latest_semver_tag(repo: str) -> str:
    """Newest X.Y.Z tag published for ``repo`` (non-semver tags like 'latest' ignored)."""
    versions = [t for t in _fetch_tags(repo) if _SEMVER.fullmatch(t)]
    if not versions:
        raise RuntimeError(f"no X.Y.Z tags found for {repo} on Docker Hub")
    versions.sort(key=lambda s: tuple(int(x) for x in s.split(".")))
    return versions[-1]


def bump_text(text: str, repo: str, version: str) -> str:
    """Rewrite the docker tag and apptainer SIF filename to ``version``."""
    name = repo.rsplit("/", 1)[-1]
    text = re.sub(rf'({re.escape(repo)}:)[^"\s]+', rf"\g<1>{version}", text)
    # SIFs are named <app>-<version>.sif per the FGCZ apptainer standard; the
    # hyphen matters — matching the old underscore form silently left the SIF
    # path pinned to the previous version.
    text = re.sub(rf'({re.escape(name)}-)\d[^"/\s]*(\.sif)', rf"\g<1>{version}\g<2>", text)
    return text


@app.default
def bump(
    version: str | None = None,
    repo: str = DEFAULT_REPO,
    config_dir: Path | None = None,
    dry_run: bool = False,
) -> None:
    """Pin ``prolfquapp_image`` in the deploy configs to ``version`` (default: newest published).

    Args:
        version: exact X.Y.Z to pin; if omitted, the newest published tag is used.
        repo: Docker Hub repository providing the prolfquapp image.
        config_dir: directory holding the ``defaults_*.yml`` (default: the package config).
        dry_run: report the intended changes without writing.
    """
    if config_dir is None:
        config_dir = Path(__file__).resolve().parent.parent / "src" / "diann_runner" / "config"

    version = version or latest_semver_tag(repo)
    if not _SEMVER.fullmatch(version):
        raise ValueError(f"--version must be X.Y.Z, got {version!r}")
    logger.info(f"pinning {repo} -> {version}")

    changed = False
    for name in CONFIG_FILES:
        path = config_dir / name
        if not path.exists():
            raise FileNotFoundError(f"config not found: {path}")
        old = path.read_text()
        new = bump_text(old, repo, version)
        if new == old:
            logger.info(f"{name}: already at {version}")
            continue
        changed = True
        if dry_run:
            logger.info(f"{name}: would pin to {version}")
        else:
            path.write_text(new)
            logger.info(f"{name}: pinned to {version}")

    if changed and not dry_run:
        logger.info("done — review with `git diff` and commit")
    elif not changed:
        logger.info(f"no changes — configs already pinned to {version}")


if __name__ == "__main__":
    app()
