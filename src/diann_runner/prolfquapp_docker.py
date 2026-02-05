#!/usr/bin/env python3
"""
prolfquapp_docker.py — Run prolfquapp/prolfqua tools inside Docker.

Usage:
  prolfquapp-docker --image <image:tag> <command> [args...]

Examples:
  prolfquapp-docker --image prolfqua/prolfquapp:2.0.8 prolfqua_qc.sh --indir out-DIANN -s DIANN ...

Note: Use relative paths or run from your data directory.
      Current directory is mounted to /work in the container.
"""

import os
import sys
from typing import Annotated

import cyclopts

from diann_runner.docker_utils import DockerCommandBuilder, run_container

app = cyclopts.App(
    name="prolfquapp-docker",
    help="Run prolfquapp/prolfqua tools inside Docker",
)


def build_docker_cmd(image: str, argv: list[str]) -> list[str]:
    """Build the Docker command for prolfquapp."""
    builder = (
        DockerCommandBuilder(image)
        .with_cleanup()
        .with_init()
        .with_uid_gid(flag="--user")
        .with_mount(os.getcwd(), "/work", style="bind")
        .with_workdir("/work")
    )

    return builder.build(argv)


@app.default
def run(
    *container_args: Annotated[str, cyclopts.Parameter(show=False)],
    image: Annotated[str, cyclopts.Parameter(help="Docker image (required)")],
) -> None:
    """
    Run a command inside the prolfquapp Docker container.

    Example:
        prolfquapp-docker --image prolfqua/prolfquapp:2.0.8 prolfqua_qc.sh --indir out-DIANN -s DIANN
    """
    docker_cmd = build_docker_cmd(image, list(container_args))
    returncode = run_container(docker_cmd)
    sys.exit(returncode)


def main():
    app()


if __name__ == "__main__":
    main()
