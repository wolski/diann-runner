#!/usr/bin/env python3
"""
prolfquapp_docker.py — Run prolfquapp/prolfqua tools inside Docker.

Usage:
  prolfquapp-docker [--image-version VERSION] <command> [args...]

Examples:
  prolfquapp-docker prolfqua_qc.sh --indir out-DIANN -s DIANN ...
  prolfquapp-docker --image-version 0.1.8 prolfqua_qc.sh ...

Note: Use relative paths or run from your data directory.
      Current directory is mounted to /work in the container.

Env vars:
  PROLFQUAPP_IMAGE_VERSION   (default: "0.1.8")
  PROLFQUAPP_IMAGE_REPO      (default: "docker.io/prolfqua/prolfquapp")
  PROLFQUAPP_EXTRA           (optional: extra docker run args)
"""

import os
import sys
import shlex
import subprocess

# --- Settings ---
DEFAULT_VERSION = os.environ.get("PROLFQUAPP_IMAGE_VERSION", "2.0.7")
DEFAULT_REPO = os.environ.get("PROLFQUAPP_IMAGE_REPO", "docker.io/prolfqua/prolfquapp")
EXTRA_ARGS = shlex.split(os.environ.get("PROLFQUAPP_EXTRA", ""))

def detect_platform_arg() -> list[str]:
    # prolfquapp is R-based, works on both x86_64 and ARM architectures
    return []

def uid_gid_args() -> list[str]:
    try:
        uid = os.getuid()
        gid = os.getgid()
        return ["--user", f"{uid}:{gid}"]
    except AttributeError:
        return []  # Windows doesn't have getuid

def check_docker_available() -> str:
    """Check if podman or docker is available, return the command."""
    if subprocess.run(["which", "podman"], capture_output=True).returncode == 0:
        return "podman"
    elif subprocess.run(["which", "docker"], capture_output=True).returncode == 0:
        return "docker"
    else:
        raise FileNotFoundError("Neither docker nor podman found. Please install Docker Desktop.")

def build_docker_cmd(image_version: str, image_repo: str, argv: list[str]) -> list[str]:
    docker_cmd = check_docker_available()
    image = f"{image_repo}:{image_version}"

    cmd = [docker_cmd, "run", "--rm"]

    # Add TTY if stdin is a terminal
    if sys.stdin.isatty():
        cmd.append("-it")
    else:
        cmd.append("-i")

    # Add user/group for file permissions
    cmd += uid_gid_args()

    # Mount current directory to /work
    cmd += ["--mount", f"type=bind,source={os.getcwd()},target=/work"]
    cmd += ["-w", "/work"]

    if EXTRA_ARGS:
        cmd += EXTRA_ARGS

    cmd += [image]
    cmd += argv

    return cmd

def main():
    if len(sys.argv) == 1:
        print(__doc__)
        sys.exit(2)

    # Parse arguments
    image_version = DEFAULT_VERSION
    image_repo = DEFAULT_REPO
    container_args = []

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--image-version" and i + 1 < len(sys.argv):
            image_version = sys.argv[i + 1]
            i += 2
        elif arg == "--image-repo" and i + 1 < len(sys.argv):
            image_repo = sys.argv[i + 1]
            i += 2
        elif arg == "--help":
            print(__doc__)
            sys.exit(0)
        else:
            container_args = sys.argv[i:]
            break

    if not container_args:
        print("Error: No command specified", file=sys.stderr)
        print(__doc__)
        sys.exit(2)

    docker_cmd = build_docker_cmd(image_version, image_repo, container_args)

    # Pretty print the command for debugging
    print(f"→ Running: {' '.join(shlex.quote(x) for x in docker_cmd)}", file=sys.stderr)

    try:
        completed = subprocess.run(docker_cmd)
        sys.exit(completed.returncode)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(127)

if __name__ == "__main__":
    main()
