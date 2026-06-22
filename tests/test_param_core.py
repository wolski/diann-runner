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
# Omits the defaulted fields (scan_window, ids_to_names, diann_version, and the
# top-level controls) so the default path is exercised too.
CANON = {
    "var_mods": "--var-mods 1 --var-mod UniMod:35,15.994915,M",
    "no_peptidoforms": "false",
    "unimod4": "true",
    "met_excision": "true",
    "min_pep_len": "6",
    "max_pep_len": "30",
    "min_pr_charge": "2",
    "max_pr_charge": "3",
    "min_pr_mz": "400",
    "max_pr_mz": "1500",
    "min_fr_mz": "200",
    "max_fr_mz": "1800",
    "cut": "K*,R*",
    "missed_cleavages": "1",
    "mass_acc": "AUTO",
    "mass_acc_ms1": "AUTO",
    "qvalue": "0.01",
    "pg_level": "protein_names_1",
    "relaxed_prot_inf": "true",
    "reanalyse": "true",
    "no_norm": "false",
    "verbose": "1",
    "is_dda": "false",
}
FASTA = {"database_path": "db.fasta", "use_custom_fasta": False}


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
        self.assertEqual(_pg_level("protein_names_1"), 1)
        self.assertEqual(_pg_level("genes_0"), 0)
        self.assertEqual(_pg_level("isoforms_2"), 2)

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
        # Omitted from the canonical input -> typed defaults in the diann sub-dict.
        result = build_internal_params(dict(CANON), fasta=dict(FASTA))
        self.assertEqual(result["diann"]["export_quant"], False)
        self.assertEqual(result["diann"]["unrelated_runs"], False)
        self.assertEqual(result["diann"]["freestyle"], [])
        # Supplied values are transformed.
        canon = dict(
            CANON,
            export_quant="true",
            unrelated_runs="true",
            freestyle="--unrelated-runs",
        )
        result = build_internal_params(canon, fasta=dict(FASTA))
        self.assertEqual(result["diann"]["export_quant"], True)
        self.assertEqual(result["diann"]["unrelated_runs"], True)
        self.assertEqual(result["diann"]["freestyle"], ["--unrelated-runs"])
        self.assertEqual(parse_var_mods_string(""), [])


class TestBuildInternalParams(unittest.TestCase):
    def test_transforms_and_types(self):
        wf = build_internal_params(dict(CANON), fasta=dict(FASTA))
        d = wf["diann"]
        self.assertEqual(d["min_pep_len"], 6)
        self.assertIsInstance(d["min_pep_len"], int)
        self.assertEqual(d["qvalue"], 0.01)
        self.assertIsInstance(d["qvalue"], float)
        self.assertEqual(d["mass_acc"], "AUTO")
        self.assertEqual(d["pg_level"], 1)
        self.assertIs(d["is_dda"], False)
        self.assertEqual(d["var_mods"], [("35", "15.994915", "M")])
        self.assertEqual(wf["var_mods"], [("35", "15.994915", "M")])
        self.assertEqual(wf["fasta"], FASTA)

    def test_hardcoded_and_defaults(self):
        wf = build_internal_params(dict(CANON), fasta=dict(FASTA))
        d = wf["diann"]
        self.assertEqual(d["diann_bin"], DIANN_BIN)
        self.assertEqual(d["diann_bin"], "diann-docker")
        # Defaulted fields (caller omitted them):
        self.assertEqual(d["scan_window"], "AUTO")
        self.assertIs(d["ids_to_names"], False)
        self.assertEqual(d["diann_version"], "2.3.2")
        self.assertEqual(wf["workflow_mode"], "two_step")
        self.assertEqual(wf["raw_converter"], "thermoraw")
        self.assertEqual(wf["library_predictor"], "diann")
        self.assertIs(wf["enable_step_c"], False)
        self.assertIs(wf["include_libs"], False)

    def test_missing_required_field_raises(self):
        partial = dict(CANON)
        del partial["qvalue"]  # qvalue has no default -> required
        with self.assertRaises(KeyError):
            build_internal_params(partial, fasta=dict(FASTA))

    def test_var_mods_default_is_fresh_list(self):
        # Two builds without var_mods must not share the same list object.
        canon = {k: v for k, v in CANON.items() if k != "var_mods"}
        a = build_internal_params(dict(canon), fasta=dict(FASTA))
        b = build_internal_params(dict(canon), fasta=dict(FASTA))
        self.assertEqual(a["diann"]["var_mods"], [])
        self.assertIsNot(a["diann"]["var_mods"], b["diann"]["var_mods"])

    def test_defaulted_field_names_match_get_semantics(self):
        # Only these canonical fields carry a default (mirroring parse_flat_params's
        # historical .get() reads); the rest are required (no default -> KeyError).
        defaulted = {n for n, spec in DIANN_FIELDS.items() if spec.default is not _MISSING}
        self.assertEqual(
            defaulted,
            {
                "scan_window",
                "ids_to_names",
                "diann_version",
                "export_quant",
                "unrelated_runs",
                "freestyle",
                "workflow_mode",
                "raw_converter",
                "library_predictor",
                "enable_step_c",
                "include_libs",
            },
        )


if __name__ == "__main__":
    unittest.main()
