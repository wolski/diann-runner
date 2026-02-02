"""Helper functions for deploy.smk"""

import shutil
import subprocess
import sys
from pathlib import Path


def check_command(cmd: str) -> bool:
    """Check if a command is available in PATH."""
    return shutil.which(cmd) is not None


def check_prerequisites(output_flag: Path) -> None:
    """
    Verify Docker is available and running.

    Args:
        output_flag: Path to flag file to create on success
    """
    print("=" * 60)
    print("Checking Prerequisites")
    print("=" * 60)

    all_good = True

    # Check Docker
    if check_command("docker"):
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
        print(f"✓ {result.stdout.strip()}")

        result = subprocess.run(["docker", "ps"], capture_output=True)
        if result.returncode == 0:
            print("✓ Docker daemon is running")
        else:
            print("✗ Docker daemon is not running")
            all_good = False
    else:
        print("✗ Docker not found")
        all_good = False

    print("=" * 60)

    if not all_good:
        print("\n✗ Prerequisites check failed!")
        sys.exit(1)

    print("✓ Prerequisites OK\n")
    output_flag.touch()


def check_docker_images(diann_version: str = "2.3.2") -> None:
    """
    Check if required Docker images are available.

    Args:
        diann_version: DIA-NN version to check for
    """
    print("=" * 60)
    print("Checking Docker Images")
    print("=" * 60)

    images_to_check = [
        (f"diann:{diann_version}", f"diann:{diann_version}"),
        ("thermorawfileparser:linux", "thermorawfileparser:linux"),
    ]

    result = subprocess.run(
        ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
        capture_output=True,
        text=True
    )
    available_images = set(result.stdout.strip().split("\n"))

    all_present = True
    for image_name, display_name in images_to_check:
        if image_name in available_images:
            # Get image details
            detail = subprocess.run(
                ["docker", "images", image_name, "--format", "{{.Size}} (created {{.CreatedSince}})"],
                capture_output=True,
                text=True
            )
            print(f"✓ {display_name}: {detail.stdout.strip()}")
        else:
            print(f"✗ {display_name}: NOT FOUND")
            all_present = False

    print("=" * 60)

    if all_present:
        print("✓ All required images are available\n")
    else:
        print("\n✗ Some images are missing!")
        print("  Run: snakemake -s deploy.smk --cores 1\n")


def print_deployment_complete(output_flag: Path) -> None:
    """
    Print final deployment summary.

    Args:
        output_flag: Path to flag file to create on success
    """
    print("\n" + "=" * 60)
    print("Docker Images Built")
    print("=" * 60)

    result = subprocess.run(
        ["docker", "images", "--format", "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"],
        capture_output=True,
        text=True
    )

    for line in result.stdout.split("\n"):
        if "diann" in line.lower() or "thermorawfileparser" in line.lower() or line.startswith("REPOSITORY"):
            print(f"  {line}")

    print("=" * 60)
    print("\nTest with:")
    print("  docker run --rm diann:2.3.2 --help")
    print("=" * 60 + "\n")

    output_flag.touch()
