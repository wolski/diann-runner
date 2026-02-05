#!/usr/bin/env python3
"""
diann_docker.py — Run DIA-NN inside Docker.

Usage:
  diann-docker --image <image:tag> [OPTIONS] <DIA-NN args>

Examples:
  diann-docker --image diann:2.3.2 --f data/sample.mzML --fasta ref.fasta --out report.tsv

Note: Use relative paths or run from your data directory.
      Current directory is mounted to /work in the container.
"""

import os
import sys
from typing import Annotated

import cyclopts

from diann_runner.docker_utils import DockerCommandBuilder, run_container

app = cyclopts.App(
    name="diann-docker",
    help="Run DIA-NN inside Docker container",
)


def build_docker_cmd(
    diann_args: list[str],
    image: str,
    platform_override: str,
) -> list[str]:
    """Build the Docker command for DIA-NN."""
    builder = (
        DockerCommandBuilder(image)
        .with_cleanup()
        .with_init()
        .with_platform(force_amd64_on_arm=True, override=platform_override)
        .with_uid_gid()
        .with_mount(os.getcwd(), "/work")
        .with_workdir("/work")
        .with_resource_limits()
    )

    return builder.build(diann_args)


@app.default
def run(
    *diann_args: Annotated[str, cyclopts.Parameter(show=False)],
    image: Annotated[str, cyclopts.Parameter(help="Docker image (required)")],
    platform: Annotated[str, cyclopts.Parameter(help="Docker platform (e.g., linux/amd64)")] = "",
) -> None:
    """
    Run DIA-NN with the provided arguments inside a Docker container.

    Example:
        diann-docker --image diann:2.3.2 --f data/sample.mzML --fasta ref.fasta --out report.tsv
    """
    docker_cmd = build_docker_cmd(list(diann_args), image, platform)
    returncode = run_container(docker_cmd)
    sys.exit(returncode)


def main():
    app()


if __name__ == "__main__":
    main()
