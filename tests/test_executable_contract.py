"""Contract tests binding the A386 executable XML (the source of truth) to the
parser, the adapter maps, and the slurmworker mirror.

These guard the bug classes the rename refactor exposed but the behavioural tests
could not see:
- an XML <value> default that the parser cannot transform (the pre-2026-06-26
  ``pg_level`` enum form ``protein_IDs_2`` -> ``int("protein_IDs")`` ValueError),
- a modifiable XML key with no ``BFABRIC_TO_DRUNNER`` entry (silently dropped by
  ``parse_flat_params``),
- an adapter map value that is not a real canonical field,
- the two A386 executables drifting apart.
"""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from diann_runner.param_core import DIANN_FIELDS, _pg_level
from diann_runner.request import DIANNRunnerParams
from diann_runner.snakemake_helpers import BFABRIC_TO_DRUNNER, parse_flat_params
from diann_runner.sushi_adapter import SUSHI_TO_DRUNNER

REPO_ROOT = Path(__file__).resolve().parents[1]
XML_PATH = REPO_ROOT / "bfabric_executable" / "executable_A386_DIANN_3.2.xml"
SLURMWORKER_XML = (
    REPO_ROOT.parent / "slurmworker" / "config" / "A386_DIANN_23" / "executable_A386_DIANN23plus.xml"
)

# FASTA keys are resolved by _bfabric_fasta (not via BFABRIC_TO_DRUNNER); the
# version-bookkeeping key is consumed by B-Fabric, not the workflow.
FASTA_KEYS = {"input_fasta_databases", "input_fasta_additional", "input_fasta_use_custom"}
UNMAPPED_OK = FASTA_KEYS | {"application_version"}


def _parameters():
    return list(ET.parse(XML_PATH).getroot().iter("parameter"))


class TestExecutableContract(unittest.TestCase):
    def test_xml_defaults_parse_and_validate(self):
        """Every <parameter>'s default <value> must parse + validate end to end.

        This is the test that would have caught the slurmworker ``pg_level``
        default ``protein_IDs_2`` (unparseable by ``_pg_level``).
        """
        flat = {p.findtext("key"): p.findtext("value") for p in _parameters()}
        parsed = parse_flat_params(flat)
        DIANNRunnerParams.from_parsed(parsed)  # raises on any drift

    def test_every_modifiable_key_is_mapped(self):
        """A user-editable XML key with no map entry would be silently dropped."""
        for p in _parameters():
            key = p.findtext("key")
            if key in BFABRIC_TO_DRUNNER or key in UNMAPPED_OK:
                continue
            self.assertEqual(
                p.findtext("modifiable"), "false",
                f"XML key {key!r} is modifiable but absent from BFABRIC_TO_DRUNNER "
                "-> parse_flat_params would silently drop it",
            )

    def test_adapter_values_are_canonical_fields(self):
        """Every adapter map value must be a real DIANN_FIELDS canonical name."""
        for name, mapping in (("BFABRIC_TO_DRUNNER", BFABRIC_TO_DRUNNER), ("SUSHI_TO_DRUNNER", SUSHI_TO_DRUNNER)):
            for gui_key, canonical in mapping.items():
                self.assertIn(
                    canonical, DIANN_FIELDS,
                    f"{name}[{gui_key!r}] -> {canonical!r} is not a DIANN_FIELDS field",
                )

    def test_pg_level_enums_and_default_parse(self):
        """Every pg_level enum + the default must survive _pg_level (leading-number form)."""
        for p in _parameters():
            if p.findtext("key") == "search_protein_pg_level":
                for e in p.findall("enumeration"):
                    _pg_level(e.text)
                _pg_level(p.findtext("value"))
                return
        self.fail("search_protein_pg_level not found in XML")

    def test_bfabric_and_sushi_agree_on_shared_keys(self):
        """Both frontends must map a shared GUI key to the same canonical field."""
        for k in set(BFABRIC_TO_DRUNNER) & set(SUSHI_TO_DRUNNER):
            self.assertEqual(
                BFABRIC_TO_DRUNNER[k], SUSHI_TO_DRUNNER[k],
                f"frontends disagree on canonical name for {k!r}",
            )
        # library_predictor is the only mapped key that is B-Fabric-only.
        self.assertEqual(set(BFABRIC_TO_DRUNNER) - set(SUSHI_TO_DRUNNER), {"library_predictor"})
        self.assertEqual(set(SUSHI_TO_DRUNNER) - set(BFABRIC_TO_DRUNNER), set())

    @unittest.skipUnless(SLURMWORKER_XML.is_file(), "slurmworker mirror not checked out")
    def test_slurmworker_mirror_body_identical(self):
        """The slurmworker A386 executable body must match the diann_runner source."""
        def body(path: Path) -> str:
            text = path.read_text()
            return text[text.index("<parameter"):]  # parameters + footer; ignore the header

        self.assertEqual(
            body(XML_PATH), body(SLURMWORKER_XML),
            "slurmworker A386 executable body diverged from the diann_runner source",
        )


if __name__ == "__main__":
    unittest.main()
