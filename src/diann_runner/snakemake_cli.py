"""CLI wrapper for running the DIA-NN Snakemake workflow.

This module provides a command-line interface that locates the bundled
Snakefile and invokes snakemake with the correct path.

Usage:
    diann-snakemake --cores 64 -d /path/to/workdir all
    diann-snakemake --cores 8 all  # run in current directory
"""

import os
import subprocess
import sys
from importlib.resources import files

from loguru import logger


def get_snakefile_path() -> str:
    """Get the path to the bundled Snakefile.

    Returns:
        Absolute path to Snakefile.DIANN3step.smk
    """
    # Use importlib.resources to find the Snakefile in the package
    snakefile = files("diann_runner").joinpath("Snakefile.DIANN3step.smk")
    # Convert to string path (works for both installed packages and editable installs)
    return str(snakefile)


def main() -> int:
    """Main entry point for diann-snakemake command.

    Passes all arguments through to snakemake, automatically adding
    the -s flag pointing to the bundled Snakefile.

    Returns:
        Exit code from snakemake
    """
    snakefile_path = get_snakefile_path()

    # Build snakemake command
    # Pass through all user arguments, prepending -s with our Snakefile path
    cmd = ["snakemake", "-s", snakefile_path] + sys.argv[1:]

    logger.info(f"Working directory: {os.getcwd()}")
    logger.info(f"Running Snakemake command: {' '.join(cmd)}")

    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
