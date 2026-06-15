"""
container_utils.py — Runtime-agnostic container command construction.

Replaces the older docker_utils.py. Builds `docker run …` or
`apptainer exec …` invocations from the same fluent API.

Runtime is selected by what is installed on the host
(`detect_runtime()` — apptainer wins if both are present).
"""

from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess
import sys
from typing import Literal

Runtime = Literal["docker", "apptainer"]


def is_apple_silicon() -> bool:
    """Check if running on Apple Silicon."""
    m = platform.machine().lower()
    return "arm" in m or "aarch64" in m


def detect_runtime() -> Runtime:
    """Select container runtime based on what is installed on the host.

    Apptainer wins when both are present — a host that has apptainer
    installed is one that should be using it. Production hosts will have
    exactly one.
    """
    if shutil.which("apptainer"):
        return "apptainer"
    if shutil.which("docker"):
        return "docker"
    raise RuntimeError(
        "No container runtime found: neither apptainer nor docker is on PATH."
    )


def find_docker_runtime() -> str:
    """Return `podman` or `docker` (in that order) if either is available."""
    for runtime in ("podman", "docker"):
        if shutil.which(runtime):
            return runtime
    raise FileNotFoundError(
        "Neither docker nor podman found. Please install Docker Desktop."
    )


def print_command(cmd: list[str], label: str = "Running", file=sys.stderr) -> None:
    quoted = " ".join(shlex.quote(x) for x in cmd)
    print(f"→ {label}: {quoted}", file=file)


def run_container(
    cmd: list[str],
    print_cmd: bool = True,
    label: str = "Running",
) -> int:
    if print_cmd:
        print_command(cmd, label)
    return subprocess.run(cmd).returncode


class ContainerCommandBuilder:
    """Build a container invocation for either docker or apptainer.

    Methods that don't apply to the selected runtime are no-ops, so the
    same fluent chain works for both runtimes.
    """

    def __init__(self, image: str, runtime: Runtime = "docker"):
        if runtime not in ("docker", "apptainer"):
            raise ValueError(
                f"Unknown runtime {runtime!r}; expected 'docker' or 'apptainer'."
            )
        self.image = image
        self.runtime = runtime
        self._docker_args: list[str] = []
        self._apptainer_args: list[str] = []
        self._apptainer_use_exec: bool = False
        if runtime == "docker":
            self._executable = find_docker_runtime()
        else:
            self._executable = "apptainer"

    def with_cleanup(self) -> "ContainerCommandBuilder":
        if self.runtime == "docker":
            self._docker_args.append("--rm")
        return self

    def with_init(self) -> "ContainerCommandBuilder":
        if self.runtime == "docker":
            self._docker_args.append("--init")
        return self

    def with_interactive(self, tty: bool = True) -> "ContainerCommandBuilder":
        if self.runtime != "docker":
            return self
        if tty and sys.stdin.isatty():
            self._docker_args.append("-it")
        else:
            self._docker_args.append("-i")
        return self

    def with_platform(
        self, force_amd64_on_arm: bool = True, override: str = ""
    ) -> "ContainerCommandBuilder":
        if self.runtime != "docker":
            return self
        if override:
            self._docker_args.extend(["--platform", override])
        elif force_amd64_on_arm and is_apple_silicon():
            self._docker_args.extend(["--platform", "linux/amd64"])
        return self

    def with_uid_gid(self, flag: str = "-u") -> "ContainerCommandBuilder":
        if self.runtime != "docker":
            return self
        try:
            self._docker_args.extend([flag, f"{os.getuid()}:{os.getgid()}"])
        except AttributeError:
            pass
        return self

    def with_mount(
        self,
        source: str,
        target: str,
        style: str = "volume",
        read_only: bool = False,
    ) -> "ContainerCommandBuilder":
        """Bind-mount a host path into the container.

        Call multiple times to add multiple mounts (e.g. a writable work dir
        plus a read-only raw-file dir). ``read_only=True`` mounts the path
        read-only, which is appropriate for shared input directories the
        container must not modify (e.g. an external raw-file dir).
        """
        if self.runtime == "apptainer":
            bind = f"{source}:{target}:ro" if read_only else f"{source}:{target}"
            self._apptainer_args.extend(["--bind", bind])
            return self
        if style == "bind":
            spec = f"type=bind,source={source},target={target}"
            if read_only:
                spec += ",readonly"
            self._docker_args.extend(["--mount", spec])
        else:
            spec = f"{source}:{target}:ro" if read_only else f"{source}:{target}"
            self._docker_args.extend(["-v", spec])
        return self

    def with_workdir(self, path: str) -> "ContainerCommandBuilder":
        if self.runtime == "apptainer":
            self._apptainer_args.extend(["--pwd", path])
        else:
            self._docker_args.extend(["-w", path])
        return self

    def with_extra_args(self, args: list[str]) -> "ContainerCommandBuilder":
        if self.runtime == "apptainer":
            self._apptainer_args.extend(args)
        else:
            self._docker_args.extend(args)
        return self

    def with_resource_limits(
        self,
        shm_size: str = "2g",
        nofile_limit: int = 1048576,
        ipc_host: bool = True,
    ) -> "ContainerCommandBuilder":
        if self.runtime != "docker":
            return self
        self._docker_args.extend(["--shm-size", shm_size])
        self._docker_args.extend(["--ulimit", f"nofile={nofile_limit}:{nofile_limit}"])
        if ipc_host:
            self._docker_args.extend(["--ipc", "host"])
        return self

    def with_wine_compat(self, wineprefix: str = "/tmp/.wine") -> "ContainerCommandBuilder":
        """Enable Wine inside an Apptainer image with a read-only FS.

        Wine needs a writable `$WINEPREFIX`. Docker provides it via the
        writable container layer; Apptainer mounts the image read-only by
        default, so without help Wine fails at prefix initialisation.

        No-op under Docker.
        """
        if self.runtime != "apptainer":
            return self
        self._apptainer_args.append("--writable-tmpfs")
        self._apptainer_args.extend(["--env", f"WINEPREFIX={wineprefix}"])
        return self

    def with_explicit_command(self) -> "ContainerCommandBuilder":
        """Use `apptainer exec` (caller supplies the binary as the first arg)
        instead of the default `apptainer run` (image runscript decides).

        Needed when the caller wants to override the image's runscript —
        e.g. msconvert is invoked via `sh -c "wine msconvert ..."` to set
        Wine env vars, which would conflict with the pwiz runscript that
        unconditionally executes `wine64_anyuser msconvert`.

        No-op under Docker (docker run already overrides CMD with args).
        """
        if self.runtime == "apptainer":
            self._apptainer_use_exec = True
        return self

    def build(self, container_args: list[str]) -> list[str]:
        if self.runtime == "apptainer":
            # Default: `apptainer run` so the image's runscript is invoked
            # (mirrors docker's ENTRYPOINT semantics). Opt into `exec` via
            # with_explicit_command() when the caller passes its own binary
            # as container_args[0].
            verb = "exec" if self._apptainer_use_exec else "run"
            return [self._executable, verb, *self._apptainer_args, self.image, *container_args]
        return [self._executable, "run", *self._docker_args, self.image, *container_args]
