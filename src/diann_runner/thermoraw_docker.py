#!/usr/bin/env python3
"""
thermoraw_docker.py — Convert Thermo RAW files to mzML format.

Provides 3 converter options:
- thermoraw: ThermoRawFileParser (native on macOS ARM, Docker elsewhere)
- msconvert: msconvert standard conversion (x86/Linux only)
- msconvert-demultiplex: msconvert with demultiplex filter (x86/Linux only)

Usage:
  thermoraw -i sample.raw -o sample.mzML
  thermoraw -i sample.raw -o sample.mzML --converter msconvert
  thermoraw -i sample.raw -o sample.mzML --converter msconvert-demultiplex
"""

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import cyclopts

from diann_runner.docker_utils import (
    DockerCommandBuilder,
    is_apple_silicon,
    print_command,
    run_container,
)

# --- Default Docker Images ---
DEFAULT_THERMORAW_IMAGE = os.environ.get(
    "THERMORAW_DOCKER_IMAGE", "thermorawfileparser:2.0.0"
)
DEFAULT_MSCONVERT_IMAGE = os.environ.get(
    "MSCONVERT_DOCKER_IMAGE", "chambm/pwiz-skyline-i-agree-to-the-vendor-licenses"
)

# --- msconvert options (hardcoded for consistency) ---
MSCONVERT_BASE_OPTIONS = '--mzML --64 --zlib --filter "peakPicking vendor msLevel=1-"'
MSCONVERT_DEMUX_FILTER = '--filter "demultiplex optimization=overlap_only massError=10.0ppm"'

app = cyclopts.App(
    name="thermoraw",
    help="Convert Thermo RAW files to mzML format",
)


def _get_native_binary() -> Path | None:
    """Get path to native ThermoRawFileParser binary on macOS, None elsewhere."""
    if platform.system() != "Darwin":
        return None

    # Find package root (where pyproject.toml is)
    current = Path(__file__).parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            binary = current / "tools" / "ThermoRawFileParser-osx" / "ThermoRawFileParser"
            if binary.is_file():
                return binary
            break
        current = current.parent

    return None


NATIVE_BINARY = _get_native_binary()


def _run_thermoraw_native(input_file: Path, output_dir: Path) -> int:
    """Run ThermoRawFileParser using native binary."""
    cmd = [
        str(NATIVE_BINARY),
        "-i", str(input_file),
        "-o", str(output_dir),
        "-f", "2",  # indexed mzML format
    ]
    print_command(cmd, label="Running (native ThermoRawFileParser)")
    result = subprocess.run(cmd)
    return result.returncode


def _run_thermoraw_docker(input_file: Path, output_dir: Path, image: str) -> int:
    """Run ThermoRawFileParser using Docker."""
    cwd = os.getcwd()
    # Paths relative to mount point
    container_input = f"/data/{input_file.resolve().relative_to(cwd)}"
    container_output = f"/data/{output_dir.resolve().relative_to(cwd)}"

    cmd = (
        DockerCommandBuilder(image)
        .with_cleanup()
        .with_platform(force_amd64_on_arm=True)
        .with_uid_gid()
        .with_mount(cwd, "/data")
        .with_workdir("/data")
        .build(["-i", container_input, "-o", container_output, "-f", "2"])
    )

    return run_container(cmd, label="Running (ThermoRawFileParser Docker)")


def _run_msconvert_docker(
    input_file: Path,
    output_dir: Path,
    image: str,
    demultiplex: bool = False,
) -> int:
    """Run msconvert using Docker (requires Wine, x86 only)."""
    cwd = os.getcwd()
    container_input = f"/data/{input_file.resolve().relative_to(cwd)}"
    container_output = f"/data/{output_dir.resolve().relative_to(cwd)}"

    # Build msconvert options
    options = MSCONVERT_BASE_OPTIONS
    if demultiplex:
        options = f"{options} {MSCONVERT_DEMUX_FILTER}"

    # msconvert via Wine in Docker
    msconvert_cmd = f"wine msconvert {container_input} {options} -o {container_output}"

    cmd = (
        DockerCommandBuilder(image)
        .with_cleanup()
        .with_mount(cwd, "/data")
        .with_workdir("/data")
        .build(["sh", "-c", msconvert_cmd])
    )

    return run_container(cmd, label="Running (msconvert Docker)")


@app.default
def run(
    input_file: Annotated[Path, cyclopts.Parameter(name=["-i", "--input"])],
    output_file: Annotated[Path, cyclopts.Parameter(name=["-o", "--output"])],
    converter: Annotated[
        str,
        cyclopts.Parameter(
            help="Converter: thermoraw, msconvert, msconvert-demultiplex"
        ),
    ] = "thermoraw",
    image: Annotated[
        str | None,
        cyclopts.Parameter(help="Docker image override"),
    ] = None,
) -> None:
    """
    Convert Thermo RAW files to mzML format.

    Converter options:
      thermoraw           ThermoRawFileParser (native on ARM Mac, Docker elsewhere)
      msconvert           msconvert standard conversion (x86/Linux only)
      msconvert-demultiplex  msconvert with demultiplex for overlapping DIA windows

    Examples:
        thermoraw -i sample.raw -o sample.mzML
        thermoraw -i input/sample.raw -o input/sample.mzML --converter msconvert
    """
    # Validate converter option
    valid_converters = ("thermoraw", "msconvert", "msconvert-demultiplex")
    if converter not in valid_converters:
        print(f"Error: Invalid converter '{converter}'", file=sys.stderr)
        print(f"Valid options: {', '.join(valid_converters)}", file=sys.stderr)
        sys.exit(1)

    # Check ARM Mac compatibility for msconvert
    if converter in ("msconvert", "msconvert-demultiplex") and is_apple_silicon():
        print(
            "Error: msconvert requires Wine which doesn't run on ARM Mac.",
            file=sys.stderr,
        )
        print("Use --converter thermoraw instead.", file=sys.stderr)
        sys.exit(1)

    # Extract output directory from output file path
    output_dir = output_file.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Route to appropriate converter
    if converter == "thermoraw":
        # Use native binary on macOS if available
        if NATIVE_BINARY:
            sys.exit(_run_thermoraw_native(input_file, output_dir))
        else:
            img = image or DEFAULT_THERMORAW_IMAGE
            sys.exit(_run_thermoraw_docker(input_file, output_dir, img))

    elif converter == "msconvert":
        img = image or DEFAULT_MSCONVERT_IMAGE
        sys.exit(_run_msconvert_docker(input_file, output_dir, img, demultiplex=False))

    elif converter == "msconvert-demultiplex":
        img = image or DEFAULT_MSCONVERT_IMAGE
        sys.exit(_run_msconvert_docker(input_file, output_dir, img, demultiplex=True))


def main():
    app()


if __name__ == "__main__":
    main()
