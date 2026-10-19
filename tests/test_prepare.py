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
    "lib_mods_variable": "None",
    "lib_mods_no_peptidoforms": "false",
    "lib_mods_unimod4": "true",
    "lib_mods_met_excision": "true",
    "lib_peptide_min_length": "6",
    "lib_peptide_max_length": "30",
    "lib_precursor_charge_min": "2",
    "lib_precursor_charge_max": "3",
    "lib_precursor_mz_min": "400",
    "lib_precursor_mz_max": "1500",
    "lib_fragment_mz_min": "200",
    "lib_fragment_mz_max": "1800",
    "lib_digestion_cut": "K*,R*",
    "lib_digestion_missed_cleavages": "1",
    "search_mass_acc_ms2": "AUTO",
    "search_mass_acc_ms1": "AUTO",
    "search_scoring_qvalue": "0.01",
    "search_protein_pg_level": "1_protein_names",
    "quant_reanalyse": "true",
    "quant_no_norm": "false",
    "advanced_verbose": "1",
    "pipeline_is_dda": "false",
    "input_fasta_databases": "db.fasta",
    "input_fasta_use_custom": "false",
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


def _finished_work_dir(work: Path) -> None:
    """A work dir as a successful AppRunner run leaves it."""
    raw = work / "input" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "dataset.parquet").write_text("ds")
    (raw / "c.d.zip").write_text("zip")
    (raw / "c.done").write_text("")
    d = raw / "c.d"
    (d / "m.m").mkdir(parents=True)
    (d / "analysis.tdf").write_text("tdf")
    (d / "m.m" / "hystar.method").write_text("m")
    for p in (d / "m.m", d):  # staged timsTOF .d dirs arrive read-only
        p.chmod(0o555)
    (work / "temp-DIANN_quantB").mkdir()
    (work / "temp-DIANN_quantB" / "a.quant").write_text("q")
    (work / "out-DIANN_quantB").mkdir()
    (work / "out-DIANN_quantB" / "report.parquet").write_text("r")
    (work / "logs").mkdir()
    (work / "Result_WU999.zip").write_text("zip")
    (work / "outputs.yml").write_text("outputs: []")
    (work / "params.yml").write_text("p")


class TestCleanupWorkDir(unittest.TestCase):
    def test_removes_raws_and_intermediates_keeps_deliverables(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            work = tmp / "work"
            req = _make_request(tmp, raw_dir=work / "input" / "raw", work_dir=work)
            _finished_work_dir(work)
            prepare.cleanup_work_dir(req)
            raw = work / "input" / "raw"
            for gone in ("a.raw", "b.raw", "c.d.zip", "c.d"):
                self.assertFalse((raw / gone).exists(), gone)
            self.assertFalse((work / "temp-DIANN_quantB").exists())
            self.assertFalse((work / "out-DIANN_quantB").exists())
            for kept in ("Result_WU999.zip", "outputs.yml", "params.yml", "input/raw/dataset.parquet"):
                self.assertTrue((work / kept).is_file(), kept)
            self.assertIn("freed", (work / "logs" / "cleanup.log").read_text())

    def test_external_raw_dir_is_never_touched(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            work = tmp / "work"
            req = _make_request(tmp, raw_dir=tmp / "primary", work_dir=work)
            _finished_work_dir(work)
            prepare.cleanup_work_dir(req)
            self.assertTrue((tmp / "primary" / "a.raw").is_file())
            self.assertTrue((tmp / "primary" / "b.raw").is_file())
            self.assertFalse((work / "input" / "raw" / "c.d").exists())  # conversion output goes

    def test_nothing_deleted_without_outputs_yml(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            work = tmp / "work"
            req = _make_request(tmp, raw_dir=work / "input" / "raw", work_dir=work)
            _finished_work_dir(work)
            (work / "outputs.yml").unlink()
            prepare.cleanup_work_dir(req)
            self.assertTrue((work / "input" / "raw" / "a.raw").is_file())
            self.assertTrue((work / "temp-DIANN_quantB").is_dir())
            for p in (work / "input" / "raw" / "c.d", work / "input" / "raw" / "c.d" / "m.m"):
                p.chmod(0o755)  # let TemporaryDirectory clean up

    def test_flag_defaults_off(self):
        params = DIANNRunnerParams.from_parsed(parse_flat_params(dict(FLAT)))
        self.assertFalse(params.output.cleanup_on_success)
        flat = dict(FLAT, output_cleanup_on_success="true")
        params = DIANNRunnerParams.from_parsed(parse_flat_params(flat))
        self.assertTrue(params.output.cleanup_on_success)


if __name__ == "__main__":
    unittest.main()
