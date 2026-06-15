"""Tests for reading raw files from an external, read-only mounted directory.

Covers the three pieces that let DIA-NN / thermoraw read raw files in place
(without copying them into the work dir):
- diann_docker --mount HOST:CONTAINER[:ro]
- DiannWorkflow.raw_mount → --mount in the generated invocation
- thermoraw _mount_io auto-mounting an external input at /raw
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from diann_runner.container_utils import ContainerCommandBuilder
from diann_runner.diann_docker import _parse_mount_spec, build_container_cmd
from diann_runner.thermoraw_docker import _mount_io
from diann_runner.workflow import DiannWorkflow


class TestParseMountSpec(unittest.TestCase):
    def test_rw_spec(self):
        self.assertEqual(_parse_mount_spec("/h:/c"), ("/h", "/c", False))

    def test_ro_spec(self):
        self.assertEqual(_parse_mount_spec("/srv/raw:/raw:ro"), ("/srv/raw", "/raw", True))

    def test_invalid_spec_raises(self):
        with self.assertRaises(ValueError):
            _parse_mount_spec("/only-one")


class TestDiannDockerExtraMount(unittest.TestCase):
    @patch("diann_runner.diann_docker.os.getcwd", return_value="/work/host")
    @patch("diann_runner.container_utils.find_docker_runtime", return_value="docker")
    def test_extra_read_only_mount_added(self, *_):
        cmd = build_container_cmd(
            ["--f", "/raw/s.raw"],
            image="diann:2.3.2",
            runtime="docker",
            platform_override="",
            mounts=("/srv/gstore/raw:/raw:ro",),
        )
        self.assertIn("/work/host:/work", cmd)
        self.assertIn("/srv/gstore/raw:/raw:ro", cmd)


class TestWorkflowRawMount(unittest.TestCase):
    def test_prefix_includes_mount_when_raw_mount_set(self):
        wf = DiannWorkflow(
            workunit_id="WU0",
            docker_image="diann:2.3.2",
            container_runtime="apptainer",
            raw_mount=("/srv/gstore/raw", "/raw"),
        )
        prefix = wf._diann_invocation_prefix()
        self.assertIn("--mount /srv/gstore/raw:/raw:ro", prefix)
        # mount flag must precede the '--' separator
        self.assertLess(prefix.index("--mount /srv/gstore/raw:/raw:ro"), prefix.index("--"))

    def test_prefix_omits_mount_by_default(self):
        wf = DiannWorkflow(workunit_id="WU0", docker_image="diann:2.3.2")
        self.assertFalse(any(a.startswith("--mount") for a in wf._diann_invocation_prefix()))

    def test_raw_mount_round_trips_through_config(self):
        wf = DiannWorkflow(workunit_id="WU0", raw_mount=("/srv/raw", "/raw"))
        self.assertEqual(wf.to_config_dict()["raw_mount"], ["/srv/raw", "/raw"])
        restored = DiannWorkflow(**wf.to_config_dict())
        self.assertEqual(restored.raw_mount, ("/srv/raw", "/raw"))


class TestThermorawMountIO(unittest.TestCase):
    @patch("diann_runner.container_utils.find_docker_runtime", return_value="docker")
    def test_external_input_mounted_read_only_at_raw(self, _):
        with TemporaryDirectory() as root:
            root_p = Path(root).resolve()
            work = root_p / "work"
            raw = root_p / "gstore_raw"
            work.mkdir()
            raw.mkdir()
            (raw / "sample.raw").write_text("x")
            old = os.getcwd()
            os.chdir(work)
            try:
                builder = ContainerCommandBuilder("img", runtime="docker")
                container_in, container_out = _mount_io(
                    builder, raw / "sample.raw", work / "converted"
                )
                cmd = builder.build(["-i", container_in, "-o", container_out])
            finally:
                os.chdir(old)
            self.assertEqual(container_in, "/raw/sample.raw")
            self.assertEqual(container_out, "/data/converted")
            self.assertIn(f"{raw}:/raw:ro", cmd)
            self.assertIn(f"{work}:/data", cmd)

    @patch("diann_runner.container_utils.find_docker_runtime", return_value="docker")
    def test_input_inside_workdir_uses_data_mount_only(self, _):
        with TemporaryDirectory() as root:
            work = Path(root).resolve()
            (work / "input").mkdir()
            (work / "input" / "sample.raw").write_text("x")
            old = os.getcwd()
            os.chdir(work)
            try:
                builder = ContainerCommandBuilder("img", runtime="docker")
                container_in, container_out = _mount_io(
                    builder, work / "input" / "sample.raw", work / "converted"
                )
                cmd = builder.build(["-i", container_in])
            finally:
                os.chdir(old)
            self.assertEqual(container_in, "/data/input/sample.raw")
            self.assertNotIn("/raw", " ".join(cmd))


if __name__ == "__main__":
    unittest.main()
