#!/usr/bin/env python3
"""
prolfquapp_docker.py — Run prolfquapp/prolfqua tools inside Docker.

Usage:
  prolfquapp-docker [OPTIONS] <command> [args...]

Examples:
  prolfquapp-docker prolfqua_qc.sh --indir out-DIANN -s DIANN ...
  prolfquapp-docker --image-version 0.1.8 prolfqua_qc.sh ...

Note: Use relative paths or run from your data directory.
      Current directory is mounted to /work in the container.

Env vars (can also use CLI options):
  PROLFQUAPP_IMAGE_VERSION   Image version (default: "2.0.7")
  PROLFQUAPP_IMAGE_REPO      Image repository (default: "docker.io/prolfqua/prolfquapp")
  PROLFQUAPP_EXTRA           Extra docker run args
"""

import os
import shlex
import sys
from typing import Annotated

import cyclopts

from diann_runner.docker_utils import DockerCommandBuilder, run_container

# --- Settings from environment ---
DEFAULT_VERSION = os.environ.get("PROLFQUAPP_IMAGE_VERSION", "2.0.7")
DEFAULT_REPO = os.environ.get("PROLFQUAPP_IMAGE_REPO", "docker.io/prolfqua/prolfquapp")
EXTRA_ARGS = shlex.split(os.environ.get("PROLFQUAPP_EXTRA", ""))

app = cyclopts.App(
    name="prolfquapp-docker",
    help="Run prolfquapp/prolfqua tools inside Docker",
)


def build_docker_cmd(image_version: str, image_repo: str, argv: list[str]) -> list[str]:
    """Build the Docker command for prolfquapp."""
    image = f"{image_repo}:{image_version}"

    builder = (
        DockerCommandBuilder(image)
        .with_cleanup()
        .with_interactive()
        .with_uid_gid(flag="--user")
        .with_mount(os.getcwd(), "/work", style="bind")
        .with_workdir("/work")
    )

    if EXTRA_ARGS:
        builder.with_extra_args(EXTRA_ARGS)

    return builder.build(argv)


@app.default
def run(
    *container_args: Annotated[str, cyclopts.Parameter(show=False)],
    image_version: Annotated[str, cyclopts.Parameter(help="Docker image version")] = DEFAULT_VERSION,
    image_repo: Annotated[str, cyclopts.Parameter(help="Docker image repository")] = DEFAULT_REPO,
) -> None:
    """
    Run a command inside the prolfquapp Docker container.

    Example:
        prolfquapp-docker prolfqua_qc.sh --indir out-DIANN -s DIANN
    """
    docker_cmd = build_docker_cmd(image_version, image_repo, list(container_args))
    returncode = run_container(docker_cmd)
    sys.exit(returncode)


def main():
    app()


if __name__ == "__main__":
    main()
