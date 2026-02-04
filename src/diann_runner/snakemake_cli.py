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


def run_snakemake(cmd: list[str]) -> tuple[int, str]:
    """Run snakemake command, streaming output and capturing it for error checking.
    
    Args:
        cmd: List of command arguments
        
    Returns:
        Tuple of (return_code, captured_output)
    """
    # Merge stderr into stdout so we can capture and stream everything easily
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1  # Line buffered
    )

    captured_lines = []
    
    if process.stdout:
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            captured_lines.append(line)
    
    returncode = process.wait()
    return returncode, "".join(captured_lines)


def main() -> int:
    """Main entry point for diann-snakemake command.

    Passes all arguments through to snakemake, automatically adding
    the -s flag pointing to the bundled Snakefile.
    
    Handles directory locking by automatically attempting unlock and retry.

    Returns:
        Exit code from snakemake
    """
    snakefile_path = get_snakefile_path()

    # Build snakemake command
    # Pass through all user arguments, prepending -s with our Snakefile path
    cmd = ["snakemake", "-s", snakefile_path] + sys.argv[1:]

    logger.info(f"Working directory: {os.getcwd()}")
    logger.info(f"Running Snakemake command: {' '.join(cmd)}")

    returncode, output = run_snakemake(cmd)
    
    # Check for LockException
    if returncode != 0 and ("LockException" in output or "Directory cannot be locked" in output):
        logger.warning("Snakemake failed with LockException. Attempting to unlock and retry...")
        
        # Build unlock command (append --unlock to original args)
        unlock_cmd = cmd + ["--unlock"]
        
        logger.info(f"Running unlock command: {' '.join(unlock_cmd)}")
        unlock_rc, _ = run_snakemake(unlock_cmd)
        
        if unlock_rc == 0:
            logger.info("Unlock successful. Retrying original command...")
            returncode, output = run_snakemake(cmd)
            if returncode == 0:
                logger.info("Retry successful.")
            else:
                logger.error("Retry failed.")
        else:
            logger.error("Failed to unlock directory.")

    return returncode


if __name__ == "__main__":
    sys.exit(main())
