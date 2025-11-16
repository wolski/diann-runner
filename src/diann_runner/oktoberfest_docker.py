#!/usr/bin/env python3
"""
oktoberfest_docker.py — Run Oktoberfest inside Docker.

Usage:
  python oktoberfest_docker.py <Oktoberfest args>

Note: Use relative paths or run from your data directory.
      Current directory is mounted to /work in the container.

Env vars:
  OKTOBERFEST_DOCKER_IMAGE   (default: "oktoberfest:latest")
  OKTOBERFEST_IMAGE_REPO     (optional: e.g., "ghcr.io/wilhelm-lab/oktoberfest")
  OKTOBERFEST_IMAGE_VERSION  (optional: default "latest")
  OKTOBERFEST_PLATFORM       (optional: override docker --platform)
  OKTOBERFEST_EXTRA          (optional: extra docker run args)
"""

import os
import sys
import shlex
import subprocess
import platform

# --- Settings ---
# Support both direct image name and repo+version pattern (like prolfqua_docker)
IMAGE_REPO = os.environ.get("OKTOBERFEST_IMAGE_REPO", "")
IMAGE_VERSION = os.environ.get("OKTOBERFEST_IMAGE_VERSION", "latest")

if IMAGE_REPO:
    DEFAULT_IMAGE = f"{IMAGE_REPO}:{IMAGE_VERSION}"
else:
    DEFAULT_IMAGE = os.environ.get("OKTOBERFEST_DOCKER_IMAGE", "oktoberfest:latest")

PLATFORM_OVERRIDE = os.environ.get("OKTOBERFEST_PLATFORM", "")
EXTRA_ARGS = shlex.split(os.environ.get("OKTOBERFEST_EXTRA", ""))

# Dockerfile URL for fallback build
DOCKERFILE_URL = "https://raw.githubusercontent.com/wilhelm-lab/oktoberfest/development/Dockerfile"

def is_apple_silicon() -> bool:
    m = platform.machine().lower()
    return "arm" in m or "aarch64" in m

def detect_platform_arg() -> list[str]:
    if PLATFORM_OVERRIDE:
        return ["--platform", PLATFORM_OVERRIDE]
    if is_apple_silicon():
        return ["--platform", "linux/amd64"]
    return []

def uid_gid_args() -> list[str]:
    try:
        uid = os.getuid()
        gid = os.getgid()
        return ["-u", f"{uid}:{gid}"]
    except AttributeError:
        return []  # Windows doesn't have getuid

def image_exists(image_name: str) -> bool:
    """Check if a Docker image exists locally."""
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image_name],
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False

def try_pull_image(image_name: str) -> bool:
    """Try to pull the Docker image from a registry. Returns True if successful."""
    print(f"Image '{image_name}' not found locally. Attempting to pull...", file=sys.stderr)
    try:
        result = subprocess.run(
            ["docker", "pull", image_name],
            capture_output=False,  # Show pull progress
            check=False
        )
        if result.returncode == 0:
            print(f"✓ Successfully pulled '{image_name}'", file=sys.stderr)
            return True
        else:
            print(f"✗ Failed to pull '{image_name}' (exit code {result.returncode})", file=sys.stderr)
            return False
    except FileNotFoundError:
        return False

def build_from_dockerfile() -> bool:
    """Download Dockerfile and build image locally as fallback. Returns True if successful."""
    print(f"\nAttempting to build '{DEFAULT_IMAGE}' from Dockerfile...", file=sys.stderr)

    # Create temporary directory for build
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        dockerfile_path = os.path.join(tmpdir, "Dockerfile")

        # Download Dockerfile
        print(f"Downloading Dockerfile from {DOCKERFILE_URL}...", file=sys.stderr)
        try:
            result = subprocess.run(
                ["curl", "-fsSL", "-o", dockerfile_path, DOCKERFILE_URL],
                capture_output=True,
                check=False
            )
            if result.returncode != 0:
                print(f"✗ Failed to download Dockerfile", file=sys.stderr)
                return False
        except FileNotFoundError:
            print(f"✗ curl not found. Cannot download Dockerfile.", file=sys.stderr)
            return False

        # Build the image
        print(f"Building Docker image '{DEFAULT_IMAGE}'...", file=sys.stderr)
        print("This may take several minutes on first run.", file=sys.stderr)

        platform_args = detect_platform_arg()
        cmd = ["docker", "build"] + platform_args + ["-t", DEFAULT_IMAGE, "-f", dockerfile_path, tmpdir]

        result = subprocess.run(cmd, capture_output=False, check=False)
        if result.returncode == 0:
            print(f"✓ Successfully built '{DEFAULT_IMAGE}'", file=sys.stderr)
            return True
        else:
            print(f"✗ Failed to build image (exit code {result.returncode})", file=sys.stderr)
            return False

def ensure_image_exists():
    """Ensure Docker image exists: check local → pull from registry → build from Dockerfile."""
    # Check if image exists locally
    if image_exists(DEFAULT_IMAGE):
        print(f"Using Docker image: {DEFAULT_IMAGE}", file=sys.stderr)
        return

    # Try to pull from registry (if it looks like a registry image)
    if "/" in DEFAULT_IMAGE or DEFAULT_IMAGE.startswith("ghcr.io"):
        if try_pull_image(DEFAULT_IMAGE):
            return

    # Try to build from Dockerfile as fallback (only for local image names)
    if "/" not in DEFAULT_IMAGE:
        print(f"\nImage '{DEFAULT_IMAGE}' is a local name. Trying to build from Dockerfile...", file=sys.stderr)
        if build_from_dockerfile():
            return

    # All methods failed
    print(f"\n✗ Error: Could not obtain Docker image '{DEFAULT_IMAGE}'.", file=sys.stderr)
    print("\nOptions:", file=sys.stderr)
    print("  1. Use a public registry image (if available):", file=sys.stderr)
    print("     export OKTOBERFEST_IMAGE_REPO=ghcr.io/wilhelm-lab/oktoberfest", file=sys.stderr)
    print("     export OKTOBERFEST_IMAGE_VERSION=latest", file=sys.stderr)
    print("  2. Build manually from the oktoberfest repository:", file=sys.stderr)
    print("     git clone https://github.com/wilhelm-lab/oktoberfest.git", file=sys.stderr)
    print("     cd oktoberfest", file=sys.stderr)
    print("     docker build -t oktoberfest:latest .", file=sys.stderr)
    print("  3. Specify a custom image:", file=sys.stderr)
    print("     export OKTOBERFEST_DOCKER_IMAGE=your-custom-image:tag", file=sys.stderr)
    sys.exit(1)

def build_docker_cmd(argv: list[str]) -> list[str]:
    cmd = ["docker", "run", "--rm"]
    cmd += detect_platform_arg()
    # NOTE: Don't use uid_gid_args() because oktoberfest files are in /root
    # and non-root users can't read them

    # Mount current directory to /work
    cmd += ["-v", f"{os.getcwd()}:/work"]

    if EXTRA_ARGS:
        cmd += EXTRA_ARGS

    cmd += [DEFAULT_IMAGE]
    # Use bash to set PYTHONPATH, cd to /work, then run oktoberfest
    bash_cmd = "export PYTHONPATH=/root && cd /work && python -m oktoberfest " + " ".join(shlex.quote(arg) for arg in argv)
    cmd += ["bash", "-c", bash_cmd]
    return cmd

def main():
    if len(sys.argv) == 1:
        print("""Usage: python oktoberfest_docker.py <Oktoberfest arguments>

Example workflow:
  # Your directory structure:
  # ./config.json         (Oktoberfest configuration)
  # ./data/sample1.mzML
  # ./data/sample2.mzML
  # ./reference/uniprot.fasta
  # ./output/  (will be created)

  # Run Oktoberfest:
  python oktoberfest_docker.py -c config.json

  # Results will be in the output directory specified in config.json
""")
        sys.exit(2)

    # Ensure Docker image exists (pull or build if needed)
    ensure_image_exists()

    oktoberfest_args = sys.argv[1:]
    docker_cmd = build_docker_cmd(oktoberfest_args)

    # Pretty print the command for debugging
    print("→ Running:", " ".join(shlex.quote(x) for x in docker_cmd), file=sys.stderr)
    try:
        # Stream output directly
        completed = subprocess.run(docker_cmd)
        sys.exit(completed.returncode)
    except FileNotFoundError:
        print("Error: Docker not found. Please install Docker Desktop and ensure `docker` is on PATH.",
              file=sys.stderr)
        sys.exit(127)

if __name__ == "__main__":
    main()
