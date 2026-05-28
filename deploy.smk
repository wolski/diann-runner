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
    - diann_thermo_version: DIA-NN version for native Thermo image (default: 2.5.0)
"""

from pathlib import Path

from deploy import (
    check_apptainer_prerequisites,
    check_docker_images,
    check_prerequisites,
    print_deployment_complete,
    print_sif_deployment_complete,
)

# Resolve base directory from the Snakefile location
BASE_DIR = Path(workflow.basedir).resolve() if "workflow" in globals() else Path.cwd().resolve()

# Ensure all paths are relative to the directory containing deploy.smk
workdir: str(BASE_DIR)

# Configuration with defaults
FORCE_REBUILD = config.get("force_rebuild", False)
DIANN_VERSION = config.get("diann_version", "2.3.2")
DIANN_THERMO_VERSION = config.get("diann_thermo_version", "2.5.0")
THERMORAW_VERSION = config.get("thermoraw_version", "2.0.0")
PROLFQUAPP_VERSION = config.get("prolfquapp_version", "2.0.10")
MSCONVERT_IMAGE = config.get(
    "msconvert_image", "chambm/pwiz-skyline-i-agree-to-the-vendor-licenses"
)

# SIF output directory (used by all_sif). Defaults to ./sif relative to
# this Snakefile. Override with --config sif_output_dir=/opt/sif when
# running on the target apptainer host directly.
SIF_DIR = Path(config.get("sif_output_dir", BASE_DIR / "sif"))

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


rule all_sif:
    """Build all SIF images for apptainer deployment.

    Convert locally-built docker images to SIF via docker-daemon://, and
    pull upstream images (msconvert, prolfquapp) from Docker Hub via
    docker://. Requires both docker and apptainer on the host running
    this rule.
    """
    input:
        FLAGS_DIR / "sif_deployment_complete.flag"
    message:
        "SIF deployment complete!"


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


rule build_diann_thermo_docker:
    """Build DIA-NN image with native Thermo .raw reader (.NET 8 + DIA-NN 2.5+)."""
    input:
        dockerfile = "docker/Dockerfile.diann_thermofilereader",
        prereq_flag = FLAGS_DIR / "prerequisites_checked.flag"
    output:
        flag = FLAGS_DIR / "diann_thermo_docker_built.flag"
    log:
        LOGS_DIR / "build_diann_thermo_docker.log"
    params:
        force_rebuild = FORCE_REBUILD,
        version = DIANN_THERMO_VERSION
    shell:
        """
        TAG="diann:{params.version}-thermo"
        if docker images --format "{{{{.Repository}}}}:{{{{.Tag}}}}" | grep -q "^${{TAG}}$" && [ "{params.force_rebuild}" != "True" ]; then
            echo "${{TAG}} already exists (use --config force_rebuild=true to rebuild)"
        else
            echo "Building ${{TAG}}..."
            docker build --platform linux/amd64 --build-arg DIANN_VERSION={params.version} \
                -f {input.dockerfile:q} -t "${{TAG}}" . 2>&1 | tee {log:q}
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
        FLAGS_DIR / "diann_thermo_docker_built.flag",
        FLAGS_DIR / "thermorawfileparser_docker_built.flag"
    output:
        flag = FLAGS_DIR / "deployment_complete.flag"
    run:
        print_deployment_complete(output_flag=Path(output.flag))


################################################################################
# SIF (Apptainer) Rules
################################################################################

rule check_apptainer_prerequisites:
    """Verify apptainer + docker daemon are available for SIF building."""
    output:
        flag = FLAGS_DIR / "apptainer_prereq_checked.flag"
    run:
        check_apptainer_prerequisites(output_flag=Path(output.flag))


rule build_diann_sif:
    """Convert diann:<version> docker image to SIF via docker-daemon://."""
    input:
        prereq_flag = FLAGS_DIR / "apptainer_prereq_checked.flag",
        docker_flag = FLAGS_DIR / "diann_docker_built.flag"
    output:
        sif = SIF_DIR / f"diann_{DIANN_VERSION}.sif"
    log:
        LOGS_DIR / "build_diann_sif.log"
    params:
        tag = f"diann:{DIANN_VERSION}"
    shell:
        """
        mkdir -p "$(dirname {output.sif:q})"
        apptainer pull --force {output.sif:q} docker-daemon://{params.tag} 2>&1 | tee {log:q}
        """


rule build_diann_thermo_sif:
    """Convert diann:<version>-thermo docker image to SIF."""
    input:
        prereq_flag = FLAGS_DIR / "apptainer_prereq_checked.flag",
        docker_flag = FLAGS_DIR / "diann_thermo_docker_built.flag"
    output:
        sif = SIF_DIR / f"diann_{DIANN_THERMO_VERSION}-thermo.sif"
    log:
        LOGS_DIR / "build_diann_thermo_sif.log"
    params:
        tag = f"diann:{DIANN_THERMO_VERSION}-thermo"
    shell:
        """
        mkdir -p "$(dirname {output.sif:q})"
        apptainer pull --force {output.sif:q} docker-daemon://{params.tag} 2>&1 | tee {log:q}
        """


rule build_thermorawfileparser_sif:
    """Convert thermorawfileparser:<version> docker image to SIF."""
    input:
        prereq_flag = FLAGS_DIR / "apptainer_prereq_checked.flag",
        docker_flag = FLAGS_DIR / "thermorawfileparser_docker_built.flag"
    output:
        sif = SIF_DIR / f"thermorawfileparser_{THERMORAW_VERSION}.sif"
    log:
        LOGS_DIR / "build_thermorawfileparser_sif.log"
    params:
        tag = f"thermorawfileparser:{THERMORAW_VERSION}"
    shell:
        """
        mkdir -p "$(dirname {output.sif:q})"
        apptainer pull --force {output.sif:q} docker-daemon://{params.tag} 2>&1 | tee {log:q}
        """


rule pull_msconvert_sif:
    """Pull the upstream msconvert (pwiz) image from Docker Hub."""
    input:
        prereq_flag = FLAGS_DIR / "apptainer_prereq_checked.flag"
    output:
        sif = SIF_DIR / "pwiz.sif"
    log:
        LOGS_DIR / "pull_msconvert_sif.log"
    params:
        ref = MSCONVERT_IMAGE
    shell:
        """
        mkdir -p "$(dirname {output.sif:q})"
        apptainer pull --force {output.sif:q} docker://{params.ref} 2>&1 | tee {log:q}
        """


rule pull_prolfquapp_sif:
    """Pull the upstream prolfquapp image from Docker Hub."""
    input:
        prereq_flag = FLAGS_DIR / "apptainer_prereq_checked.flag"
    output:
        sif = SIF_DIR / f"prolfquapp_{PROLFQUAPP_VERSION}.sif"
    log:
        LOGS_DIR / "pull_prolfquapp_sif.log"
    params:
        ref = f"prolfqua/prolfquapp:{PROLFQUAPP_VERSION}"
    shell:
        """
        mkdir -p "$(dirname {output.sif:q})"
        apptainer pull --force {output.sif:q} docker://{params.ref} 2>&1 | tee {log:q}
        """


rule sif_deployment_complete:
    """Final SIF deployment marker with summary."""
    input:
        SIF_DIR / f"diann_{DIANN_VERSION}.sif",
        SIF_DIR / f"diann_{DIANN_THERMO_VERSION}-thermo.sif",
        SIF_DIR / f"thermorawfileparser_{THERMORAW_VERSION}.sif",
        SIF_DIR / "pwiz.sif",
        SIF_DIR / f"prolfquapp_{PROLFQUAPP_VERSION}.sif"
    output:
        flag = FLAGS_DIR / "sif_deployment_complete.flag"
    run:
        print_sif_deployment_complete(output_flag=Path(output.flag), sif_dir=SIF_DIR)


################################################################################
# Utility Rules
################################################################################

rule check_images:
    """Check if required Docker images are available."""
    params:
        version = DIANN_VERSION,
        thermo_version = DIANN_THERMO_VERSION
    run:
        check_docker_images(diann_version=params.version, diann_thermo_version=params.thermo_version)


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
        version = DIANN_VERSION,
        thermo_version = DIANN_THERMO_VERSION
    shell:
        """
        echo "This will remove:"
        echo "  - Deployment flags (.deploy_flags/)"
        echo "  - Docker images (diann:{params.version}, diann:{params.thermo_version}-thermo, thermorawfileparser:2.0.0)"
        echo ""
        read -p "Continue? [y/N]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf {params.flags_dir:q}
            docker rmi diann:{params.version} 2>/dev/null || true
            docker rmi diann:{params.thermo_version}-thermo 2>/dev/null || true
            docker rmi thermorawfileparser:2.0.0 2>/dev/null || true
            echo "Done"
        else
            echo "Cancelled"
        fi
        """
