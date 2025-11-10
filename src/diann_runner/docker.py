#!/usr/bin/env python3
"""
diann_docker.py — Run DIA-NN inside Docker.

Usage:
  python diann_docker.py <DIA-NN args>
  
Note: Use relative paths or run from your data directory.
      Current directory is mounted to /work in the container.

Env vars:
  DIANN_DOCKER_IMAGE   (default: "diann:2.3.0")
  DIANN_PLATFORM       (optional: override docker --platform)
  DIANN_EXTRA          (optional: extra docker run args)
"""

import os
import sys
import shlex
import subprocess
import platform

# --- Settings ---
DEFAULT_IMAGE = os.environ.get("DIANN_DOCKER_IMAGE", "diann:2.3.0")
PLATFORM_OVERRIDE = os.environ.get("DIANN_PLATFORM", "")
EXTRA_ARGS = shlex.split(os.environ.get("DIANN_EXTRA", ""))

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

def build_docker_cmd(argv: list[str]) -> list[str]:
    cmd = ["docker", "run", "--rm"]
    cmd += detect_platform_arg()
    cmd += uid_gid_args()
    
    # Mount current directory to /work and set as working directory
    cmd += ["-v", f"{os.getcwd()}:/work", "-w", "/work"]
    
    # Defaults for large runs
    cmd += ["--shm-size", "2g", "--ulimit", "nofile=1048576:1048576", "--ipc", "host"]
    
    if EXTRA_ARGS:
        cmd += EXTRA_ARGS
    
    cmd += [DEFAULT_IMAGE]
    cmd += argv
    return cmd

def main():
    if len(sys.argv) == 1:
        print("""Usage: python diann_docker.py <DIA-NN arguments>

Example workflow:
  # Your directory structure:
  # ./data/sample1.mzML
  # ./data/sample2.mzML
  # ./reference/uniprot.fasta
  # ./output/  (will be created)
  
  # Run DIA-NN:
  python diann_docker.py \\
    --f data/sample1.mzML --f data/sample2.mzML \\
    --fasta reference/uniprot.fasta \\
    --out output/report.tsv \\
    --qvalue 0.01 --matrices
  
  # Results will be in ./output/report.tsv (and related files)
""")
        sys.exit(2)

    diann_args = sys.argv[1:]
    docker_cmd = build_docker_cmd(diann_args)

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
