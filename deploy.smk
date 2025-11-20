"""
deploy.smk - Snakemake workflow for deploying diann_runner to FGCZ Linux servers

Prerequisites:
    - Python 3.10+
    - Docker (with daemon running)
    - Git
    - Snakemake (to run this workflow)
    - uv (package manager)

Usage:
    # Default deployment (includes oktoberfest)
    snakemake -s deploy.smk --cores 1

    # Skip oktoberfest build (faster)
    snakemake -s deploy.smk --cores 1 --config skip_oktoberfest=true

    # Dry run to see what will be executed
    snakemake -s deploy.smk --cores 1 --dry-run

    # Force rebuild of Docker images
    snakemake -s deploy.smk --cores 1 --config force_rebuild=true

Configuration:
    Set via --config or in deploy_config.yaml:
    - skip_oktoberfest: Skip oktoberfest Docker build (default: false)
    - force_rebuild: Force rebuild of Docker images (default: false)
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Import deployment helpers
from deploy import build_oktoberfest

# Load configuration
configfile: "deploy_config.yaml" if os.path.exists("deploy_config.yaml") else "/dev/null"

# Configuration with defaults
SKIP_OKTOBERFEST = config.get("skip_oktoberfest", False)
FORCE_REBUILD = config.get("force_rebuild", False)
DEPLOY_DIR = Path.cwd()

# Deployment flags directory
FLAGS_DIR = DEPLOY_DIR / ".deploy_flags"
FLAGS_DIR.mkdir(exist_ok=True)

################################################################################
# Helper Functions
################################################################################

def check_command(cmd):
    """Check if a command is available."""
    return shutil.which(cmd) is not None

def get_cpu_cores():
    """Get number of CPU cores."""
    try:
        return os.cpu_count()
    except:
        return "unknown"

################################################################################
# Rules
################################################################################

rule all:
    input:
        FLAGS_DIR / "deployment_complete.flag"
    message:
        "✓ Deployment complete! See output for next steps."

rule check_prerequisites:
    """Verify all system prerequisites are met before deployment."""
    output:
        flag = FLAGS_DIR / "prerequisites_checked.flag"
    log:
        "logs/check_prerequisites.log"
    run:
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

        # Check Snakemake (must be installed to run this)
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

            # Check Docker daemon
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
        Path(output.flag).touch()

rule create_venv:
    """Create Python virtual environment using uv."""
    input:
        FLAGS_DIR / "prerequisites_checked.flag"
    output:
        venv_dir = directory(".venv"),
        flag = FLAGS_DIR / "venv_created.flag"
    log:
        "logs/create_venv.log"
    shell:
        """
        if [ -d .venv ]; then
            echo "ℹ  Virtual environment .venv already exists, using it"
        else
            echo "Creating virtual environment with uv..."
            uv venv
            echo "✓ Virtual environment created"
        fi

        touch {output.flag}
        """

rule install_package:
    """Install diann_runner package in editable mode."""
    input:
        venv = ".venv",
        flag = FLAGS_DIR / "venv_created.flag",
        pyproject = "pyproject.toml"
    output:
        flag = FLAGS_DIR / "package_installed.flag"
    log:
        "logs/install_package.log"
    shell:
        """
        echo "Installing diann_runner package..."
        uv pip install --python .venv/bin/python -e .
        echo "✓ Package installed"
        touch {output.flag}
        """

rule build_diann_docker:
    """Build diann:2.3.0 Docker image (~10 minutes, 766MB)."""
    input:
        dockerfile = "Dockerfile.diann",
        flag = FLAGS_DIR / "package_installed.flag"
    output:
        flag = FLAGS_DIR / "diann_docker_built.flag"
    log:
        "logs/build_diann_docker.log"
    shell:
        """
        if docker images | grep -q "^diann.*2.3.0" && [ "{FORCE_REBUILD}" != "True" ]; then
            echo "✓ diann:2.3.0 already exists (use --config force_rebuild=true to rebuild)"
        else
            echo "Building diann:2.3.0 (this takes ~10 minutes)..."
            docker build -f Dockerfile.diann -t diann:2.3.0 . 2>&1 | tee {log}
            echo "✓ diann:2.3.0 built successfully"
        fi

        touch {output.flag}
        """

rule build_oktoberfest_docker:
    """Build oktoberfest:latest Docker image (~30-60 minutes, 4GB) - optional."""
    input:
        flag = FLAGS_DIR / "package_installed.flag"
    output:
        flag = FLAGS_DIR / "oktoberfest_docker_built.flag"
    log:
        "logs/build_oktoberfest_docker.log"
    run:
        build_oktoberfest(
            output_flag=Path(output.flag),
            log_file=Path(log[0]),
            skip=SKIP_OKTOBERFEST,
            force_rebuild=FORCE_REBUILD
        )

rule verify_installation:
    """Verify all CLI tools are installed and working."""
    input:
        FLAGS_DIR / "package_installed.flag",
        FLAGS_DIR / "diann_docker_built.flag",
        FLAGS_DIR / "oktoberfest_docker_built.flag"
    output:
        flag = FLAGS_DIR / "installation_verified.flag"
    log:
        "logs/verify_installation.log"
    run:
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
            tool_path = DEPLOY_DIR / ".venv" / "bin" / tool
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
            if "diann" in line.lower() or "oktoberfest" in line.lower() or line.startswith("REPOSITORY"):
                print(f"  {line}")

        print("=" * 70)

        if not all_ok:
            print("\n✗ Some components are missing!")
            sys.exit(1)

        print("\n✓ All components verified!\n")
        Path(output.flag).touch()

rule configure_fgcz:
    """Display FGCZ-specific configuration information."""
    input:
        FLAGS_DIR / "installation_verified.flag"
    output:
        flag = FLAGS_DIR / "fgcz_configured.flag"
    log:
        "logs/configure_fgcz.log"
    run:
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
        print(f"    diann:")
        print(f"      threads: {cores}")

        print("=" * 70 + "\n")
        Path(output.flag).touch()

rule deployment_complete:
    """Final deployment marker with summary."""
    input:
        FLAGS_DIR / "fgcz_configured.flag"
    output:
        flag = FLAGS_DIR / "deployment_complete.flag"
    run:
        print("\n" + "=" * 70)
        print("✓ DEPLOYMENT COMPLETE!")
        print("=" * 70)

        print(f"\nInstallation directory: {DEPLOY_DIR}")
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
        print(f"   fish ../run_snakefile_workflow.fish --cores {get_cpu_cores()}")

        print("\n4. Or use Snakemake directly:")
        print(f"   snakemake -s ../Snakefile.DIANN3step --cores {get_cpu_cores()} all")

        print("\n5. Or use CLI for custom workflows:")
        print("   diann-workflow all-stages \\")
        print("       --fasta db.fasta \\")
        print("       --raw-files *.mzML \\")
        print("       --workunit-id WU001")

        print("\n" + "=" * 70 + "\n")

        Path(output.flag).touch()

################################################################################
# Cleanup Rules (optional)
################################################################################

rule clean_deployment:
    """Remove deployment flags to allow re-deployment."""
    shell:
        """
        echo "Removing deployment flags..."
        rm -rf {FLAGS_DIR}
        echo "✓ Deployment flags removed."
        echo "Re-run: snakemake -s deploy.smk --cores 1"
        """

rule clean_all:
    """Remove deployment flags, venv, and Docker images."""
    shell:
        """
        echo "⚠  WARNING: This will remove:"
        echo "  - Deployment flags (.deploy_flags/)"
        echo "  - Virtual environment (.venv/)"
        echo "  - Oktoberfest build directory (oktoberfest_build/)"
        echo "  - Docker images (diann:2.3.0, oktoberfest:latest)"
        echo ""
        read -p "Continue? [y/N]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Removing deployment flags..."
            rm -rf {FLAGS_DIR}

            echo "Removing virtual environment..."
            rm -rf .venv

            echo "Removing Oktoberfest build directory..."
            rm -rf oktoberfest_build

            echo "Removing Docker images..."
            docker rmi diann:2.3.0 2>/dev/null || true
            docker rmi oktoberfest:latest 2>/dev/null || true

            echo "✓ Cleanup complete"
        else
            echo "Cancelled"
        fi
        """
