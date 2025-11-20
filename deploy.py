"""Helper functions for deploy.smk"""

import subprocess
import sys
from pathlib import Path


def docker_image_exists(image_name: str) -> bool:
    """Check if Docker image exists."""
    result = subprocess.run(
        ["docker", "images", "-q", image_name],
        capture_output=True,
        text=True
    )
    return bool(result.stdout.strip())


def build_oktoberfest(
    output_flag: Path,
    log_file: Path,
    skip: bool = False,
    force_rebuild: bool = False
) -> None:
    """
    Build Oktoberfest Docker image.

    Args:
        output_flag: Path to flag file to create on success
        log_file: Path to log file for build output
        skip: If True, skip the build
        force_rebuild: If True, force rebuild even if image exists
    """
    if skip:
        print("⊘ Skipping Oktoberfest build (skip_oktoberfest=true)")
        output_flag.touch()
        return

    # Check if image already exists
    if docker_image_exists("oktoberfest:latest") and not force_rebuild:
        print("✓ oktoberfest:latest already exists (use --config force_rebuild=true to rebuild)")
        output_flag.touch()
        return

    oktoberfest_dir = Path("oktoberfest_build")

    # Clone or update Oktoberfest repository
    if not oktoberfest_dir.exists():
        print("Cloning Oktoberfest repository...")
        result = subprocess.run([
            "git", "clone", "--depth", "1", "--branch", "development",
            "https://github.com/wilhelm-lab/oktoberfest.git",
            str(oktoberfest_dir)
        ])
        if result.returncode != 0:
            print("✗ Failed to clone Oktoberfest repository")
            sys.exit(1)
    else:
        print("Updating Oktoberfest repository...")
        subprocess.run(["git", "pull"], cwd=oktoberfest_dir)

    # Generate hash.file with git commit for version tracking
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=oktoberfest_dir,
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        hash_file = oktoberfest_dir / "hash.file"
        hash_file.write_text(result.stdout.strip())
        print(f"Created hash.file with commit: {result.stdout.strip()[:8]}")

    # Build Docker image
    print("Building oktoberfest:latest (this takes ~30-60 minutes)...")
    with open(log_file, "w") as logfile:
        result = subprocess.run(
            ["docker", "build", "-t", "oktoberfest:latest", "."],
            cwd=oktoberfest_dir,
            stdout=logfile,
            stderr=subprocess.STDOUT
        )

    if result.returncode != 0:
        print(f"✗ Oktoberfest build failed - see {log_file}")
        sys.exit(1)

    print("✓ oktoberfest:latest built successfully")
    output_flag.touch()
