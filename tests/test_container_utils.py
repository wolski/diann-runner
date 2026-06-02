"""Tests for ContainerCommandBuilder and runtime detection."""

import os
import unittest
from unittest.mock import patch

from diann_runner.container_utils import (
    ContainerCommandBuilder,
    detect_runtime,
)


def _has_uid() -> bool:
    return hasattr(os, "getuid")


class TestContainerCommandBuilderDocker(unittest.TestCase):
    """Docker output should match historical behaviour."""

    @patch("diann_runner.container_utils.find_docker_runtime", return_value="docker")
    def test_basic_docker_invocation_shape(self, _):
        cmd = ContainerCommandBuilder("diann:2.3.2", runtime="docker").build(["--help"])
        self.assertEqual(cmd[0], "docker")
        self.assertEqual(cmd[1], "run")
        self.assertEqual(cmd[-2], "diann:2.3.2")
        self.assertEqual(cmd[-1], "--help")

    @patch("diann_runner.container_utils.find_docker_runtime", return_value="docker")
    def test_docker_emits_full_flag_set(self, _):
        cmd = (
            ContainerCommandBuilder("diann:2.3.2", runtime="docker")
            .with_cleanup()
            .with_init()
            .with_mount("/host", "/work")
            .with_workdir("/work")
            .build(["--help"])
        )
        self.assertIn("--rm", cmd)
        self.assertIn("--init", cmd)
        self.assertIn("-v", cmd)
        self.assertIn("/host:/work", cmd)
        self.assertIn("-w", cmd)

    @patch("diann_runner.container_utils.find_docker_runtime", return_value="docker")
    def test_docker_resource_limits_emitted(self, _):
        cmd = (
            ContainerCommandBuilder("diann:2.3.2", runtime="docker")
            .with_resource_limits()
            .build(["x"])
        )
        self.assertIn("--shm-size", cmd)
        self.assertIn("2g", cmd)
        self.assertIn("--ulimit", cmd)
        self.assertIn("--ipc", cmd)
        self.assertIn("host", cmd)

    @patch("diann_runner.container_utils.find_docker_runtime", return_value="docker")
    @patch("diann_runner.container_utils.is_apple_silicon", return_value=True)
    def test_docker_platform_forced_on_apple_silicon(self, *_):
        cmd = (
            ContainerCommandBuilder("img", runtime="docker")
            .with_platform()
            .build([])
        )
        self.assertIn("--platform", cmd)
        self.assertIn("linux/amd64", cmd)


class TestContainerCommandBuilderApptainer(unittest.TestCase):
    """Apptainer output should drop Docker-only flags and use apptainer syntax."""

    def test_basic_apptainer_invocation_shape(self):
        cmd = ContainerCommandBuilder("/opt/sif/diann.sif", runtime="apptainer").build(["--help"])
        self.assertEqual(cmd[0], "apptainer")
        self.assertEqual(cmd[1], "run")
        self.assertEqual(cmd[-2], "/opt/sif/diann.sif")
        self.assertEqual(cmd[-1], "--help")

    def test_apptainer_explicit_command_uses_exec(self):
        cmd = (
            ContainerCommandBuilder("/opt/sif/pwiz.sif", runtime="apptainer")
            .with_explicit_command()
            .build(["sh", "-c", "echo hi"])
        )
        self.assertEqual(cmd[1], "exec")

    def test_apptainer_mount_uses_bind(self):
        cmd = (
            ContainerCommandBuilder("/opt/sif/diann.sif", runtime="apptainer")
            .with_mount("/host", "/work")
            .with_workdir("/work")
            .build(["x"])
        )
        self.assertIn("--bind", cmd)
        self.assertIn("/host:/work", cmd)
        self.assertIn("--pwd", cmd)
        self.assertIn("/work", cmd)

    def test_apptainer_omits_docker_only_flags(self):
        cmd = (
            ContainerCommandBuilder("/opt/sif/diann.sif", runtime="apptainer")
            .with_cleanup()
            .with_init()
            .with_platform(force_amd64_on_arm=True)
            .with_uid_gid()
            .with_resource_limits()
            .build(["x"])
        )
        for forbidden in (
            "--rm",
            "--init",
            "--platform",
            "-u",
            "--user",
            "--shm-size",
            "--ulimit",
            "--ipc",
        ):
            self.assertNotIn(forbidden, cmd, f"Apptainer command must not contain {forbidden!r}")

    def test_wine_compat_only_emitted_under_apptainer(self):
        apptainer_cmd = (
            ContainerCommandBuilder("/opt/sif/pwiz.sif", runtime="apptainer")
            .with_wine_compat()
            .build([])
        )
        self.assertIn("--writable-tmpfs", apptainer_cmd)
        self.assertIn("--env", apptainer_cmd)
        self.assertTrue(any("WINEPREFIX=" in arg for arg in apptainer_cmd))

    @patch("diann_runner.container_utils.find_docker_runtime", return_value="docker")
    def test_wine_compat_is_noop_under_docker(self, _):
        docker_cmd = (
            ContainerCommandBuilder("img", runtime="docker")
            .with_wine_compat()
            .build([])
        )
        self.assertNotIn("--writable-tmpfs", docker_cmd)


class TestDetectRuntime(unittest.TestCase):
    def test_apptainer_wins_when_both_installed(self):
        def both_installed(name):
            return {"apptainer": "/usr/bin/apptainer", "docker": "/usr/bin/docker"}.get(name)

        with patch("diann_runner.container_utils.shutil.which", side_effect=both_installed):
            self.assertEqual(detect_runtime(), "apptainer")

    def test_docker_when_only_docker(self):
        def only_docker(name):
            return "/usr/bin/docker" if name == "docker" else None

        with patch("diann_runner.container_utils.shutil.which", side_effect=only_docker):
            self.assertEqual(detect_runtime(), "docker")

    def test_apptainer_when_only_apptainer(self):
        def only_apptainer(name):
            return "/usr/bin/apptainer" if name == "apptainer" else None

        with patch("diann_runner.container_utils.shutil.which", side_effect=only_apptainer):
            self.assertEqual(detect_runtime(), "apptainer")

    def test_raises_when_neither_installed(self):
        with patch("diann_runner.container_utils.shutil.which", return_value=None):
            with self.assertRaises(RuntimeError):
                detect_runtime()


class TestRejectsUnknownRuntime(unittest.TestCase):
    def test_unknown_runtime_raises(self):
        with self.assertRaises(ValueError):
            ContainerCommandBuilder("img", runtime="podman")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
