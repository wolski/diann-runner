#!/usr/bin/env python3
"""
diann_docker.py — Run DIA-NN inside Docker.

Usage:
  diann-docker [OPTIONS] <DIA-NN args>

Note: Use relative paths or run from your data directory.
      Current directory is mounted to /work in the container.

Env vars (can also use CLI options):
  DIANN_DOCKER_IMAGE   Docker image (default: "diann:2.3.2")
  DIANN_PLATFORM       Override docker --platform
  DIANN_EXTRA          Extra docker run args
"""

import os
import shlex
import sys
from typing import Annotated

import cyclopts

from diann_runner.docker_utils import DockerCommandBuilder, run_container

# --- Settings from environment ---
DEFAULT_IMAGE = os.environ.get("DIANN_DOCKER_IMAGE", "diann:2.3.2")
DEFAULT_PLATFORM = os.environ.get("DIANN_PLATFORM", "")
DEFAULT_EXTRA = os.environ.get("DIANN_EXTRA", "")

app = cyclopts.App(
    name="diann-docker",
    help="Run DIA-NN inside Docker container",
)


def build_docker_cmd(
    diann_args: list[str],
    image: str,
    platform_override: str,
    extra_args: list[str],
) -> list[str]:
    """Build the Docker command for DIA-NN."""
    builder = (
        DockerCommandBuilder(image)
        .with_cleanup()
        .with_platform(force_amd64_on_arm=True, override=platform_override)
        .with_uid_gid()
        .with_mount(os.getcwd(), "/work")
        .with_workdir("/work")
        .with_resource_limits()
    )

    if extra_args:
        builder.with_extra_args(extra_args)

    return builder.build(diann_args)


@app.default
def run(
    *diann_args: Annotated[str, cyclopts.Parameter(show=False)],
    image: Annotated[str, cyclopts.Parameter(help="Docker image to use")] = DEFAULT_IMAGE,
    platform: Annotated[str, cyclopts.Parameter(help="Docker platform (e.g., linux/amd64)")] = DEFAULT_PLATFORM,
    extra: Annotated[str, cyclopts.Parameter(help="Extra docker run arguments")] = DEFAULT_EXTRA,
) -> None:
    """
    Run DIA-NN with the provided arguments inside a Docker container.

    Example:
        diann-docker --f data/sample.mzML --fasta ref.fasta --out report.tsv
    """
    extra_args = shlex.split(extra) if extra else []
    docker_cmd = build_docker_cmd(list(diann_args), image, platform, extra_args)
    returncode = run_container(docker_cmd)
    sys.exit(returncode)


def main():
    app()


if __name__ == "__main__":
    main()
