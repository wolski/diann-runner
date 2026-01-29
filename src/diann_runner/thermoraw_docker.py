#!/usr/bin/env python3
"""
thermoraw_docker.py — Run ThermoRawFileParser (native or Docker).

Converts Thermo RAW files to mzML format.

Usage:
  thermoraw -i input.raw -o output_dir -f 2
  thermoraw --help

Execution order:
  1. Native binary (if THERMORAW_BINARY is set or found in standard locations)
  2. Docker container (thermorawfileparser:2.0.0)

Env vars:
  THERMORAW_BINARY         Path to native ThermoRawFileParser binary
  THERMORAW_DOCKER_IMAGE   Docker image (default: "thermorawfileparser:2.0.0")
  THERMORAW_USE_DOCKER     Force Docker even if native available ("true"/"false")
"""

import os
import sys
import shlex
import shutil
import subprocess
import platform
from pathlib import Path

# --- Settings ---
DEFAULT_IMAGE = os.environ.get("THERMORAW_DOCKER_IMAGE", "thermorawfileparser:2.0.0")
NATIVE_BINARY_ENV = os.environ.get("THERMORAW_BINARY", "")
FORCE_DOCKER = os.environ.get("THERMORAW_USE_DOCKER", "").lower() == "true"

# Standard locations to search for native binary
def _get_search_paths() -> list[Path]:
    """Get list of paths to search for native binary."""
    # Find project root (where pyproject.toml is)
    current = Path(__file__).parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            project_bin = current / "bin" / "ThermoRawFileParser"
            break
        current = current.parent
    else:
        project_bin = Path("/nonexistent")

    return [
        project_bin,
        Path.home() / ".local" / "bin" / "ThermoRawFileParser",
        Path("/usr/local/bin/ThermoRawFileParser"),
    ]

NATIVE_SEARCH_PATHS = _get_search_paths()


def is_apple_silicon() -> bool:
    """Check if running on Apple Silicon."""
    m = platform.machine().lower()
    return ("arm" in m or "aarch64" in m) and platform.system() == "Darwin"


def find_native_binary() -> str | None:
    """Find native ThermoRawFileParser binary."""
    # Check env var first
    if NATIVE_BINARY_ENV:
        if Path(NATIVE_BINARY_ENV).is_file():
            return NATIVE_BINARY_ENV
        print(f"Warning: THERMORAW_BINARY={NATIVE_BINARY_ENV} not found", file=sys.stderr)

    # Search standard locations
    for path in NATIVE_SEARCH_PATHS:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)

    return None


def run_native(binary: str, argv: list[str]) -> int:
    """Run ThermoRawFileParser using native binary."""
    cmd = [binary] + argv
    print(f"→ Running (native): {' '.join(shlex.quote(x) for x in cmd)}", file=sys.stderr)
    result = subprocess.run(cmd)
    return result.returncode


def run_docker(argv: list[str]) -> int:
    """Run ThermoRawFileParser using Docker."""
    cmd = ["docker", "run", "--rm"]

    # Platform for Apple Silicon
    if is_apple_silicon():
        cmd += ["--platform", "linux/amd64"]

    # UID/GID for file permissions (Unix only)
    try:
        cmd += ["-u", f"{os.getuid()}:{os.getgid()}"]
    except AttributeError:
        pass  # Windows

    # Mount current directory
    cmd += ["-v", f"{os.getcwd()}:/data", "-w", "/data"]

    cmd += [DEFAULT_IMAGE]
    cmd += argv

    print(f"→ Running (docker): {' '.join(shlex.quote(x) for x in cmd)}", file=sys.stderr)
    result = subprocess.run(cmd)
    return result.returncode


def print_help():
    """Print usage information."""
    print("""ThermoRawFileParser wrapper - converts Thermo RAW files to mzML

Usage: thermoraw [options]

Common options:
  -i, --input=FILE          Input RAW file (required)
  -d, --input_directory=DIR Input directory containing RAW files
  -o, --output_directory=DIR Output directory (default: input directory)
  -f, --format=FORMAT       Output format:
                              0 = MGF
                              1 = mzML
                              2 = indexed mzML (default)
                              3 = Parquet
  -h, --help                Show help

Examples:
  # Convert single file to indexed mzML
  thermoraw -i sample.raw -o output/ -f 2

  # Convert all files in directory
  thermoraw -d raw_files/ -o converted/ -f 2

Environment variables:
  THERMORAW_BINARY         Path to native binary (auto-detected on Mac)
  THERMORAW_DOCKER_IMAGE   Docker image (default: thermorawfileparser:2.0.0)
  THERMORAW_USE_DOCKER     Force Docker even if native available
""")


def main():
    if len(sys.argv) == 1 or sys.argv[1] in ("-h", "--help"):
        print_help()
        sys.exit(0 if len(sys.argv) > 1 else 2)

    argv = sys.argv[1:]

    # Try native binary first (unless forced to use Docker)
    if not FORCE_DOCKER:
        native = find_native_binary()
        if native:
            sys.exit(run_native(native, argv))

    # Fall back to Docker
    if not shutil.which("docker"):
        print("Error: Neither native binary nor Docker found.", file=sys.stderr)
        print("Install Docker or set THERMORAW_BINARY environment variable.", file=sys.stderr)
        sys.exit(127)

    sys.exit(run_docker(argv))


if __name__ == "__main__":
    main()
