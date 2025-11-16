#!/usr/bin/env python3
"""
cleanup.py - Clean DIA-NN workflow outputs and caches

This module provides cleanup functionality for DIA-NN workflow runs.
It removes temporary files, output directories, and caches that can
become stale when libraries or parameters change.
"""

import os
import sys
import shutil
from pathlib import Path


def get_work_directory() -> Path:
    """Get the current working directory as a Path object."""
    return Path.cwd()


def cleanup_logs_only():
    """Remove only log files."""
    print("Cleaning log files only...")
    work_dir = get_work_directory()

    patterns = ["workflow*.log", "diann*.log.txt"]
    removed = 0

    for pattern in patterns:
        for file in work_dir.glob(pattern):
            file.unlink()
            removed += 1
            print(f"  Removed: {file.name}")

    if removed == 0:
        print("  No log files found")
    else:
        print(f"✓ Cleaned {removed} log file(s)")


def cleanup_soft():
    """Clean Step B/C outputs but keep Step A library."""
    print("Soft clean: keeping Step A outputs, cleaning Step B/C...")
    work_dir = get_work_directory()

    dirs_to_remove = [
        "temp-DIANN_quantB",
        "temp-DIANN_quantC",
        "out-DIANN_quantB",
        "out-DIANN_quantC",
        "out-DIANN"
    ]

    files_to_remove = [
        "step_B_quantification_refinement.sh",
        "step_C_final_quantification.sh"
    ]

    # Remove directories
    for dir_name in dirs_to_remove:
        dir_path = work_dir / dir_name
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"  Removed: {dir_name}/")

    # Remove files
    for file_name in files_to_remove:
        file_path = work_dir / file_name
        if file_path.exists():
            file_path.unlink()
            print(f"  Removed: {file_name}")

    # Clean Snakemake locks
    locks_dir = work_dir / ".snakemake" / "locks"
    if locks_dir.exists():
        for lock_file in locks_dir.iterdir():
            lock_file.unlink()
        print("  Removed: .snakemake/locks/*")

    print("✓ Step B/C cleaned (Step A library preserved)")


def cleanup_full():
    """Full clean: remove all outputs and caches."""
    work_dir = get_work_directory()

    print("Full clean: removing all outputs and caches...")
    print("This will delete:")
    print("  - All generated scripts (step_*.sh)")
    print("  - All temp directories (temp-DIANN*)")
    print("  - All output directories (out-DIANN*)")
    print("  - Snakemake cache (.snakemake/)")
    print("  - Log files (workflow*.log)")
    print()

    # Get user confirmation
    try:
        response = input("Continue? (y/N) ").strip().lower()
        if response not in ('y', 'yes'):
            print("Cancelled")
            return
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled")
        return

    # Remove generated scripts
    for script in work_dir.glob("step_*.sh"):
        script.unlink()
        print(f"  Removed: {script.name}")

    # Remove temp directories
    for temp_dir in work_dir.glob("temp-DIANN*"):
        shutil.rmtree(temp_dir)
        print(f"  Removed: {temp_dir.name}/")

    # Remove output directories
    for out_dir in work_dir.glob("out-DIANN*"):
        shutil.rmtree(out_dir)
        print(f"  Removed: {out_dir.name}/")

    # Remove Snakemake cache
    snakemake_dir = work_dir / ".snakemake"
    if snakemake_dir.exists():
        shutil.rmtree(snakemake_dir)
        print("  Removed: .snakemake/")

    # Remove log files
    for log_file in work_dir.glob("workflow*.log"):
        log_file.unlink()
        print(f"  Removed: {log_file.name}")

    for log_file in work_dir.glob("diann*.log.txt"):
        log_file.unlink()
        print(f"  Removed: {log_file.name}")

    print("✓ Full cleanup complete")
    print()
    print("To restart the workflow, run:")
    print("  snakemake -s ../Snakefile.DIANN3step --cores 8 all")


def print_usage():
    """Print usage information."""
    print("""Usage: python -m diann_runner.cleanup [OPTIONS]

Clean DIA-NN workflow outputs and caches.

Options:
  --soft        Keep Step A library (only clean Step B/C)
  --logs-only   Only clean log files
  -h, --help    Show this help message

Examples:
  python -m diann_runner.cleanup              # Full clean (interactive)
  python -m diann_runner.cleanup --soft       # Clean Step B/C only
  python -m diann_runner.cleanup --logs-only  # Clean logs only

Note: Run this from your work directory (e.g., WU12345_work/)
""")


def main():
    """Main entry point."""
    args = sys.argv[1:]

    # Handle help
    if '-h' in args or '--help' in args:
        print_usage()
        sys.exit(0)

    # Handle no arguments - default to full clean
    if len(args) == 0:
        cleanup_full()
        sys.exit(0)

    # Handle specific modes
    if '--logs-only' in args:
        cleanup_logs_only()
    elif '--soft' in args:
        cleanup_soft()
    else:
        print(f"Unknown option: {args[0]}")
        print("Run with --help for usage information")
        sys.exit(1)


if __name__ == "__main__":
    main()
