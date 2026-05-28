"""Helper functions for deploy.smk"""

import re
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


def check_docker_images(
    diann_version: str = "2.3.2",
    diann_thermo_version: str = "2.5.0",
) -> None:
    """
    Check if required Docker images are available.

    Args:
        diann_version: DIA-NN version to check for
        diann_thermo_version: DIA-NN version for the native Thermo image
    """
    print("=" * 60)
    print("Checking Docker Images")
    print("=" * 60)

    thermo_tag = f"diann:{diann_thermo_version}-thermo"
    images_to_check = [
        (f"diann:{diann_version}", f"diann:{diann_version}"),
        (thermo_tag, thermo_tag),
        ("thermorawfileparser:2.0.0", "thermorawfileparser:2.0.0"),
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


def check_apptainer_prerequisites(output_flag: Path) -> None:
    """Verify apptainer (and docker, for docker-daemon:// pulls) are available.

    The SIF build path needs:
    - apptainer on PATH (to run `apptainer pull`)
    - docker on PATH and the daemon running (to satisfy `docker-daemon://`
      pulls for locally-built images: diann, thermorawfileparser)

    Upstream-only pulls (msconvert, prolfquapp) only need apptainer, but
    a typical SIF build run needs both — we check for both here.
    """
    print("=" * 60)
    print("Checking Apptainer Prerequisites")
    print("=" * 60)

    all_good = True

    if check_command("apptainer"):
        result = subprocess.run(["apptainer", "--version"], capture_output=True, text=True)
        print(f"✓ {result.stdout.strip()}")
    else:
        print("✗ apptainer not found on PATH")
        all_good = False

    if check_command("docker"):
        result = subprocess.run(["docker", "ps"], capture_output=True)
        if result.returncode == 0:
            print("✓ Docker daemon is running (needed for docker-daemon:// pulls)")
        else:
            print("✗ Docker daemon not running — docker-daemon:// pulls will fail")
            all_good = False
    else:
        print("✗ docker not found — docker-daemon:// pulls will fail")
        all_good = False

    print("=" * 60)

    if not all_good:
        print("\n✗ Apptainer prerequisites check failed!")
        sys.exit(1)

    print("✓ Apptainer prerequisites OK\n")
    output_flag.touch()


def generate_def_from_dockerfile(
    dockerfile: Path,
    output_def: Path,
    overrides: dict[str, str] | None = None,
) -> None:
    """Convert a Dockerfile to an apptainer .def file via spython.

    spython turns Dockerfile ARGs into plain shell assignments in the %post
    section, baking in their default values. To build a non-default version
    we post-process the generated .def and override the relevant
    assignment(s).

    Args:
        dockerfile: Path to the source Dockerfile.
        output_def: Destination .def path (parent dir is created if needed).
        overrides: Optional {var: value} map. For each entry, the first
            line matching ``^<var>=.*$`` in the generated .def is replaced
            with ``<var>=<value>``. Use this to pin DIANN_VERSION etc.
    """
    from spython.main.parse.parsers import DockerParser
    from spython.main.parse.writers import SingularityWriter

    parser = DockerParser(str(dockerfile))
    writer = SingularityWriter(parser.recipe)
    content = writer.convert()

    for var, value in (overrides or {}).items():
        content, count = re.subn(
            rf"^{re.escape(var)}=.*$",
            f"{var}={value}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
        if count == 0:
            raise RuntimeError(
                f"Override variable {var!r} not found in .def generated from "
                f"{dockerfile} (looked for line starting with '{var}=')."
            )

    output_def.parent.mkdir(parents=True, exist_ok=True)
    output_def.write_text(content)


def print_sif_deployment_complete(output_flag: Path, sif_dir: Path) -> None:
    """Print final SIF deployment summary."""
    print("\n" + "=" * 60)
    print("SIF Images Built")
    print("=" * 60)

    if sif_dir.exists():
        for sif in sorted(sif_dir.glob("*.sif")):
            size_mb = sif.stat().st_size / (1024 * 1024)
            print(f"  {sif.name}  ({size_mb:.1f} MB)")

    print("=" * 60)
    print(f"\nSIFs are in: {sif_dir.resolve()}")
    print("Next: copy them to /opt/sif/ on the apptainer host:")
    print(f"  rsync -av {sif_dir}/ <apptainer-host>:/opt/sif/")
    print("=" * 60 + "\n")

    output_flag.touch()


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
