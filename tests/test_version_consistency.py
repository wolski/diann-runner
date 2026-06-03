"""Drift guard: the DIA-NN version dropdown, the image maps, and the deploy
build matrix must all agree.

The bfabric XML executable is the single source of truth for the
``01_diann_version`` dropdown. Every version offered there must have a
matching entry in ``images.docker.diann_images`` (and ``images.apptainer``)
of both shipped defaults files, and the deploy build matrix must cover exactly
those versions. This test fails loudly if any of them drift apart.
"""

import unittest
import xml.etree.ElementTree as ET
from importlib.resources import files
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
XML_PATH = REPO_ROOT / "bfabric_executable" / "executable_A386_DIANN_3.2.xml"
CONFIG_DIR = files("diann_runner") / "config"
DEFAULTS_FILES = ("defaults_local.yml", "defaults_server.yml")


def xml_version_enumerations() -> set[str]:
    """Versions offered by the 01_diann_version dropdown in the XML executable."""
    tree = ET.parse(XML_PATH)
    for parameter in tree.getroot().iter("parameter"):
        key = parameter.findtext("key")
        if key == "01_diann_version":
            return {e.text for e in parameter.findall("enumeration")}
    raise AssertionError("No '01_diann_version' parameter found in XML executable")


def diann_image_keys(defaults_filename: str, runtime: str) -> set[str]:
    """Version keys in images.<runtime>.diann_images of a defaults file."""
    with (CONFIG_DIR / defaults_filename).open() as f:
        raw = yaml.safe_load(f)
    return set(raw["images"][runtime]["diann_images"].keys())


class TestVersionConsistency(unittest.TestCase):
    def test_xml_dropdown_matches_config_maps(self):
        """Every defaults file (docker + apptainer) lists exactly the XML versions."""
        xml_versions = xml_version_enumerations()
        self.assertTrue(xml_versions, "XML dropdown should enumerate at least one version")
        for defaults_filename in DEFAULTS_FILES:
            for runtime in ("docker", "apptainer"):
                self.assertEqual(
                    diann_image_keys(defaults_filename, runtime),
                    xml_versions,
                    f"{defaults_filename} images.{runtime}.diann_images keys "
                    f"must match the 01_diann_version XML enumerations",
                )

    def test_build_matrix_covers_all_dropdown_versions(self):
        """deploy.load_diann_build_matrix() builds exactly the dropdown versions."""
        import sys

        sys.path.insert(0, str(REPO_ROOT))
        from deploy import load_diann_build_matrix

        matrix_versions = {spec["version"] for spec in load_diann_build_matrix()}
        self.assertEqual(matrix_versions, xml_version_enumerations())

    def test_build_matrix_uses_single_dockerfile(self):
        """All versions build from the one .NET 8 Dockerfile (no -thermo split)."""
        import sys

        sys.path.insert(0, str(REPO_ROOT))
        from deploy import load_diann_build_matrix

        dockerfile = REPO_ROOT / "docker" / "Dockerfile.diann"
        self.assertTrue(dockerfile.exists(), "the shared DIA-NN Dockerfile must exist")
        for spec in load_diann_build_matrix():
            self.assertEqual(spec["dockerfile"], "docker/Dockerfile.diann")
            self.assertFalse(
                spec["tag"].endswith("-thermo"),
                "image tags should no longer carry the -thermo suffix",
            )


if __name__ == "__main__":
    unittest.main()
