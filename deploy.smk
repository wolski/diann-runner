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

    # Build a single image (target its flag), e.g. only DIA-NN 2.5.1:
    snakemake -s deploy.smk .deploy_flags/diann_2.5.1_built.flag --cores 1

    # Check if images are already available
    snakemake -s deploy.smk check_images --cores 1

Configuration:
    Set via --config:
    - force_rebuild: Force rebuild of Docker images (default: false)

DIA-NN versions:
    All DIA-NN images are built — one per entry in images.docker.diann_images
    in src/diann_runner/config/defaults_server.yml, which mirrors the
    01_diann_version dropdown in the bfabric XML executable. To add a version,
    add the enumeration to the XML and the entry to the config map; deploy.smk
    picks it up automatically.
"""

import re
from pathlib import Path

from deploy import (
    check_apptainer_prerequisites,
    check_docker_images,
    check_prerequisites,
    generate_def_from_dockerfile,
    load_deploy_settings,
    load_diann_build_matrix,
    load_msconvert_image,
    load_prolfquapp_version,
    load_thermoraw_version,
    print_deployment_complete,
    print_sif_deployment_complete,
)

# Resolve base directory from the Snakefile location
BASE_DIR = Path(workflow.basedir).resolve() if "workflow" in globals() else Path.cwd().resolve()

# Ensure all paths are relative to the directory containing deploy.smk
workdir: str(BASE_DIR)

# Single config source: everything deploy.smk needs comes from
# src/diann_runner/config/defaults_server.yml — the same file the runtime
# workflow (Snakefile.DIANN3step) reads. There is no separate deploy config
# file. Build-time knobs live in its `deploy:` block; image versions are
# derived from its `images:` block. An explicit `--config key=value` still
# overrides any of these for a one-off build.
DEPLOY = load_deploy_settings()

FORCE_REBUILD = config.get("force_rebuild", DEPLOY["force_rebuild"])
THERMORAW_VERSION = config.get("thermoraw_version", load_thermoraw_version())
PROLFQUAPP_VERSION = config.get("prolfquapp_version", load_prolfquapp_version())
MSCONVERT_IMAGE = config.get("msconvert_image", load_msconvert_image())

# DIA-NN build matrix — one entry per version in the diann_images config map
# (the single source of truth, mirroring the bfabric XML dropdown). Each spec
# carries version/tag/dockerfile/slug; see deploy.load_diann_build_matrix().
DIANN_MATRIX = load_diann_build_matrix()
DIANN_BY_SLUG = {m["slug"]: m for m in DIANN_MATRIX}
DIANN_SLUGS = list(DIANN_BY_SLUG)

# Constrain the {slug} wildcard to known DIA-NN slugs so the wildcarded
# build/SIF rules never capture the thermorawfileparser/pwiz/prolfquapp flags.
wildcard_constraints:
    slug = "|".join(re.escape(s) for s in DIANN_SLUGS)

# SIF output directory (used by all_sif), from the deploy: block — the shared
# FGCZ apptainer cache, where the runtime workflow also reads SIFs from.
# Override with --config sif_output_dir=... for a one-off build elsewhere.
SIF_DIR = Path(config.get("sif_output_dir", DEPLOY["sif_output_dir"]))

# SIF builder: "native" (apptainer build from spython-generated .def, no
# docker needed) or "docker" (converts locally-built docker images via
# docker-daemon://, requires docker daemon + apptainer). From the deploy: block.
SIF_BUILDER = config.get("sif_builder", DEPLOY["sif_builder"])
if SIF_BUILDER not in ("docker", "native"):
    raise ValueError(
        f"sif_builder must be 'docker' or 'native', got {SIF_BUILDER!r}"
    )

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

    Two builders are available, selected by ``--config sif_builder=...``:

    - ``native`` (default): build directly with ``apptainer build`` from
      .def files generated from the Dockerfiles via spython. No docker
      needed. Works on hosts that have apptainer only.

    - ``docker``: convert locally-built docker images to SIF via
      ``docker-daemon://``. Requires both docker (daemon running) and
      apptainer on the host running this rule.

    Upstream images (msconvert, prolfquapp) are always pulled via
    ``docker://`` — same in both modes.
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


rule build_diann_image:
    """Build one DIA-NN Docker image.

    Version and tag come from the build matrix (the diann_images config map);
    all versions share the one .NET 8 Dockerfile, which gives native Thermo
    .raw support across the board.
    """
    input:
        dockerfile = lambda wc: DIANN_BY_SLUG[wc.slug]["dockerfile"],
        prereq_flag = FLAGS_DIR / "prerequisites_checked.flag"
    output:
        flag = FLAGS_DIR / "{slug}_built.flag"
    log:
        LOGS_DIR / "build_{slug}.log"
    params:
        force_rebuild = FORCE_REBUILD,
        tag = lambda wc: DIANN_BY_SLUG[wc.slug]["tag"],
        version = lambda wc: DIANN_BY_SLUG[wc.slug]["version"]
    shell:
        """
        TAG="{params.tag}"
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
        expand(str(FLAGS_DIR / "{slug}_built.flag"), slug=DIANN_SLUGS),
        FLAGS_DIR / "thermorawfileparser_docker_built.flag"
    output:
        flag = FLAGS_DIR / "deployment_complete.flag"
    run:
        print_deployment_complete(output_flag=Path(output.flag))


################################################################################
# SIF (Apptainer) Rules
################################################################################

rule check_apptainer_prerequisites:
    """Verify apptainer (and docker daemon, when sif_builder=docker) are
    available for SIF building. Used by docker-daemon:// build rules.
    """
    output:
        flag = FLAGS_DIR / "apptainer_prereq_checked.flag"
    run:
        check_apptainer_prerequisites(output_flag=Path(output.flag))


# Docker-daemon builders — only registered when sif_builder=docker.
if SIF_BUILDER == "docker":

    rule build_diann_sif:
        """Convert each diann:<version> docker image to SIF via docker-daemon://."""
        input:
            prereq_flag = FLAGS_DIR / "apptainer_prereq_checked.flag",
            docker_flag = FLAGS_DIR / "{slug}_built.flag"
        output:
            sif = SIF_DIR / "{slug}.sif"
        log:
            LOGS_DIR / "build_{slug}_sif.log"
        params:
            tag = lambda wc: DIANN_BY_SLUG[wc.slug]["tag"]
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
    """Pull the upstream msconvert (pwiz) image from Docker Hub.

    Uses the apptainer-only prereq check — pulling doesn't need docker,
    so this works for both all_sif (docker-host) and all_sif_native
    (apptainer-host-only) flows.
    """
    input:
        prereq_flag = FLAGS_DIR / "apptainer_only_prereq_checked.flag"
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
        prereq_flag = FLAGS_DIR / "apptainer_only_prereq_checked.flag"
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
        expand(str(SIF_DIR / "{slug}.sif"), slug=DIANN_SLUGS),
        SIF_DIR / f"thermorawfileparser_{THERMORAW_VERSION}.sif",
        SIF_DIR / "pwiz.sif",
        SIF_DIR / f"prolfquapp_{PROLFQUAPP_VERSION}.sif"
    output:
        flag = FLAGS_DIR / "sif_deployment_complete.flag"
    run:
        print_sif_deployment_complete(output_flag=Path(output.flag), sif_dir=SIF_DIR)


################################################################################
# Native SIF rules — only registered when sif_builder=native.
# Generated .def files live under build/ (gitignored). Always regenerated
# from the Dockerfile via spython — single source of truth, no drift risk.
################################################################################

DEF_DIR = BASE_DIR / "build"


rule check_apptainer_only_prerequisites:
    """Verify apptainer is on PATH (docker not required). Used by both
    the pull rules and the native-builder rules.
    """
    output:
        flag = FLAGS_DIR / "apptainer_only_prereq_checked.flag"
    shell:
        """
        if ! command -v apptainer >/dev/null 2>&1; then
            echo "ERROR: apptainer not found on PATH" >&2
            exit 1
        fi
        apptainer --version
        touch {output.flag:q}
        """


if SIF_BUILDER == "native":

    rule generate_diann_def:
        """Convert the DIA-NN Dockerfile to a .def file with DIANN_VERSION pinned.

        One per build-matrix entry; all versions share the single
        Dockerfile.diann, with the version resolved from the {slug} wildcard.
        """
        input:
            dockerfile = lambda wc: DIANN_BY_SLUG[wc.slug]["dockerfile"]
        output:
            deffile = DEF_DIR / "{slug}.def"
        params:
            version = lambda wc: DIANN_BY_SLUG[wc.slug]["version"]
        run:
            generate_def_from_dockerfile(
                Path(input.dockerfile),
                Path(output.deffile),
                overrides={"DIANN_VERSION": params.version},
            )

    rule generate_thermorawfileparser_def:
        """Convert Dockerfile.thermorawfileparser-linux to a .def file."""
        input:
            dockerfile = "docker/Dockerfile.thermorawfileparser-linux"
        output:
            deffile = DEF_DIR / f"thermorawfileparser_{THERMORAW_VERSION}.def"
        run:
            # No ARG to override — Dockerfile hardcodes 2.0.0-dev.
            generate_def_from_dockerfile(
                Path(input.dockerfile),
                Path(output.deffile),
            )

    rule build_diann_sif:
        """Build each diann SIF natively from its generated .def file (no docker)."""
        input:
            prereq_flag = FLAGS_DIR / "apptainer_only_prereq_checked.flag",
            deffile = DEF_DIR / "{slug}.def"
        output:
            sif = SIF_DIR / "{slug}.sif"
        log:
            LOGS_DIR / "build_{slug}_sif.log"
        shell:
            """
            mkdir -p "$(dirname {output.sif:q})"
            apptainer build --force {output.sif:q} {input.deffile:q} 2>&1 | tee {log:q}
            """

    rule build_thermorawfileparser_sif:
        """Build ThermoRawFileParser SIF natively from generated .def file."""
        input:
            prereq_flag = FLAGS_DIR / "apptainer_only_prereq_checked.flag",
            deffile = DEF_DIR / f"thermorawfileparser_{THERMORAW_VERSION}.def"
        output:
            sif = SIF_DIR / f"thermorawfileparser_{THERMORAW_VERSION}.sif"
        log:
            LOGS_DIR / "build_thermorawfileparser_sif.log"
        shell:
            """
            mkdir -p "$(dirname {output.sif:q})"
            apptainer build --force {output.sif:q} {input.deffile:q} 2>&1 | tee {log:q}
            """


################################################################################
# Utility Rules
################################################################################

rule check_images:
    """Check if required Docker images are available."""
    run:
        check_docker_images()


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
        diann_tags = " ".join(m["tag"] for m in DIANN_MATRIX)
    shell:
        """
        echo "This will remove:"
        echo "  - Deployment flags (.deploy_flags/)"
        echo "  - Docker images ({params.diann_tags}, thermorawfileparser:2.0.0)"
        echo ""
        read -p "Continue? [y/N]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf {params.flags_dir:q}
            for tag in {params.diann_tags}; do
                docker rmi "$tag" 2>/dev/null || true
            done
            docker rmi thermorawfileparser:2.0.0 2>/dev/null || true
            echo "Done"
        else
            echo "Cancelled"
        fi
        """
