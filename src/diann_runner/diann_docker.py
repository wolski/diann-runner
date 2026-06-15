#!/usr/bin/env python3
"""
diann_docker.py — Run DIA-NN inside a container (Docker or Apptainer).

Usage:
  diann-docker --image <image> [--runtime docker|apptainer] [OPTIONS] <DIA-NN args>

Examples:
  diann-docker --image diann:2.3.2 --f data/sample.mzML --fasta ref.fasta --out report.tsv
  diann-docker --runtime apptainer --image /opt/sif/diann_2.3.2.sif --f data/sample.mzML ...

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
    name="diann-docker",
    help="Run DIA-NN inside a container (Docker or Apptainer)",
)


def _parse_mount_spec(spec: str) -> tuple[str, str, bool]:
    """Parse a ``HOST:CONTAINER[:ro]`` mount spec.

    Returns ``(source, target, read_only)``. POSIX paths only (no Windows
    drive-letter colons), which is all DIA-NN runs on.
    """
    parts = spec.split(":")
    if len(parts) == 2:
        return parts[0], parts[1], False
    if len(parts) == 3 and parts[2] == "ro":
        return parts[0], parts[1], True
    raise ValueError(
        f"Invalid --mount spec {spec!r}; expected HOST:CONTAINER or HOST:CONTAINER:ro"
    )


def build_container_cmd(
    diann_args: list[str],
    image: str,
    runtime: Runtime,
    platform_override: str,
    mounts: tuple[str, ...] = (),
) -> list[str]:
    """Build the container command for DIA-NN.

    Always mounts the working dir at ``/work`` (read-write). Additional
    ``mounts`` (``HOST:CONTAINER[:ro]``) are added on top — e.g. an external
    raw-file directory mounted read-only at ``/raw`` so DIA-NN can read raw
    files in place without them being copied into the work dir.
    """
    builder = (
        ContainerCommandBuilder(image, runtime=runtime)
        .with_cleanup()
        .with_init()
        .with_platform(force_amd64_on_arm=True, override=platform_override)
        .with_uid_gid()
        .with_mount(os.getcwd(), "/work")
        .with_workdir("/work")
        .with_resource_limits()
    )
    for spec in mounts:
        source, target, read_only = _parse_mount_spec(spec)
        builder.with_mount(source, target, read_only=read_only)

    return builder.build(diann_args)


@app.default
def run(
    *diann_args: Annotated[str, cyclopts.Parameter(show=False)],
    image: Annotated[str, cyclopts.Parameter(help="Container image (required)")],
    runtime: Annotated[
        Runtime,
        cyclopts.Parameter(help="Container runtime: docker or apptainer"),
    ] = "docker",
    platform: Annotated[
        str,
        cyclopts.Parameter(help="Docker platform (e.g., linux/amd64). Ignored under apptainer."),
    ] = "",
    mount: Annotated[
        tuple[str, ...],
        cyclopts.Parameter(help="Extra bind mount HOST:CONTAINER[:ro]; repeatable."),
    ] = (),
) -> None:
    """
    Run DIA-NN with the provided arguments inside a container.

    Example:
        diann-docker --image diann:2.3.2 --f data/sample.mzML --fasta ref.fasta --out report.tsv
        diann-docker --image diann:2.3.2 --mount /srv/gstore/raw:/raw:ro --f /raw/sample.raw ...
    """
    cmd = build_container_cmd(list(diann_args), image, runtime, platform, mounts=mount)
    returncode = run_container(cmd)
    sys.exit(returncode)


def main():
    app()


if __name__ == "__main__":
    main()
