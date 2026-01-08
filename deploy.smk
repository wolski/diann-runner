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

from pathlib import Path

from deploy import (
    build_oktoberfest,
    check_prerequisites,
    configure_fgcz,
    print_deployment_complete,
    verify_installation,
)

# Resolve base directory from the Snakefile location
BASE_DIR = Path(workflow.basedir).resolve() if "workflow" in globals() else Path.cwd().resolve()
CONFIG_PATH = BASE_DIR / "deploy_config.yaml"

# Load configuration (only if file exists)
if CONFIG_PATH.exists():
    configfile: str(CONFIG_PATH)

# Ensure all paths are relative to the directory containing deploy.smk
workdir: str(BASE_DIR)

# Configuration with defaults
SKIP_OKTOBERFEST = config.get("skip_oktoberfest", False)
FORCE_REBUILD = config.get("force_rebuild", False)
DEPLOY_DIR = BASE_DIR

# Deployment flags and logs directories
FLAGS_DIR = DEPLOY_DIR / ".deploy_flags"
LOGS_DIR = DEPLOY_DIR / "logs"
FLAGS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

################################################################################
# Rules
################################################################################

rule all:
    input:
        final_flag = FLAGS_DIR / "deployment_complete.flag"
    message:
        "Deployment complete! See output for next steps."


rule check_prerequisites:
    """Verify all system prerequisites are met before deployment."""
    output:
        flag = FLAGS_DIR / "prerequisites_checked.flag"
    log:
        logfile = LOGS_DIR / "check_prerequisites.log"
    run:
        check_prerequisites(output_flag=Path(output.flag))


rule create_venv:
    """Create Python virtual environment using uv."""
    input:
        prereq_flag = FLAGS_DIR / "prerequisites_checked.flag"
    output:
        venv_dir = directory(".venv"),
        flag = FLAGS_DIR / "venv_created.flag"
    log:
        logfile = LOGS_DIR / "create_venv.log"
    shell:
        """
        if [ -d .venv ]; then
            echo "Virtual environment .venv already exists, using it"
        else
            echo "Creating virtual environment with uv..."
            uv venv
            echo "Virtual environment created"
        fi
        touch {output.flag:q}
        """


rule install_package:
    """Install diann_runner package in editable mode."""
    input:
        venv = ".venv",
        venv_flag = FLAGS_DIR / "venv_created.flag",
        pyproject = "pyproject.toml"
    output:
        flag = FLAGS_DIR / "package_installed.flag"
    log:
        logfile = LOGS_DIR / "install_package.log"
    shell:
        """
        echo "Installing diann_runner package..."
        uv pip install --python .venv/bin/python -e .
        echo "Package installed"
        touch {output.flag:q}
        """


rule build_diann_docker:
    """Build diann:2.3.1 Docker image (~10 minutes, 766MB)."""
    input:
        dockerfile = "docker/Dockerfile.diann-2.3.1",
        pkg_flag = FLAGS_DIR / "package_installed.flag"
    output:
        flag = FLAGS_DIR / "diann_docker_built.flag"
    log:
        logfile = LOGS_DIR / "build_diann_docker.log"
    params:
        force_rebuild = FORCE_REBUILD
    shell:
        """
        if docker images | grep -q "^diann.*2.3.1" && [ "{params.force_rebuild}" != "True" ]; then
            echo "diann:2.3.1 already exists (use --config force_rebuild=true to rebuild)"
        else
            echo "Building diann:2.3.1 (this takes ~10 minutes)..."
            docker build -f {input.dockerfile:q} -t diann:2.3.1 . 2>&1 | tee {log.logfile:q}
            echo "diann:2.3.1 built successfully"
        fi
        touch {output.flag:q}
        """


rule build_thermorawfileparser_docker:
    """Build thermorawfileparser:linux Docker image for x86_64 servers."""
    input:
        dockerfile = "docker/Dockerfile.thermorawfileparser-linux",
        pkg_flag = FLAGS_DIR / "package_installed.flag"
    output:
        flag = FLAGS_DIR / "thermorawfileparser_docker_built.flag"
    log:
        logfile = LOGS_DIR / "build_thermorawfileparser_docker.log"
    params:
        force_rebuild = FORCE_REBUILD
    shell:
        """
        if docker images | grep -q "^thermorawfileparser.*linux" && [ "{params.force_rebuild}" != "True" ]; then
            echo "thermorawfileparser:linux already exists (use --config force_rebuild=true to rebuild)"
        else
            echo "Building thermorawfileparser:linux..."
            docker build -f {input.dockerfile:q} -t thermorawfileparser:linux . 2>&1 | tee {log.logfile:q}
            echo "thermorawfileparser:linux built successfully"
        fi
        touch {output.flag:q}
        """


rule build_oktoberfest_docker:
    """Build oktoberfest:latest Docker image (~30-60 minutes, 4GB) - optional."""
    input:
        pkg_flag = FLAGS_DIR / "package_installed.flag"
    output:
        flag = FLAGS_DIR / "oktoberfest_docker_built.flag"
    log:
        logfile = LOGS_DIR / "build_oktoberfest_docker.log"
    run:
        build_oktoberfest(
            output_flag=Path(output.flag),
            log_file=Path(log.logfile),
            skip=SKIP_OKTOBERFEST,
            force_rebuild=FORCE_REBUILD
        )


rule verify_installation:
    """Verify all CLI tools are installed and working."""
    input:
        pkg_flag = FLAGS_DIR / "package_installed.flag",
        diann_flag = FLAGS_DIR / "diann_docker_built.flag",
        thermo_flag = FLAGS_DIR / "thermorawfileparser_docker_built.flag",
        oktoberfest_flag = FLAGS_DIR / "oktoberfest_docker_built.flag"
    output:
        flag = FLAGS_DIR / "installation_verified.flag"
    log:
        logfile = LOGS_DIR / "verify_installation.log"
    run:
        verify_installation(
            deploy_dir=DEPLOY_DIR,
            output_flag=Path(output.flag)
        )


rule configure_fgcz:
    """Display FGCZ-specific configuration information."""
    input:
        verify_flag = FLAGS_DIR / "installation_verified.flag"
    output:
        flag = FLAGS_DIR / "fgcz_configured.flag"
    log:
        logfile = LOGS_DIR / "configure_fgcz.log"
    run:
        configure_fgcz(output_flag=Path(output.flag))


rule deployment_complete:
    """Final deployment marker with summary."""
    input:
        fgcz_flag = FLAGS_DIR / "fgcz_configured.flag"
    output:
        flag = FLAGS_DIR / "deployment_complete.flag"
    log:
        logfile = LOGS_DIR / "deployment_complete.log"
    run:
        print_deployment_complete(
            deploy_dir=DEPLOY_DIR,
            output_flag=Path(output.flag)
        )


################################################################################
# Cleanup Rules (optional)
################################################################################

rule clean_deployment:
    """Remove deployment flags to allow re-deployment."""
    log:
        logfile = LOGS_DIR / "clean_deployment.log"
    params:
        flags_dir = FLAGS_DIR
    shell:
        """
        echo "Removing deployment flags..."
        rm -rf {params.flags_dir:q}
        echo "Deployment flags removed."
        echo "Re-run: snakemake -s deploy.smk --cores 1"
        """


rule clean_all:
    """Remove deployment flags, venv, and Docker images."""
    log:
        logfile = LOGS_DIR / "clean_all.log"
    params:
        flags_dir = FLAGS_DIR
    shell:
        """
        echo "WARNING: This will remove:"
        echo "  - Deployment flags (.deploy_flags/)"
        echo "  - Virtual environment (.venv/)"
        echo "  - Oktoberfest build directory (oktoberfest_build/)"
        echo "  - Docker images (diann:2.3.1, thermorawfileparser:linux, oktoberfest:latest)"
        echo ""
        read -p "Continue? [y/N]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Removing deployment flags..."
            rm -rf {params.flags_dir:q}

            echo "Removing virtual environment..."
            rm -rf .venv

            echo "Removing Oktoberfest build directory..."
            rm -rf oktoberfest_build

            echo "Removing Docker images..."
            docker rmi diann:2.3.1 2>/dev/null || true
            docker rmi thermorawfileparser:linux 2>/dev/null || true
            docker rmi oktoberfest:latest 2>/dev/null || true

            echo "Cleanup complete"
        else
            echo "Cancelled"
        fi
        """
