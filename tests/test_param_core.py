"""Tests for the shared caller-agnostic DIA-NN parameter core."""

import unittest

from diann_runner.param_core import (
    _MISSING,
    DIANN_BIN,
    DIANN_FIELDS,
    _freestyle,
    _int_or_auto,
    _pg_level,
    _to_bool,
    build_internal_params,
    parse_var_mods_string,
)

# A full canonical-keyed input (string values, as the caller adapters supply).
# Omits the defaulted fields (scan_window, protein_ids_to_names, diann_version, and
# the top-level controls) so the default path is exercised too.
CANON = {
    "mods_variable": "--var-mods 1 --var-mod UniMod:35,15.994915,M",
    "mods_no_peptidoforms": "false",
    "mods_unimod4": "true",
    "mods_met_excision": "true",
    "peptide_min_length": "6",
    "peptide_max_length": "30",
    "precursor_charge_min": "2",
    "precursor_charge_max": "3",
    "precursor_mz_min": "400",
    "precursor_mz_max": "1500",
    "fragment_mz_min": "200",
    "fragment_mz_max": "1800",
    "digestion_cut": "K*,R*",
    "digestion_missed_cleavages": "1",
    "mass_acc_ms2": "AUTO",
    "mass_acc_ms1": "AUTO",
    "scoring_qvalue": "0.01",
    "protein_pg_level": "1_protein_names",
    "reanalyse": "true",
    "no_norm": "false",
    "verbose": "1",
    "is_dda": "false",
}
FASTA = {"fasta_databases": ["db.fasta"], "fasta_use_custom": False}


class TestLeafTransforms(unittest.TestCase):
    def test_to_bool(self):
        self.assertTrue(_to_bool("true"))
        self.assertTrue(_to_bool("TRUE"))
        self.assertTrue(_to_bool(True))
        self.assertFalse(_to_bool("false"))
        self.assertFalse(_to_bool(False))

    def test_int_or_auto(self):
        self.assertEqual(_int_or_auto("AUTO"), "AUTO")
        self.assertEqual(_int_or_auto("10"), 10)

    def test_pg_level(self):
        self.assertEqual(_pg_level("0_isoform_IDs"), 0)
        self.assertEqual(_pg_level("1_protein_names"), 1)
        self.assertEqual(_pg_level("2_genes"), 2)

    def test_parse_var_mods_string(self):
        self.assertEqual(
            parse_var_mods_string("--var-mods 1 --var-mod UniMod:35,15.994915,M"),
            [("35", "15.994915", "M")],
        )
        self.assertEqual(parse_var_mods_string("None"), [])

    def test_freestyle(self):
        # Empty / sentinel -> [] (and never the shared default object).
        self.assertEqual(_freestyle("None"), [])
        self.assertEqual(_freestyle(""), [])
        self.assertEqual(_freestyle("  "), [])
        # Plain flags split on whitespace.
        self.assertEqual(
            _freestyle("--individual-mass-acc --individual-windows"),
            ["--individual-mass-acc", "--individual-windows"],
        )
        # shlex preserves quoted arguments.
        self.assertEqual(
            _freestyle('--foo "a b" --bar'), ["--foo", "a b", "--bar"]
        )
        # Fresh list each call.
        self.assertIsNot(_freestyle("None"), _freestyle("None"))

    def test_unrelated_runs_and_freestyle_defaults(self):
        # Omitted from the canonical input -> typed defaults in their sub-dicts.
        result = build_internal_params(dict(CANON), fasta=dict(FASTA))
        self.assertEqual(result["output"]["fragment_quant"], False)
        self.assertEqual(result["search"]["mass_acc_unrelated_runs"], False)
        self.assertEqual(result["advanced"]["freestyle"], [])
        # Supplied values are transformed.
        canon = dict(
            CANON,
            fragment_quant="true",
            mass_acc_unrelated_runs="true",
            freestyle="--unrelated-runs",
        )
        result = build_internal_params(canon, fasta=dict(FASTA))
        self.assertEqual(result["output"]["fragment_quant"], True)
        self.assertEqual(result["search"]["mass_acc_unrelated_runs"], True)
        self.assertEqual(result["advanced"]["freestyle"], ["--unrelated-runs"])
        self.assertEqual(parse_var_mods_string(""), [])


class TestBuildInternalParams(unittest.TestCase):
    def test_transforms_and_types(self):
        wf = build_internal_params(dict(CANON), fasta=dict(FASTA))
        self.assertEqual(wf["lib"]["peptide_min_length"], 6)
        self.assertIsInstance(wf["lib"]["peptide_min_length"], int)
        self.assertEqual(wf["search"]["scoring_qvalue"], 0.01)
        self.assertIsInstance(wf["search"]["scoring_qvalue"], float)
        self.assertEqual(wf["search"]["mass_acc_ms2"], "AUTO")
        self.assertEqual(wf["search"]["protein_pg_level"], 1)
        self.assertIs(wf["pipeline"]["is_dda"], False)
        self.assertEqual(wf["lib"]["mods_variable"], [("35", "15.994915", "M")])
        self.assertEqual(wf["inputs"], FASTA)

    def test_hardcoded_and_defaults(self):
        wf = build_internal_params(dict(CANON), fasta=dict(FASTA))
        self.assertEqual(wf["diann_bin"], DIANN_BIN)
        self.assertEqual(wf["diann_bin"], "diann-docker")
        # Defaulted fields (caller omitted them):
        self.assertEqual(wf["quant"]["scan_window"], "AUTO")
        self.assertIs(wf["search"]["protein_ids_to_names"], False)
        self.assertEqual(wf["pipeline"]["diann_version"], "2.3.2")
        self.assertEqual(wf["pipeline"]["workflow_mode"], "two_step")
        self.assertEqual(wf["pipeline"]["raw_converter"], "thermoraw")
        self.assertEqual(wf["library_predictor"], "diann")
        self.assertIs(wf["enable_step_c"], False)
        self.assertIs(wf["output"]["include_libs"], False)
        self.assertIs(wf["output"]["pmultiqc"], True)

    def test_missing_required_field_raises(self):
        partial = dict(CANON)
        del partial["scoring_qvalue"]  # scoring_qvalue has no default -> required
        with self.assertRaises(KeyError):
            build_internal_params(partial, fasta=dict(FASTA))

    def test_var_mods_default_and_parsed_lists(self):
        # Omitted mods_variable -> empty list default in the lib sub-dict.
        canon = {k: v for k, v in CANON.items() if k != "mods_variable"}
        a = build_internal_params(dict(canon), fasta=dict(FASTA))
        self.assertEqual(a["lib"]["mods_variable"], [])
        # When supplied, the parse transform yields a fresh list each build so
        # two builds never alias the same mutable object.
        supplied = dict(CANON, mods_variable="--var-mods 1 --var-mod UniMod:35,15.994915,M")
        x = build_internal_params(dict(supplied), fasta=dict(FASTA))
        y = build_internal_params(dict(supplied), fasta=dict(FASTA))
        self.assertEqual(x["lib"]["mods_variable"], [("35", "15.994915", "M")])
        self.assertIsNot(x["lib"]["mods_variable"], y["lib"]["mods_variable"])

    def test_defaulted_field_names_match_get_semantics(self):
        # Only these canonical fields carry a default (mirroring parse_flat_params's
        # historical .get() reads); the rest are required (no default -> KeyError).
        defaulted = {n for n, spec in DIANN_FIELDS.items() if spec.default is not _MISSING}
        self.assertEqual(
            defaulted,
            {
                "scan_window",
                "protein_ids_to_names",
                "diann_version",
                "fragment_quant",
                "mass_acc_unrelated_runs",
                "mods_variable",
                "freestyle",
                "workflow_mode",
                "raw_converter",
                "library_predictor",
                "enable_step_c",
                "include_libs",
                "pmultiqc",
            },
        )


if __name__ == "__main__":
    unittest.main()
