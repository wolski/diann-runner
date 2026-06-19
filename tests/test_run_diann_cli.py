"""Tests for the run-diann adapters (apprunner / sushi input handling)."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd
import yaml

from diann_runner.request import (
    COL_GROUPING,
    COL_NAME,
    COL_RELATIVE_PATH,
    DIANNRunnerParams,
    dataset_raw_basenames,
)
from diann_runner.run_diann_cli import _apply_fasta, _load_flat_params, app, sushi
from diann_runner.snakemake_helpers import parse_flat_params
from diann_runner.sushi_adapter import parse_sushi_dataset, parse_sushi_params

FLAT = {
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
    "09_diann_mass_acc_ms1": "AUTO",
    "10_diann_scoring_qvalue": "0.01",
    "11a_diann_protein_pg_level": "protein_names_1",
    "11b_diann_protein_relaxed_prot_inf": "true",
    "12a_diann_quantification_reanalyse": "true",
    "12b_diann_quantification_no_norm": "false",
    "99_other_verbose": "1",
    "05_diann_is_dda": "false",
    "03_fasta_database_path": "db.fasta",
    "03_fasta_use_custom": "false",
}

# SUSHI readable equivalent of FLAT (same values, readable keys). The SUSHI path
# carries every DIA-NN field via the GUI dump, so the full set is required — there
# is no longer a B-Fabric template to fill gaps.
SUSHI_FULL = {
    "mods_variable": "--var-mods 1 --var-mod UniMod:35,15.994915,M",
    "mods_no_peptidoforms": "false",
    "mods_unimod4": "true",
    "mods_met_excision": "true",
    "peptide_min_length": "6",
    "peptide_max_length": "30",
    "peptide_precursor_charge_min": "2",
    "peptide_precursor_charge_max": "3",
    "peptide_precursor_mz_min": "400",
    "peptide_precursor_mz_max": "1500",
    "peptide_fragment_mz_min": "200",
    "peptide_fragment_mz_max": "1800",
    "digestion_cut": "K*,R*",
    "digestion_missed_cleavages": "1",
    "mass_acc_ms2": "AUTO",
    "mass_acc_ms1": "AUTO",
    "scoring_qvalue": "0.01",
    "protein_pg_level": "protein_names_1",
    "protein_relaxed_prot_inf": "true",
    "quantification_reanalyse": "true",
    "quantification_no_norm": "false",
    "verbose": "1",
    "is_dda": "false",
}


class TestLoadFlatParams(unittest.TestCase):
    """AppRunner params.yml loading (unchanged)."""

    def test_params_block_with_registration(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "params.yml"
            p.write_text(yaml.safe_dump({"params": FLAT, "registration": {"workunit_id": "5", "container_id": "9"}}))
            flat, reg = _load_flat_params(p)
            self.assertEqual(flat["10_diann_scoring_qvalue"], "0.01")
            self.assertEqual(reg["workunit_id"], "5")

    def test_bare_flat_mapping(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "params.yml"
            p.write_text(yaml.safe_dump(FLAT))
            flat, reg = _load_flat_params(p)
            self.assertEqual(flat["08_diann_digestion_cut"], "K*,R*")
            self.assertEqual(reg, {})


class TestParseSushiParams(unittest.TestCase):
    """SUSHI params adapter: readable keys → internal params + fasta extraction."""

    def _write(self, root: Path, **extra) -> Path:
        p = root / "sushi_params.yml"
        p.write_text(yaml.safe_dump({**SUSHI_FULL, **extra}))
        return p

    def test_readable_overrides_map_to_diann_params(self):
        with tempfile.TemporaryDirectory() as t:
            p = self._write(
                Path(t),
                quantification_no_norm="true",       # override template 'false'
                peptide_min_length="8",              # override template '6'
                protein_relaxed_prot_inf="false",    # match template
                dataRoot="/srv/gstore/projects",
            )
            wf, fastas, data_root = parse_sushi_params(p)
            self.assertTrue(wf["diann"]["no_norm"])
            self.assertEqual(wf["diann"]["min_pep_len"], 8)
            self.assertFalse(wf["diann"]["relaxed_prot_inf"])
            self.assertEqual(data_root, "/srv/gstore/projects")
            self.assertEqual(fastas, [])

    def test_fasta_databases_split_into_list(self):
        with tempfile.TemporaryDirectory() as t:
            p = self._write(Path(t), fasta_databases="/db/a.fasta,/db/b.fasta")
            _, fastas, _ = parse_sushi_params(p)
            self.assertEqual(fastas, [Path("/db/a.fasta"), Path("/db/b.fasta")])

    def test_matches_apprunner_for_equivalent_keys(self):
        """SUSHI_TO_DRUNNER and BFABRIC_TO_DRUNNER converge on identical internal
        params without sharing any key vocabulary. SUSHI_FULL mirrors FLAT, so the
        nested `diann` dicts must be byte-identical (regression net against drift)."""
        with tempfile.TemporaryDirectory() as t:
            su_wf, _, _ = parse_sushi_params(self._write(Path(t)))
            ar_wf = parse_flat_params(dict(FLAT))
            self.assertEqual(su_wf["diann"], ar_wf["diann"])
            for key in (
                "var_mods",
                "workflow_mode",
                "raw_converter",
                "library_predictor",
                "enable_step_c",
                "include_libs",
            ):
                self.assertEqual(su_wf[key], ar_wf[key])

    def test_defaults_for_optional_keys(self):
        with tempfile.TemporaryDirectory() as t:
            wf, _, _ = parse_sushi_params(self._write(Path(t)))
            self.assertEqual(wf["diann"]["scan_window"], "AUTO")
            self.assertEqual(wf["diann"]["diann_version"], "2.3.2")
            self.assertIs(wf["diann"]["ids_to_names"], False)
            self.assertEqual(wf["workflow_mode"], "two_step")
            self.assertEqual(wf["raw_converter"], "thermoraw")
            self.assertEqual(wf["library_predictor"], "diann")
            self.assertIs(wf["enable_step_c"], False)
            self.assertIs(wf["include_libs"], False)

    def test_hardcoded_invariants(self):
        with tempfile.TemporaryDirectory() as t:
            wf, _, _ = parse_sushi_params(self._write(Path(t)))
            self.assertEqual(wf["diann"]["diann_bin"], "diann-docker")
            self.assertEqual(wf["fasta"], {"database_path": "NONE", "use_custom_fasta": False})

    def test_int_or_auto_and_pg_level_transforms(self):
        with tempfile.TemporaryDirectory() as t:
            wf, _, _ = parse_sushi_params(
                self._write(Path(t), scan_window="5", mass_acc_ms2="10", protein_pg_level="protein_names_2")
            )
            self.assertEqual(wf["diann"]["scan_window"], 5)
            self.assertEqual(wf["diann"]["mass_acc"], 10)
            self.assertEqual(wf["diann"]["pg_level"], 2)

    def test_missing_required_key_raises(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "sushi_params.yml"
            partial = dict(SUSHI_FULL)
            del partial["scoring_qvalue"]  # required field, no default
            p.write_text(yaml.safe_dump(partial))
            with self.assertRaises(KeyError):
                parse_sushi_params(p)

    def test_result_validates_as_DIANNRunnerParams(self):
        with tempfile.TemporaryDirectory() as t:
            wf, _, _ = parse_sushi_params(self._write(Path(t)))
            DIANNRunnerParams.from_parsed(wf)  # exact key set matches extra="forbid"


class TestParseSushiDataset(unittest.TestCase):
    """SUSHI dataset adapter: normalize + derive raw dir under dataRoot."""

    def test_maps_thermo_raw_and_derives_raw_dir(self):
        with tempfile.TemporaryDirectory() as t:
            tsv = Path(t) / "input_dataset.tsv"
            pd.DataFrame(
                {
                    "Name": ["A", "B"],
                    "Thermo RAW [File]": ["p34486/x/a.raw", "p34486/x/b.raw"],
                    "Group [Factor]": ["g1", "g2"],
                }
            ).to_csv(tsv, sep="\t", index=False)
            df, raw_dir = parse_sushi_dataset(tsv, data_root="/data")
            self.assertEqual(list(df.columns), [COL_RELATIVE_PATH, COL_NAME])
            self.assertEqual(dataset_raw_basenames(df), ["a.raw", "b.raw"])
            self.assertEqual(str(raw_dir), "/data/p34486/x")

    def test_absolute_paths_need_no_data_root(self):
        with tempfile.TemporaryDirectory() as t:
            tsv = Path(t) / "ds.tsv"
            pd.DataFrame(
                {"Name": ["A"], "Thermo RAW [File]": ["/abs/raw/a.raw"]}
            ).to_csv(tsv, sep="\t", index=False)
            _, raw_dir = parse_sushi_dataset(tsv)
            self.assertEqual(str(raw_dir), "/abs/raw")

    def test_grouping_var_passthrough(self):
        with tempfile.TemporaryDirectory() as t:
            tsv = Path(t) / "ds.tsv"
            pd.DataFrame(
                {"Name": ["A"], "RAW": ["a.raw"], COL_GROUPING: ["x"]}
            ).to_csv(tsv, sep="\t", index=False)
            df, _ = parse_sushi_dataset(tsv)
            self.assertIn(COL_GROUPING, df.columns)

    def test_multiple_dirs_raises(self):
        with tempfile.TemporaryDirectory() as t:
            tsv = Path(t) / "ds.tsv"
            pd.DataFrame(
                {"Name": ["A", "B"], "Thermo RAW [File]": ["p1/a.raw", "p2/b.raw"]}
            ).to_csv(tsv, sep="\t", index=False)
            with self.assertRaises(ValueError):
                parse_sushi_dataset(tsv, data_root="/data")

    def test_missing_raw_column_raises(self):
        with tempfile.TemporaryDirectory() as t:
            tsv = Path(t) / "ds.tsv"
            pd.DataFrame({"Name": ["A"]}).to_csv(tsv, sep="\t", index=False)
            with self.assertRaises(KeyError):
                parse_sushi_dataset(tsv)


class TestApplyFasta(unittest.TestCase):
    def test_explicit_fasta_is_authoritative(self):
        wf = parse_flat_params(dict(FLAT))
        db = Path("/abs/realdb.fasta")
        order = Path("/abs/order.fasta")
        result = _apply_fasta(wf, [db, order], Path("work"))
        self.assertEqual(result, [db, order])
        self.assertEqual(Path(wf["fasta"]["database_path"]).name, "realdb.fasta")
        self.assertTrue(wf["fasta"]["use_custom_fasta"])

    def test_derive_skips_missing_or_empty_order_fasta(self):
        """Custom sequences ON but no staged order.fasta -> derive db only (no phantom path)."""
        wf = parse_flat_params(dict(FLAT))
        wf["fasta"]["use_custom_fasta"] = True
        with tempfile.TemporaryDirectory() as t:
            work = Path(t)
            (work / "input").mkdir()
            # order.fasta missing -> db only
            self.assertEqual(_apply_fasta(wf, [], work), [work / "input" / "db.fasta"])
            # order.fasta empty -> still db only
            (work / "input" / "order.fasta").write_text("", encoding="utf-8")
            self.assertEqual(_apply_fasta(wf, [], work), [work / "input" / "db.fasta"])

    def test_derive_includes_nonempty_order_fasta(self):
        wf = parse_flat_params(dict(FLAT))
        wf["fasta"]["use_custom_fasta"] = True
        with tempfile.TemporaryDirectory() as t:
            work = Path(t)
            (work / "input").mkdir()
            (work / "input" / "order.fasta").write_text(">c\nPEPTIDE\n", encoding="utf-8")
            self.assertEqual(
                _apply_fasta(wf, [], work),
                [work / "input" / "db.fasta", work / "input" / "order.fasta"],
            )


class TestSushiCliParsing(unittest.TestCase):
    """The sushi command takes --params/--dataset; raw-dir/fasta are optional."""

    def test_params_and_dataset_parse(self):
        command, bound, _ = app.parse_args(
            ["sushi", "--params", "p.yml", "--dataset", "d.tsv", "--work-dir", "w"]
        )
        self.assertIs(command, sushi)
        self.assertEqual(bound.arguments["params"], Path("p.yml"))
        self.assertEqual(bound.arguments["dataset"], Path("d.tsv"))

    def test_legacy_param_overrides_flag_rejected(self):
        # The mid-stream --param-overrides flag is gone; guard against it.
        with self.assertRaises(SystemExit):
            app.parse_args(
                ["sushi", "--params", "p.yml", "--dataset", "d.tsv", "--param-overrides", "o.yml"]
            )


def _make_sushi_fixture(root: Path) -> dict:
    """Lay out what EzAppDiann hands `run-diann sushi`: a sushi_params.yml (with
    readable keys + dataRoot + fasta_databases), an input_dataset.tsv with
    dataRoot-relative raw paths, and the actual raw files under dataRoot."""
    gstore = root / "gstore"
    raw = gstore / "p1"
    raw.mkdir(parents=True)
    (raw / "sampleA.raw").write_bytes(b"")
    (raw / "sampleB.raw").write_bytes(b"")

    db = root / "db.fasta"
    db.write_text(">sp|P1|X\nMKVL\n")

    dataset = root / "input_dataset.tsv"
    pd.DataFrame(
        {
            "Name": ["A", "B"],
            "Thermo RAW [File]": ["p1/sampleA.raw", "p1/sampleB.raw"],
            "Condition [Factor]": ["ctrl", "treat"],
        }
    ).to_csv(dataset, sep="\t", index=False)

    params = root / "sushi_params.yml"
    params.write_text(
        yaml.safe_dump(
            {
                **SUSHI_FULL,
                "dataRoot": str(gstore),
                "fasta_databases": str(db),
                "quantification_no_norm": "true",  # readable override
                "cores": "8",
            }
        )
    )
    work = root / "work"
    work.mkdir()
    return {"gstore": gstore, "db": db, "dataset": dataset, "params": params, "work": work}


class TestSushiEndToEnd(unittest.TestCase):
    """sushi(--params, --dataset) → derives raw-dir + fasta → materialized work dir.

    Snakemake is mocked, so this exercises the adapters → validate → prepare and
    the snakemake config, stopping just short of running DIA-NN.
    """

    def test_derives_inputs_and_materializes_workdir(self):
        with tempfile.TemporaryDirectory() as t:
            fx = _make_sushi_fixture(Path(t))
            with mock.patch(
                "diann_runner.prepare.subprocess.run",
                return_value=SimpleNamespace(returncode=0),
            ) as run_mock:
                rc = sushi(
                    params=fx["params"],
                    dataset=fx["dataset"],
                    work_dir=fx["work"],
                    output_dir=fx["work"],
                    cores=8,
                )
            self.assertEqual(rc, 0)

            # Readable override flowed through SUSHI_TO_DRUNNER → param_core → TOML.
            params = DIANNRunnerParams.from_toml(fx["work"] / "diann_runner_params.toml")
            self.assertTrue(params.diann.no_norm)

            # Dataset normalized + FASTA copied; no raw files copied in.
            ds = pd.read_csv(fx["work"] / "dataset.csv")
            self.assertEqual(dataset_raw_basenames(ds), ["sampleA.raw", "sampleB.raw"])
            self.assertTrue((fx["work"] / "input" / "db.fasta").is_file())
            self.assertFalse((fx["work"] / "input" / "raw").exists())

            # Raw dir derived as the external gstore folder → read-only /raw mount;
            # SUSHI must not register outputs.
            argv = run_mock.call_args.args[0]
            self.assertEqual(argv[0], "snakemake")
            # build_snakemake_config resolves the path (symlinks); compare resolved.
            self.assertIn(f"raw_file_dir={(fx['gstore'] / 'p1').resolve()}", argv)
            self.assertIn("raw_mount_target=/raw", argv)
            self.assertIn("register_outputs=False", argv)


if __name__ == "__main__":
    unittest.main()
