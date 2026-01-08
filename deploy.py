"""Helper functions for deploy.smk"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def check_command(cmd: str) -> bool:
    """Check if a command is available in PATH."""
    return shutil.which(cmd) is not None


def get_cpu_cores() -> int | str:
    """Get number of CPU cores."""
    try:
        return os.cpu_count() or "unknown"
    except Exception:
        return "unknown"


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


def check_prerequisites(output_flag: Path) -> None:
    """
    Verify all system prerequisites are met before deployment.

    Args:
        output_flag: Path to flag file to create on success
    """
    print("=" * 70)
    print("Checking Prerequisites")
    print("=" * 70)

    all_good = True

    # Check Python version
    python_version = sys.version_info
    if python_version >= (3, 10):
        print(f"✓ Python {python_version.major}.{python_version.minor}.{python_version.micro}")
    else:
        print(f"✗ Python {python_version.major}.{python_version.minor}.{python_version.micro} (requires >=3.10)")
        all_good = False

    # Check Snakemake
    if check_command("snakemake"):
        result = subprocess.run(["snakemake", "--version"], capture_output=True, text=True)
        print(f"✓ Snakemake: {result.stdout.strip()}")
    else:
        print("✗ Snakemake not found (required to run this workflow)")
        all_good = False

    # Check uv
    if check_command("uv"):
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True)
        print(f"✓ uv: {result.stdout.strip()}")
    else:
        print("✗ uv not found (install from: https://astral.sh/uv)")
        all_good = False

    # Check Docker
    if check_command("docker"):
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
        print(f"✓ Docker: {result.stdout.strip()}")

        result = subprocess.run(["docker", "ps"], capture_output=True)
        if result.returncode == 0:
            print("✓ Docker daemon is running")
        else:
            print("✗ Docker daemon is not running")
            all_good = False
    else:
        print("✗ Docker not found")
        all_good = False

    # Check Git
    if check_command("git"):
        result = subprocess.run(["git", "--version"], capture_output=True, text=True)
        print(f"✓ Git: {result.stdout.strip()}")
    else:
        print("✗ Git not found")
        all_good = False

    # Check Fish (optional)
    if check_command("fish"):
        result = subprocess.run(["fish", "--version"], capture_output=True, text=True)
        print(f"✓ Fish: {result.stdout.strip()}")
    else:
        print("ℹ  Fish shell not found (optional)")

    # Check disk space
    stat = shutil.disk_usage(".")
    available_gb = stat.free // (1024**3)
    if available_gb > 50:
        print(f"✓ Disk space: {available_gb}GB available")
    else:
        print(f"⚠  Disk space: {available_gb}GB available (50GB+ recommended)")

    # Check CPU cores
    cores = get_cpu_cores()
    print(f"ℹ  CPU cores: {cores}")

    print("=" * 70)

    if not all_good:
        print("\n✗ Prerequisites check failed! Install missing components and re-run.")
        sys.exit(1)

    print("\n✓ All prerequisites met!\n")
    output_flag.touch()


def verify_installation(deploy_dir: Path, output_flag: Path) -> None:
    """
    Verify all CLI tools are installed and working.

    Args:
        deploy_dir: Base deployment directory
        output_flag: Path to flag file to create on success
    """
    print("\n" + "=" * 70)
    print("Verifying Installation")
    print("=" * 70)

    all_ok = True

    # Check CLI tools
    print("\nChecking CLI tools:")
    tools = [
        "diann-docker",
        "diann-workflow",
        "diann-cleanup",
        "diann-qc",
        "oktoberfest-docker",
        "prolfquapp-docker"
    ]

    for tool in tools:
        tool_path = deploy_dir / ".venv" / "bin" / tool
        if tool_path.exists():
            print(f"  ✓ {tool}")
        else:
            print(f"  ✗ {tool} not found")
            all_ok = False

    # Check Docker images
    print("\nDocker images:")
    result = subprocess.run(
        ["docker", "images", "--format", "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"],
        capture_output=True,
        text=True
    )

    for line in result.stdout.split("\n"):
        if "diann" in line.lower() or "thermorawfileparser" in line.lower() or "oktoberfest" in line.lower() or line.startswith("REPOSITORY"):
            print(f"  {line}")

    print("=" * 70)

    if not all_ok:
        print("\n✗ Some components are missing!")
        sys.exit(1)

    print("\n✓ All components verified!\n")
    output_flag.touch()


def configure_fgcz(output_flag: Path) -> None:
    """
    Display FGCZ-specific configuration information.

    Args:
        output_flag: Path to flag file to create on success
    """
    print("\n" + "=" * 70)
    print("FGCZ Configuration")
    print("=" * 70)

    # Check BFabric runner
    bfabric_path = "/home/bfabric/slurmworker/bin/fgcz_app_runner"
    if os.path.exists(bfabric_path):
        print(f"✓ BFabric runner found: {bfabric_path}")
    else:
        print(f"ℹ  BFabric runner not found: {bfabric_path}")
        print("  (This is normal for test servers)")

    # CPU cores recommendation
    cores = get_cpu_cores()
    print(f"\nℹ  Detected {cores} CPU cores")
    print("\nRecommended params.yml configuration:")
    print("    diann:")
    print(f"      threads: {cores}")

    print("=" * 70 + "\n")
    output_flag.touch()


def print_deployment_complete(deploy_dir: Path, output_flag: Path) -> None:
    """
    Print final deployment summary with next steps.

    Args:
        deploy_dir: Base deployment directory
        output_flag: Path to flag file to create on success
    """
    cores = get_cpu_cores()

    print("\n" + "=" * 70)
    print("✓ DEPLOYMENT COMPLETE!")
    print("=" * 70)

    print(f"\nInstallation directory: {deploy_dir}")
    print("Virtual environment: .venv")

    print("\n" + "-" * 70)
    print("NEXT STEPS:")
    print("-" * 70)

    print("\n1. Activate the virtual environment:")
    print("   source .venv/bin/activate.fish  # Fish shell")
    print("   source .venv/bin/activate       # Bash shell")

    print("\n2. Test the installation:")
    print("   diann-docker --help")
    print("   diann-workflow --help")

    print("\n3. Run a workflow with existing Fish scripts:")
    print("   cd WU_YOURPROJECT")
    print(f"   fish ../run_snakefile_workflow.fish --cores {cores}")

    print("\n4. Or use Snakemake directly:")
    print(f"   snakemake -s ../Snakefile.DIANN3step --cores {cores} all")

    print("\n5. Or use CLI for custom workflows:")
    print("   diann-workflow all-stages \\")
    print("       --fasta db.fasta \\")
    print("       --raw-files *.mzML \\")
    print("       --workunit-id WU001")

    print("\n" + "=" * 70 + "\n")

    output_flag.touch()
