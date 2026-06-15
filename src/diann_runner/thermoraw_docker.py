#!/usr/bin/env python3
"""
thermoraw_docker.py — Convert Thermo RAW files to mzML format.

Provides 3 converter options:
- thermoraw: ThermoRawFileParser (native on macOS ARM, container elsewhere)
- msconvert: msconvert standard conversion (x86/Linux only)
- msconvert-demultiplex: msconvert with demultiplex filter (x86/Linux only)

Usage:
  thermoraw --image <image> [--runtime docker|apptainer] -i sample.raw -o sample.mzML
  thermoraw --image <image> -i sample.raw -o sample.mzML --converter msconvert

Examples:
  thermoraw --image thermorawfileparser:2.0.0 -i sample.raw -o sample.mzML
  thermoraw --image chambm/pwiz-skyline-i-agree-to-the-vendor-licenses -i sample.raw -o out.mzML --converter msconvert
  thermoraw --runtime apptainer --image /opt/sif/pwiz.sif -i sample.raw -o out.mzML --converter msconvert
"""

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import cyclopts

from diann_runner.container_utils import (
    ContainerCommandBuilder,
    Runtime,
    is_apple_silicon,
    print_command,
    run_container,
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


def _mount_io(
    builder: ContainerCommandBuilder, input_file: Path, output_dir: Path
) -> tuple[str, str]:
    """Set up container mounts for a conversion and return container paths.

    Always mounts the working dir read-write at ``/data`` (output goes there).
    When the input file lives OUTSIDE the working dir — an external, possibly
    read-only ``raw_file_dir`` — its parent is bind-mounted read-only at
    ``/raw`` and the input is referenced there. This is what lets conversion
    read raw files in place without copying them into the work dir, while
    conversion outputs are always written under the work dir.

    Returns ``(container_input, container_output)``.
    """
    cwd = Path(os.getcwd()).resolve()
    builder.with_mount(str(cwd), "/data")

    out_res = output_dir.resolve()
    try:
        container_output = f"/data/{out_res.relative_to(cwd)}"
    except ValueError as exc:
        raise ValueError(
            f"Conversion output dir must be under the working dir {cwd}: {out_res}"
        ) from exc

    in_res = input_file.resolve()
    try:
        container_input = f"/data/{in_res.relative_to(cwd)}"
    except ValueError:
        builder.with_mount(str(in_res.parent), "/raw", read_only=True)
        container_input = f"/raw/{in_res.name}"

    return container_input, container_output


def _run_thermoraw_container(
    input_file: Path,
    output_dir: Path,
    image: str,
    runtime: Runtime,
) -> int:
    """Run ThermoRawFileParser inside a container."""
    builder = (
        ContainerCommandBuilder(image, runtime=runtime)
        .with_cleanup()
        .with_init()
        .with_platform(force_amd64_on_arm=True)
        .with_uid_gid()
    )
    container_input, container_output = _mount_io(builder, input_file, output_dir)
    cmd = builder.with_workdir("/data").build(
        ["-i", container_input, "-o", container_output, "-f", "2"]
    )

    return run_container(cmd, label=f"Running (ThermoRawFileParser {runtime})")


def _run_msconvert_container(
    input_file: Path,
    output_dir: Path,
    image: str,
    runtime: Runtime,
    demultiplex: bool = False,
) -> int:
    """Run msconvert inside a container (requires Wine, x86 only)."""
    builder = (
        ContainerCommandBuilder(image, runtime=runtime)
        .with_cleanup()
        .with_init()
    )
    container_input, container_output = _mount_io(builder, input_file, output_dir)

    options = MSCONVERT_BASE_OPTIONS
    if demultiplex:
        options = f"{options} {MSCONVERT_DEMUX_FILTER}"

    msconvert_cmd = f"wine msconvert {container_input} {options} -o {container_output}"

    cmd = (
        builder
        .with_workdir("/data")
        .with_wine_compat()
        .with_explicit_command()
        .build(["sh", "-c", msconvert_cmd])
    )

    return run_container(cmd, label=f"Running (msconvert {runtime})")


@app.default
def run(
    input_file: Annotated[Path, cyclopts.Parameter(name=["-i", "--input"])],
    output_file: Annotated[Path, cyclopts.Parameter(name=["-o", "--output"])],
    image: Annotated[str, cyclopts.Parameter(help="Container image (required for container converters)")],
    converter: Annotated[
        str,
        cyclopts.Parameter(
            help="Converter: thermoraw, msconvert, msconvert-demultiplex"
        ),
    ] = "thermoraw",
    runtime: Annotated[
        Runtime,
        cyclopts.Parameter(help="Container runtime: docker or apptainer"),
    ] = "docker",
) -> None:
    """
    Convert Thermo RAW files to mzML format.

    Converter options:
      thermoraw           ThermoRawFileParser (native on ARM Mac, container elsewhere)
      msconvert           msconvert standard conversion (x86/Linux only)
      msconvert-demultiplex  msconvert with demultiplex for overlapping DIA windows

    Examples:
        thermoraw --image thermorawfileparser:2.0.0 -i sample.raw -o sample.mzML
        thermoraw --image chambm/pwiz-skyline-i-agree-to-the-vendor-licenses -i in.raw -o out.mzML --converter msconvert
    """
    valid_converters = ("thermoraw", "msconvert", "msconvert-demultiplex")
    if converter not in valid_converters:
        print(f"Error: Invalid converter '{converter}'", file=sys.stderr)
        print(f"Valid options: {', '.join(valid_converters)}", file=sys.stderr)
        sys.exit(1)

    if converter in ("msconvert", "msconvert-demultiplex") and is_apple_silicon():
        print(
            "Error: msconvert requires Wine which doesn't run on ARM Mac.",
            file=sys.stderr,
        )
        print("Use --converter thermoraw instead.", file=sys.stderr)
        sys.exit(1)

    output_dir = output_file.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    if converter == "thermoraw":
        if NATIVE_BINARY:
            sys.exit(_run_thermoraw_native(input_file, output_dir))
        sys.exit(_run_thermoraw_container(input_file, output_dir, image, runtime))

    elif converter == "msconvert":
        sys.exit(_run_msconvert_container(input_file, output_dir, image, runtime, demultiplex=False))

    elif converter == "msconvert-demultiplex":
        sys.exit(_run_msconvert_container(input_file, output_dir, image, runtime, demultiplex=True))


def main():
    app()


if __name__ == "__main__":
    main()
