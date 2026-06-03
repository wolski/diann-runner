"""Tests for the prolfquapp-docker container command builder.

prolfquapp callers supply their own command (e.g. ``prolfqua_qc.sh ...``) as
argv, so under apptainer the wrapper must use ``exec`` (override the image
runscript), not the default ``run`` (which would pass the command as a
runscript argument). See build_container_cmd().
"""

import unittest

from diann_runner.prolfquapp_docker import build_container_cmd


class TestProlfquappDockerCommand(unittest.TestCase):
    ARGV = ["prolfqua_qc.sh", "--indir", "out", "-s", "DIANN"]

    def test_apptainer_uses_exec_for_explicit_command(self):
        cmd = build_container_cmd("/opt/sif/prolfquapp.sif", "apptainer", self.ARGV)
        self.assertEqual(cmd[0], "apptainer")
        self.assertEqual(cmd[1], "exec")
        # image precedes the caller-supplied command
        img_i = cmd.index("/opt/sif/prolfquapp.sif")
        self.assertEqual(cmd[img_i + 1], "prolfqua_qc.sh")
        self.assertEqual(cmd[-len(self.ARGV):], self.ARGV)

    def test_docker_runs_with_command(self):
        cmd = build_container_cmd("prolfqua/prolfquapp:2.0.10", "docker", self.ARGV)
        self.assertIn("run", cmd)
        img_i = cmd.index("prolfqua/prolfquapp:2.0.10")
        self.assertEqual(cmd[img_i + 1], "prolfqua_qc.sh")
        self.assertEqual(cmd[-len(self.ARGV):], self.ARGV)


if __name__ == "__main__":
    unittest.main()
