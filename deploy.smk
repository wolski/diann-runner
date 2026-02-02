"""
deploy.smk - Snakemake workflow for deploying diann_runner Docker images

Prerequisites:
    - Docker (with daemon running)
    - Snakemake (to run this workflow)

Usage:
    # Build all Docker images
    snakemake -s deploy.smk --cores 1

    # Dry run to see what will be executed
    snakemake -s deploy.smk --cores 1 --dry-run

    # Force rebuild of Docker images
    snakemake -s deploy.smk --cores 1 --config force_rebuild=true

    # Build specific image
    snakemake -s deploy.smk build_diann_docker --cores 1

    # Check if images are already available
    snakemake -s deploy.smk check_images --cores 1

Configuration:
    Set via --config:
    - force_rebuild: Force rebuild of Docker images (default: false)
    - diann_version: DIA-NN version to build (default: 2.3.2)
"""

from pathlib import Path

from deploy import (
    check_docker_images,
    check_prerequisites,
    print_deployment_complete,
)

# Resolve base directory from the Snakefile location
BASE_DIR = Path(workflow.basedir).resolve() if "workflow" in globals() else Path.cwd().resolve()

# Ensure all paths are relative to the directory containing deploy.smk
workdir: str(BASE_DIR)

# Configuration with defaults
FORCE_REBUILD = config.get("force_rebuild", False)
DIANN_VERSION = config.get("diann_version", "2.3.2")

# Deployment flags and logs directories
FLAGS_DIR = BASE_DIR / ".deploy_flags"
LOGS_DIR = BASE_DIR / "logs"
FLAGS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

################################################################################
# Rules
################################################################################

rule all:
    input:
        FLAGS_DIR / "deployment_complete.flag"
    message:
        "Deployment complete!"


rule check_prerequisites:
    """Verify Docker is available and running."""
    output:
        flag = FLAGS_DIR / "prerequisites_checked.flag"
    run:
        check_prerequisites(output_flag=Path(output.flag))


rule build_diann_docker:
    """Build DIA-NN Docker image (~10 minutes, 766MB)."""
    input:
        dockerfile = "docker/Dockerfile.diann",
        prereq_flag = FLAGS_DIR / "prerequisites_checked.flag"
    output:
        flag = FLAGS_DIR / "diann_docker_built.flag"
    log:
        LOGS_DIR / "build_diann_docker.log"
    params:
        force_rebuild = FORCE_REBUILD,
        version = DIANN_VERSION
    shell:
        """
        if docker images | grep -q "^diann.*{params.version}" && [ "{params.force_rebuild}" != "True" ]; then
            echo "diann:{params.version} already exists (use --config force_rebuild=true to rebuild)"
        else
            echo "Building diann:{params.version}..."
            docker build --build-arg DIANN_VERSION={params.version} \
                -f {input.dockerfile:q} -t diann:{params.version} . 2>&1 | tee {log:q}
        fi
        touch {output.flag:q}
        """


rule build_thermorawfileparser_docker:
    """Build thermorawfileparser:2.0.0 Docker image."""
    input:
        dockerfile = "docker/Dockerfile.thermorawfileparser-linux",
        prereq_flag = FLAGS_DIR / "prerequisites_checked.flag"
    output:
        flag = FLAGS_DIR / "thermorawfileparser_docker_built.flag"
    log:
        LOGS_DIR / "build_thermorawfileparser_docker.log"
    params:
        force_rebuild = FORCE_REBUILD
    shell:
        """
        if docker images | grep -q "^thermorawfileparser.*2.0.0" && [ "{params.force_rebuild}" != "True" ]; then
            echo "thermorawfileparser:2.0.0 already exists (use --config force_rebuild=true to rebuild)"
        else
            echo "Building thermorawfileparser:2.0.0..."
            docker build -f {input.dockerfile:q} -t thermorawfileparser:2.0.0 . 2>&1 | tee {log:q}
        fi
        touch {output.flag:q}
        """


rule deployment_complete:
    """Final deployment marker with summary."""
    input:
        FLAGS_DIR / "diann_docker_built.flag",
        FLAGS_DIR / "thermorawfileparser_docker_built.flag"
    output:
        flag = FLAGS_DIR / "deployment_complete.flag"
    run:
        print_deployment_complete(output_flag=Path(output.flag))


################################################################################
# Utility Rules
################################################################################

rule check_images:
    """Check if required Docker images are available."""
    params:
        version = DIANN_VERSION
    run:
        check_docker_images(diann_version=params.version)


rule clean:
    """Remove deployment flags to allow re-running."""
    params:
        flags_dir = FLAGS_DIR
    shell:
        """
        echo "Removing deployment flags..."
        rm -rf {params.flags_dir:q}
        echo "Done. Re-run: snakemake -s deploy.smk --cores 1"
        """


rule clean_all:
    """Remove deployment flags and Docker images."""
    params:
        flags_dir = FLAGS_DIR,
        version = DIANN_VERSION
    shell:
        """
        echo "This will remove:"
        echo "  - Deployment flags (.deploy_flags/)"
        echo "  - Docker images (diann:{params.version}, thermorawfileparser:2.0.0)"
        echo ""
        read -p "Continue? [y/N]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf {params.flags_dir:q}
            docker rmi diann:{params.version} 2>/dev/null || true
            docker rmi thermorawfileparser:2.0.0 2>/dev/null || true
            echo "Done"
        else
            echo "Cancelled"
        fi
        """
