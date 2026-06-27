"""Tests for the generic runner: work-dir materialization + snakemake config."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from diann_runner import prepare
from diann_runner.request import (
    COL_NAME,
    COL_RELATIVE_PATH,
    DIANNRunnerParams,
    DiannRunRequest,
)
from diann_runner.snakemake_helpers import parse_flat_params

FLAT = {
    "06a_diann_mods_variable": "None",
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
    "09_diann_mass_acc_ms1": "AUTO",
    "10_diann_scoring_qvalue": "0.01",
    "11a_diann_protein_pg_level": "1_protein_names",
    "12a_diann_quantification_reanalyse": "true",
    "12b_diann_quantification_no_norm": "false",
    "99_other_verbose": "1",
    "05_diann_is_dda": "false",
    "03_fasta_database_path": "db.fasta",
    "03_fasta_use_custom": "false",
}


def _make_request(tmp: Path, *, raw_dir, work_dir, output_dir=None, register=True):
    raw_dir.mkdir(parents=True, exist_ok=True)
    for n in ("a.raw", "b.raw"):
        (raw_dir / n).write_text("raw")
    fasta = tmp / "db.fasta"
    fasta.write_text(">x\nPEPTIDE\n")
    df = pd.DataFrame({COL_RELATIVE_PATH: ["p/a.raw", "p/b.raw"], COL_NAME: ["A", "B"]})
    params = DIANNRunnerParams.from_parsed(parse_flat_params(dict(FLAT)))
    return DiannRunRequest(
        params=params,
        raw_file_dir=raw_dir,
        dataset=df,
        database_fasta=[fasta],
        work_dir=work_dir,
        output_dir=output_dir if output_dir is not None else work_dir,
        cores=4,
        workunit_id="999",
        register_outputs=register,
    )


class TestPrepareWorkDir(unittest.TestCase):
    def test_writes_toml_dataset_and_fasta_no_raw_copied(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req = _make_request(tmp, raw_dir=tmp / "gstore_raw", work_dir=tmp / "work")
            prepare.prepare_work_dir(req)
            work = req.work_dir
            self.assertTrue((work / "diann_runner_params.toml").is_file())
            self.assertTrue((work / "dataset.csv").is_file())
            self.assertTrue((work / "input" / "db.fasta").is_file())
            # No raw files copied into the work dir, no symlink farm.
            self.assertFalse((work / "input" / "raw").exists())
            copied = list(work.rglob("*.raw"))
            self.assertEqual(copied, [], f"raw files must not be copied: {copied}")

    def test_dataset_csv_keeps_schema(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req = _make_request(tmp, raw_dir=tmp / "gstore_raw", work_dir=tmp / "work")
            prepare.prepare_work_dir(req)
            cols = list(pd.read_csv(req.work_dir / "dataset.csv").columns)
            self.assertEqual(cols, [COL_RELATIVE_PATH, COL_NAME])


class TestSnakemakeConfig(unittest.TestCase):
    def test_external_raw_dir_gets_mount_and_converted_dir(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req = _make_request(tmp, raw_dir=tmp / "gstore_raw", work_dir=tmp / "work")
            cfg = prepare.build_snakemake_config(req)
            self.assertEqual(cfg["raw_mount_target"], "/raw")
            self.assertEqual(cfg["converted_dir"], "input/raw")
            self.assertEqual(cfg["raw_file_dir"], str((tmp / "gstore_raw").resolve()))
            self.assertEqual(cfg["register_outputs"], "True")

    def test_internal_raw_dir_is_relative_no_mount(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            work = tmp / "work"
            req = _make_request(tmp, raw_dir=work / "input" / "raw", work_dir=work, register=False)
            cfg = prepare.build_snakemake_config(req)
            self.assertEqual(cfg["raw_file_dir"], "input/raw")
            self.assertNotIn("raw_mount_target", cfg)
            self.assertNotIn("converted_dir", cfg)
            self.assertEqual(cfg["register_outputs"], "False")

    def test_container_runtime_forwarded_when_set(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req = _make_request(tmp, raw_dir=tmp / "work" / "input" / "raw", work_dir=tmp / "work")
            # default: no container_runtime in request -> not in config (auto-detect)
            self.assertNotIn("container_runtime", prepare.build_snakemake_config(req))
            req.container_runtime = "docker"
            self.assertEqual(prepare.build_snakemake_config(req)["container_runtime"], "docker")


class TestDeliverOutputs(unittest.TestCase):
    def test_noop_when_output_equals_work(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req = _make_request(tmp, raw_dir=tmp / "raw", work_dir=tmp / "work")
            req.work_dir.mkdir(parents=True, exist_ok=True)
            (req.work_dir / "Result_WU999.zip").write_text("zip")
            prepare.deliver_outputs(req)  # output_dir == work_dir → no-op, no error

    def test_copies_to_distinct_output_dir(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            req = _make_request(
                tmp, raw_dir=tmp / "raw", work_dir=tmp / "work", output_dir=tmp / "out"
            )
            req.work_dir.mkdir(parents=True, exist_ok=True)
            (req.work_dir / "Result_WU999.zip").write_text("zip")
            (req.work_dir / "qc_result").mkdir()
            (req.work_dir / "qc_result" / "x.txt").write_text("x")
            prepare.deliver_outputs(req)
            self.assertTrue((req.output_dir / "Result_WU999.zip").is_file())
            self.assertTrue((req.output_dir / "qc_result" / "x.txt").is_file())


if __name__ == "__main__":
    unittest.main()
