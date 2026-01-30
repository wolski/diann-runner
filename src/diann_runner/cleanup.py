#!/usr/bin/env python3
"""
cleanup.py - Clean DIA-NN workflow outputs via Snakemake.

This module provides a convenience wrapper around `snakemake --delete-all-output`.
It uses Snakemake's built-in output tracking to properly clean all generated files,
including partially generated outputs like .mzML files from interrupted conversions.
"""

import subprocess
import sys
from importlib.resources import files


def get_snakefile_path() -> str:
    """Get the path to the bundled Snakefile."""
    snakefile = files("diann_runner").joinpath("Snakefile.DIANN3step.smk")
    return str(snakefile)


def main():
    """Main entry point - calls snakemake --delete-all-output."""
    snakefile_path = get_snakefile_path()

    # Build snakemake command with --delete-all-output
    # --rerun-incomplete handles killed jobs that left incomplete files
    # --unlock handles killed jobs that left directory locked
    cmd = ["snakemake", "-s", snakefile_path, "--unlock"]
    subprocess.run(cmd, capture_output=True)  # Unlock first, ignore errors if not locked

    cmd = ["snakemake", "-s", snakefile_path, "--delete-all-output", "--rerun-incomplete"]

    # Pass through any additional arguments (e.g., -n for dry-run)
    cmd.extend(sys.argv[1:])

    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
