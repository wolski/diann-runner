"""Tests for the normalized DiannRunRequest / DIANNRunnerParams contract."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from diann_runner.request import (
    COL_NAME,
    COL_RELATIVE_PATH,
    DIANNRunnerParams,
    DiannRunRequest,
    dataset_raw_basenames,
    validate_request,
)
from diann_runner.snakemake_helpers import parse_flat_params

# A representative flat-params dict exercising both the 'AUTO' sentinel
# (mass_acc) and a concrete int (mass_acc_ms1), plus a variable modification.
BASE_FLAT_PARAMS = {
    "06a_diann_mods_variable": "--var-mods 1 --var-mod UniMod:35,15.994915,M",
    "06b_diann_mods_no_peptidoforms": "false",
    "06c_diann_mods_unimod4": "true",
    "06d_diann_mods_met_excision": "true",
    "07_diann_peptide_min_length": "6",
    "07_diann_peptide_max_length": "30",
    "07_diann_peptide_precursor_charge_min": "2",
    "07_diann_peptide_precursor_charge_max": "3",
    "07_diann_peptide_precursor_mz_min": "400",
    "07_diann_peptide_precursor_mz_max": "1500",
    "07_diann_peptide_fragment_mz_min": "200",
    "07_diann_peptide_fragment_mz_max": "1800",
    "08_diann_digestion_cut": "K*,R*",
    "08_diann_digestion_missed_cleavages": "1",
    "09_diann_mass_acc_ms2": "AUTO",
    "09_diann_mass_acc_ms1": "10",
    "10_diann_scoring_qvalue": "0.01",
    "11a_diann_protein_pg_level": "protein_names_2",
    "11b_diann_protein_relaxed_prot_inf": "true",
    "12a_diann_quantification_reanalyse": "true",
    "12b_diann_quantification_no_norm": "false",
    "99_other_verbose": "1",
    "05_diann_is_dda": "false",
    "05b_diann_scan_window": "AUTO",
    "03_fasta_database_path": "/data/db.fasta",
    "03_fasta_use_custom": "false",
}


class TestParamsRoundTrip(unittest.TestCase):
    """DIANNRunnerParams must preserve the parse_flat_params contract exactly."""

    def setUp(self):
        self.parsed = parse_flat_params(dict(BASE_FLAT_PARAMS))

    def test_to_parsed_equals_parse_flat_params(self):
        params = DIANNRunnerParams.from_parsed(self.parsed)
        self.assertEqual(params.to_parsed(), self.parsed)

    def test_toml_dict_round_trip(self):
        params = DIANNRunnerParams.from_parsed(self.parsed)
        restored = DIANNRunnerParams.from_toml_dict(params.to_toml_dict())
        self.assertEqual(restored.to_parsed(), self.parsed)

    def test_toml_file_round_trip(self):
        params = DIANNRunnerParams.from_parsed(self.parsed)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "diann_runner_params.toml"
            params.to_toml(path)
            restored = DIANNRunnerParams.from_toml(path)
        self.assertEqual(restored.to_parsed(), self.parsed)

    def test_auto_sentinel_and_int_types_preserved(self):
        # 'AUTO' must survive as a str; a concrete value as an int.
        params = DIANNRunnerParams.from_parsed(self.parsed)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.toml"
            params.to_toml(path)
            restored = DIANNRunnerParams.from_toml(path).to_parsed()
        self.assertEqual(restored["diann"]["mass_acc"], "AUTO")
        self.assertIsInstance(restored["diann"]["mass_acc"], str)
        self.assertEqual(restored["diann"]["mass_acc_ms1"], 10)
        self.assertIsInstance(restored["diann"]["mass_acc_ms1"], int)

    def test_var_mods_re_tupled_after_toml(self):
        params = DIANNRunnerParams.from_parsed(self.parsed)
        restored = DIANNRunnerParams.from_toml_dict(params.to_toml_dict())
        self.assertEqual(restored.var_mods, [("35", "15.994915", "M")])
        self.assertIsInstance(restored.var_mods[0], tuple)


class TestParamsValidation(unittest.TestCase):
    """The Pydantic model fails fast on a malformed parse_flat_params contract."""

    def setUp(self):
        self.parsed = parse_flat_params(dict(BASE_FLAT_PARAMS))

    def test_valid_parsed_dict_accepted(self):
        DIANNRunnerParams.from_parsed(self.parsed)  # should not raise

    def test_auto_sentinel_accepted_for_mass_acc(self):
        self.parsed["diann"]["mass_acc"] = "AUTO"
        self.assertEqual(DIANNRunnerParams.from_parsed(self.parsed).diann.mass_acc, "AUTO")

    def test_non_int_min_pep_len_rejected(self):
        self.parsed["diann"]["min_pep_len"] = "not-an-int"
        with self.assertRaises(ValidationError):
            DIANNRunnerParams.from_parsed(self.parsed)

    def test_unknown_diann_key_rejected(self):
        self.parsed["diann"]["bogus_param"] = 1
        with self.assertRaises(ValidationError):
            DIANNRunnerParams.from_parsed(self.parsed)

    def test_missing_required_key_rejected(self):
        del self.parsed["diann"]["qvalue"]
        with self.assertRaises(ValidationError):
            DIANNRunnerParams.from_parsed(self.parsed)

    def test_bad_auto_string_rejected(self):
        # Only the exact sentinel "AUTO" is allowed alongside int.
        self.parsed["diann"]["scan_window"] = "MAYBE"
        with self.assertRaises(ValidationError):
            DIANNRunnerParams.from_parsed(self.parsed)


class TestDatasetBasenames(unittest.TestCase):
    def test_basenames_taken_from_relative_path_column(self):
        df = pd.DataFrame(
            {
                COL_RELATIVE_PATH: ["p34486/sub/a.raw", "/abs/b.raw"],
                COL_NAME: ["A", "B"],
            }
        )
        self.assertEqual(dataset_raw_basenames(df), ["a.raw", "b.raw"])

    def test_missing_relative_path_column_raises(self):
        df = pd.DataFrame({COL_NAME: ["A"]})
        with self.assertRaises(KeyError):
            dataset_raw_basenames(df)


class TestValidateRequest(unittest.TestCase):
    def _params(self):
        return DIANNRunnerParams.from_parsed(parse_flat_params(dict(BASE_FLAT_PARAMS)))

    def _request(self, tmp: Path, raw_names, fasta_names, dataset_names):
        raw_dir = tmp / "raw"
        raw_dir.mkdir()
        for n in raw_names:
            (raw_dir / n).write_text("raw")
        fastas = []
        for n in fasta_names:
            f = tmp / n
            f.write_text(">seq\nPEPTIDE\n")
            fastas.append(f)
        df = pd.DataFrame(
            {
                COL_RELATIVE_PATH: list(dataset_names),
                COL_NAME: [f"S{i}" for i in range(len(dataset_names))],
            }
        )
        return DiannRunRequest(
            params=self._params(),
            raw_file_dir=raw_dir,
            dataset=df,
            database_fasta=fastas,
            work_dir=tmp / "work",
            output_dir=tmp / "work",
            cores=8,
        )

    def test_valid_request_passes(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req = self._request(
                tmp,
                raw_names=["a.raw", "b.raw"],
                fasta_names=["db.fasta"],
                dataset_names=["proj/a.raw", "proj/b.raw"],
            )
            validate_request(req)  # should not raise

    def test_missing_raw_file_fails(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req = self._request(
                tmp,
                raw_names=["a.raw"],  # b.raw missing
                fasta_names=["db.fasta"],
                dataset_names=["a.raw", "b.raw"],
            )
            with self.assertRaises(FileNotFoundError) as cm:
                validate_request(req)
            self.assertIn("b.raw", str(cm.exception))

    def test_missing_fasta_fails(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req = self._request(
                tmp,
                raw_names=["a.raw"],
                fasta_names=["db.fasta"],
                dataset_names=["a.raw"],
            )
            req.database_fasta.append(tmp / "missing.fasta")
            with self.assertRaises(FileNotFoundError) as cm:
                validate_request(req)
            self.assertIn("missing.fasta", str(cm.exception))

    def test_multiple_fasta_without_filename_inference(self):
        # Two FASTA files are carried explicitly; no role is inferred from name.
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req = self._request(
                tmp,
                raw_names=["a.raw"],
                fasta_names=["db.fasta", "order.fasta"],
                dataset_names=["a.raw"],
            )
            validate_request(req)
            self.assertEqual(len(req.database_fasta), 2)


if __name__ == "__main__":
    unittest.main()
