"""
docker_utils.py — Shared utilities for Docker wrapper scripts.

Common functionality for running containerized tools with consistent
behavior across different wrappers.
"""

import os
import platform
import shlex
import shutil
import subprocess
import sys


def is_apple_silicon() -> bool:
    """Check if running on Apple Silicon."""
    m = platform.machine().lower()
    return "arm" in m or "aarch64" in m


def get_uid_gid_args(flag: str = "-u") -> list[str]:
    """
    Get UID/GID arguments for Docker to preserve file ownership.

    Args:
        flag: The flag to use ("-u" for docker, "--user" also works)

    Returns:
        List like ["-u", "1000:1000"] or empty list on Windows.
    """
    try:
        return [flag, f"{os.getuid()}:{os.getgid()}"]
    except AttributeError:
        return []  # Windows doesn't have getuid


def get_platform_args(force_amd64_on_arm: bool = True, override: str = "") -> list[str]:
    """
    Get platform arguments for Docker.

    Args:
        force_amd64_on_arm: If True, force linux/amd64 on Apple Silicon
        override: Explicit platform override (takes precedence)

    Returns:
        List like ["--platform", "linux/amd64"] or empty list.
    """
    if override:
        return ["--platform", override]
    if force_amd64_on_arm and is_apple_silicon():
        return ["--platform", "linux/amd64"]
    return []


def find_container_runtime() -> str:
    """
    Find available container runtime (podman or docker).

    Returns:
        "podman" or "docker"

    Raises:
        FileNotFoundError: If neither is found.
    """
    for runtime in ("podman", "docker"):
        if shutil.which(runtime):
            return runtime
    raise FileNotFoundError(
        "Neither docker nor podman found. Please install Docker Desktop."
    )


def print_command(cmd: list[str], label: str = "Running", file=sys.stderr) -> None:
    """Print a command in a readable format."""
    quoted = " ".join(shlex.quote(x) for x in cmd)
    print(f"→ {label}: {quoted}", file=file)


def run_container(
    cmd: list[str],
    print_cmd: bool = True,
    label: str = "Running",
) -> int:
    """
    Run a container command and return the exit code.

    Args:
        cmd: Full docker/podman command to run
        print_cmd: Whether to print the command before running
        label: Label for the printed command

    Returns:
        Process return code
    """
    if print_cmd:
        print_command(cmd, label)

    result = subprocess.run(cmd)
    return result.returncode


class DockerCommandBuilder:
    """Builder for Docker run commands with common options."""

    def __init__(self, image: str, runtime: str | None = None):
        """
        Initialize the builder.

        Args:
            image: Docker image name with tag
            runtime: "docker" or "podman" (auto-detected if None)
        """
        self.image = image
        self.runtime = runtime or find_container_runtime()
        self._args: list[str] = []

    def with_cleanup(self) -> "DockerCommandBuilder":
        """Add --rm flag to remove container after exit."""
        self._args.append("--rm")
        return self

    def with_interactive(self, tty: bool = True) -> "DockerCommandBuilder":
        """Add interactive flags (-it or -i)."""
        if tty and sys.stdin.isatty():
            self._args.append("-it")
        else:
            self._args.append("-i")
        return self

    def with_platform(
        self, force_amd64_on_arm: bool = True, override: str = ""
    ) -> "DockerCommandBuilder":
        """Add platform argument if needed."""
        self._args.extend(get_platform_args(force_amd64_on_arm, override))
        return self

    def with_uid_gid(self, flag: str = "-u") -> "DockerCommandBuilder":
        """Add user/group mapping for file permissions."""
        self._args.extend(get_uid_gid_args(flag))
        return self

    def with_mount(
        self,
        source: str,
        target: str,
        style: str = "volume",
    ) -> "DockerCommandBuilder":
        """
        Mount a directory into the container.

        Args:
            source: Host path (absolute)
            target: Container path
            style: "volume" for -v syntax, "bind" for --mount syntax
        """
        if style == "bind":
            self._args.extend(["--mount", f"type=bind,source={source},target={target}"])
        else:
            self._args.extend(["-v", f"{source}:{target}"])
        return self

    def with_workdir(self, path: str) -> "DockerCommandBuilder":
        """Set the working directory inside the container."""
        self._args.extend(["-w", path])
        return self

    def with_extra_args(self, args: list[str]) -> "DockerCommandBuilder":
        """Add arbitrary extra arguments."""
        self._args.extend(args)
        return self

    def with_resource_limits(
        self,
        shm_size: str = "2g",
        nofile_limit: int = 1048576,
        ipc_host: bool = True,
    ) -> "DockerCommandBuilder":
        """Add resource limit settings for large workloads."""
        self._args.extend(["--shm-size", shm_size])
        self._args.extend(["--ulimit", f"nofile={nofile_limit}:{nofile_limit}"])
        if ipc_host:
            self._args.extend(["--ipc", "host"])
        return self

    def build(self, container_args: list[str]) -> list[str]:
        """
        Build the complete docker run command.

        Args:
            container_args: Arguments to pass to the container entrypoint

        Returns:
            Complete command as a list of strings
        """
        cmd = [self.runtime, "run"] + self._args + [self.image] + container_args
        return cmd
