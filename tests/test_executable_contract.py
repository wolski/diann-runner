"""Contract tests binding the A386 executable definition (YAML, the source of
truth) to the parser, the adapter maps, and the slurmworker mirror.

The executable is defined once in
``bfabric_executable/executable_A386_DIANN_3.2.yaml`` (hand-editable; uploaded to
B-Fabric with ``bfabric-cli executable upload``, which creates a new executable).
These tests guard the bug classes the rename refactor exposed:
- a ``value`` default the parser cannot transform (the pre-2026-06-26 ``pg_level``
  enum form ``protein_IDs_2`` -> ``int("protein_IDs")`` ValueError),
- a modifiable key with no ``BFABRIC_TO_DRUNNER`` entry (silently dropped),
- an adapter map value that is not a real canonical field,
- the diann_runner and slurmworker copies drifting apart.
"""

import unittest
from pathlib import Path

import yaml

from diann_runner.param_core import DIANN_FIELDS, _pg_level
from diann_runner.request import DIANNRunnerParams
from diann_runner.snakemake_helpers import BFABRIC_TO_DRUNNER, parse_flat_params
from diann_runner.sushi_adapter import SUSHI_TO_DRUNNER

REPO_ROOT = Path(__file__).resolve().parents[1]
EXEC_YAML = REPO_ROOT / "bfabric_executable" / "executable_A386_DIANN_3.2.yaml"
SLURMWORKER_YAML = (
    REPO_ROOT.parent / "slurmworker" / "config" / "A386_DIANN_23" / "executable_A386_DIANN23plus.yaml"
)

# FASTA keys are resolved by _bfabric_fasta (not via BFABRIC_TO_DRUNNER); the
# version-bookkeeping key is consumed by B-Fabric, not the workflow.
FASTA_KEYS = {"input_fasta_databases", "input_fasta_additional", "input_fasta_use_custom"}
UNMAPPED_OK = FASTA_KEYS | {"application_version"}


def _executable(path: Path = EXEC_YAML) -> dict:
    return yaml.safe_load(path.read_text())["executable"]


def _parameters() -> list[dict]:
    return _executable()["parameter"]


class TestExecutableContract(unittest.TestCase):
    def test_defaults_parse_and_validate(self):
        """Every parameter's default ``value`` must parse + validate end to end.

        This is the test that would have caught the slurmworker ``pg_level``
        default ``protein_IDs_2`` (unparseable by ``_pg_level``).
        """
        flat = {p["key"]: p["value"] for p in _parameters()}
        parsed = parse_flat_params(flat)
        DIANNRunnerParams.from_parsed(parsed)  # raises on any drift

    def test_every_modifiable_key_is_mapped(self):
        """A user-editable key with no map entry would be silently dropped."""
        for p in _parameters():
            key = p["key"]
            if key in BFABRIC_TO_DRUNNER or key in UNMAPPED_OK:
                continue
            self.assertEqual(
                p.get("modifiable"), "false",
                f"key {key!r} is modifiable but absent from BFABRIC_TO_DRUNNER "
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
            if p["key"] == "search_protein_pg_level":
                for e in p.get("enumeration", []):
                    _pg_level(e)
                _pg_level(p["value"])
                return
        self.fail("search_protein_pg_level not found in the executable YAML")

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

    @unittest.skipUnless(SLURMWORKER_YAML.is_file(), "slurmworker mirror not checked out")
    def test_slurmworker_mirror_identical(self):
        """The slurmworker executable YAML must match the diann_runner source."""
        self.assertEqual(
            _executable(EXEC_YAML), _executable(SLURMWORKER_YAML),
            "slurmworker A386 executable diverged from the diann_runner source",
        )


if __name__ == "__main__":
    unittest.main()
