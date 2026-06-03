#!/usr/bin/env python3
"""
prolfquapp_docker.py — Run prolfquapp/prolfqua tools inside a container.

Usage:
  prolfquapp-docker --image <image> [--runtime docker|apptainer] <command> [args...]

Examples:
  prolfquapp-docker --image prolfqua/prolfquapp:2.0.8 prolfqua_qc.sh --indir out-DIANN -s DIANN ...
  prolfquapp-docker --runtime apptainer --image /opt/sif/prolfquapp.sif prolfqua_qc.sh ...

Note: Use relative paths or run from your data directory.
      Current directory is mounted to /work in the container.
"""

import os
import sys
from typing import Annotated

import cyclopts

from diann_runner.container_utils import (
    ContainerCommandBuilder,
    Runtime,
    run_container,
)

app = cyclopts.App(
    name="prolfquapp-docker",
    help="Run prolfquapp/prolfqua tools inside a container",
)


def build_container_cmd(image: str, runtime: Runtime, argv: list[str]) -> list[str]:
    """Build the container command for prolfquapp."""
    builder = (
        ContainerCommandBuilder(image, runtime=runtime)
        .with_cleanup()
        .with_init()
        .with_uid_gid(flag="--user")
        .with_mount(os.getcwd(), "/work", style="bind")
        .with_workdir("/work")
        # Callers pass their own command (e.g. `prolfqua_qc.sh ...`) as argv,
        # so under apptainer use `exec` to override the image runscript rather
        # than `run`, which would pass the command as a runscript argument.
        .with_explicit_command()
    )

    return builder.build(argv)


@app.default
def run(
    *container_args: Annotated[str, cyclopts.Parameter(show=False)],
    image: Annotated[str, cyclopts.Parameter(help="Container image (required)")],
    runtime: Annotated[
        Runtime,
        cyclopts.Parameter(help="Container runtime: docker or apptainer"),
    ] = "docker",
) -> None:
    """
    Run a command inside the prolfquapp container.

    Example:
        prolfquapp-docker --image prolfqua/prolfquapp:2.0.8 prolfqua_qc.sh --indir out-DIANN -s DIANN
    """
    cmd = build_container_cmd(image, runtime, list(container_args))
    returncode = run_container(cmd)
    sys.exit(returncode)


def main():
    app()


if __name__ == "__main__":
    main()
