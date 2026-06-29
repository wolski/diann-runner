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
from diann_runner.run_diann_cli import _apply_fasta, _build_request, _load_flat_params, app, sushi
from diann_runner.snakemake_helpers import parse_flat_params
from diann_runner.sushi_adapter import parse_sushi_dataset, parse_sushi_params

FLAT = {
    "lib_mods_variable": "--var-mods 1 --var-mod UniMod:35,15.994915,M",
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
    "input_fasta_additional": "NONE",
    "input_fasta_use_custom": "false",
}

# SUSHI readable equivalent of FLAT (same values, readable keys). The SUSHI path
# carries every DIA-NN field via the GUI dump, so the full set is required — there
# is no longer a B-Fabric template to fill gaps.
SUSHI_FULL = {
    "lib_mods_variable": "--var-mods 1 --var-mod UniMod:35,15.994915,M",
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
}


class TestLoadFlatParams(unittest.TestCase):
    """AppRunner params.yml loading (unchanged)."""

    def test_params_block_with_registration(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "params.yml"
            p.write_text(yaml.safe_dump({"params": FLAT, "registration": {"workunit_id": "5", "container_id": "9"}}))
            flat, reg = _load_flat_params(p)
            self.assertEqual(flat["search_scoring_qvalue"], "0.01")
            self.assertEqual(reg["workunit_id"], "5")

    def test_bare_flat_mapping(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "params.yml"
            p.write_text(yaml.safe_dump(FLAT))
            flat, reg = _load_flat_params(p)
            self.assertEqual(flat["lib_digestion_cut"], "K*,R*")
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
                quant_no_norm="true",                # override template 'false'
                lib_peptide_min_length="8",          # override template '6'
                dataRoot="/srv/gstore/projects",
            )
            wf, fastas, data_root = parse_sushi_params(p)
            self.assertTrue(wf["quant"]["no_norm"])
            self.assertEqual(wf["lib"]["peptide_min_length"], 8)
            self.assertEqual(data_root, "/srv/gstore/projects")
            self.assertEqual(fastas, [])

    def test_fasta_databases_split_into_list(self):
        with tempfile.TemporaryDirectory() as t:
            p = self._write(Path(t), input_fasta_databases="/db/a.fasta,/db/b.fasta")
            _, fastas, _ = parse_sushi_params(p)
            self.assertEqual(fastas, [Path("/db/a.fasta"), Path("/db/b.fasta")])

    def test_matches_apprunner_for_equivalent_keys(self):
        """SUSHI_TO_DRUNNER and BFABRIC_TO_DRUNNER converge on identical internal
        params without sharing any key vocabulary. SUSHI_FULL mirrors FLAT, so the
        nested category dicts must be byte-identical (regression net against drift).
        Only `inputs` differs — FASTA selection is caller-specific (SUSHI carries it
        out-of-band, B-Fabric in the flat keys) — so it is compared separately."""
        with tempfile.TemporaryDirectory() as t:
            su_wf, _, _ = parse_sushi_params(self._write(Path(t)))
            ar_wf = parse_flat_params(dict(FLAT))
            for key in (
                "pipeline",
                "lib",
                "search",
                "quant",
                "output",
                "advanced",
                "diann_bin",
                "library_predictor",
                "enable_step_c",
            ):
                self.assertEqual(su_wf[key], ar_wf[key])

    def test_defaults_for_optional_keys(self):
        with tempfile.TemporaryDirectory() as t:
            wf, _, _ = parse_sushi_params(self._write(Path(t)))
            self.assertEqual(wf["quant"]["scan_window"], "AUTO")
            self.assertEqual(wf["pipeline"]["diann_version"], "2.3.2")
            self.assertIs(wf["search"]["protein_ids_to_names"], False)
            self.assertEqual(wf["pipeline"]["workflow_mode"], "two_step")
            self.assertEqual(wf["pipeline"]["raw_converter"], "thermoraw")
            self.assertEqual(wf["library_predictor"], "diann")
            self.assertIs(wf["enable_step_c"], False)
            self.assertIs(wf["output"]["include_libs"], False)
            self.assertIs(wf["output"]["pmultiqc"], True)

    def test_enable_step_c_override(self):
        with tempfile.TemporaryDirectory() as t:
            wf, _, _ = parse_sushi_params(self._write(Path(t), enable_step_c="true"))
            self.assertIs(wf["enable_step_c"], True)

    def test_hardcoded_invariants(self):
        with tempfile.TemporaryDirectory() as t:
            wf, _, _ = parse_sushi_params(self._write(Path(t)))
            self.assertEqual(wf["diann_bin"], "diann-docker")
            self.assertEqual(wf["inputs"], {"fasta_databases": [], "fasta_use_custom": False})

    def test_int_or_auto_and_pg_level_transforms(self):
        with tempfile.TemporaryDirectory() as t:
            wf, _, _ = parse_sushi_params(
                self._write(
                    Path(t),
                    quant_scan_window="5",
                    search_mass_acc_ms2="10",
                    search_protein_pg_level="2_genes",
                )
            )
            self.assertEqual(wf["quant"]["scan_window"], 5)
            self.assertEqual(wf["search"]["mass_acc_ms2"], 10)
            self.assertEqual(wf["search"]["protein_pg_level"], 2)

    def test_missing_required_key_raises(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "sushi_params.yml"
            partial = dict(SUSHI_FULL)
            del partial["search_scoring_qvalue"]  # required field, no default
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
            # The "Group [Factor]" column is mapped onto Grouping Var.
            self.assertEqual(
                list(df.columns), [COL_RELATIVE_PATH, COL_NAME, COL_GROUPING]
            )
            self.assertEqual(list(df[COL_GROUPING]), ["g1", "g2"])
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

    def test_explicit_grouping_var_wins_over_factor(self):
        # An explicit "Grouping Var" takes precedence over a "[Factor]" column.
        with tempfile.TemporaryDirectory() as t:
            tsv = Path(t) / "ds.tsv"
            pd.DataFrame(
                {
                    "Name": ["A"],
                    "RAW": ["a.raw"],
                    COL_GROUPING: ["x"],
                    "Condition [Factor]": ["y"],
                }
            ).to_csv(tsv, sep="\t", index=False)
            df, _ = parse_sushi_dataset(tsv)
            self.assertEqual(list(df[COL_GROUPING]), ["x"])

    def test_no_grouping_when_no_factor_column(self):
        # Datasets with only Name + raw (e.g. this run's input_dataset.tsv) carry
        # no grouping; prolfquapp QC supplies a single dummy group downstream.
        with tempfile.TemporaryDirectory() as t:
            tsv = Path(t) / "ds.tsv"
            pd.DataFrame(
                {"Name": ["A", "B"], "Thermo RAW [File]": ["p1/a.raw", "p1/b.raw"]}
            ).to_csv(tsv, sep="\t", index=False)
            df, _ = parse_sushi_dataset(tsv, data_root="/data")
            self.assertNotIn(COL_GROUPING, df.columns)

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
        self.assertEqual(Path(wf["inputs"]["fasta_databases"][0]).name, "realdb.fasta")
        self.assertTrue(wf["inputs"]["fasta_use_custom"])

    def test_derive_skips_missing_or_empty_order_fasta(self):
        """Custom sequences ON but no staged order.fasta -> derive db only (no phantom path)."""
        wf = parse_flat_params(dict(FLAT))
        wf["inputs"]["fasta_use_custom"] = True
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
        wf["inputs"]["fasta_use_custom"] = True
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


class TestRuntimeFlag(unittest.TestCase):
    """--docker pins the container runtime; default is apptainer."""

    def test_apprunner_docker_flag_parses(self):
        _, bound, _ = app.parse_args(
            ["apprunner", "--docker", "--work-dir", "w"]
        )
        self.assertTrue(bound.arguments["docker"])

    def test_apprunner_default_is_not_docker(self):
        _, bound, _ = app.parse_args(["apprunner", "--work-dir", "w"])
        # cyclopts omits unset args from bound.arguments; default is False
        self.assertFalse(bound.arguments.get("docker", False))

    def test_build_request_maps_docker_to_runtime(self):
        wf = parse_flat_params(dict(FLAT))
        req = _build_request(
            workflow_params=wf, dataset=Path("d.parquet"), raw_dir=Path("input/raw"),
            fastas=[Path("/abs/db.fasta")], work_dir=Path("w"), output_dir=None,
            cores=8, workunit_id="0", container_id="0", register_outputs=True,
            runtime="docker",
        )
        self.assertEqual(req.container_runtime, "docker")

    def test_build_request_defaults_runtime_none(self):
        wf = parse_flat_params(dict(FLAT))
        req = _build_request(
            workflow_params=wf, dataset=Path("d.parquet"), raw_dir=Path("input/raw"),
            fastas=[Path("/abs/db.fasta")], work_dir=Path("w"), output_dir=None,
            cores=8, workunit_id="0", container_id="0", register_outputs=True,
        )
        self.assertIsNone(req.container_runtime)

    def test_legacy_param_overrides_flag_rejected(self):
        # The mid-stream --param-overrides flag is gone; guard against it.
        with self.assertRaises(SystemExit):
            app.parse_args(
                ["sushi", "--params", "p.yml", "--dataset", "d.tsv", "--param-overrides", "o.yml"]
            )


def _make_sushi_fixture(root: Path) -> dict:
    """Lay out what EzAppDiann hands `run-diann sushi`: a sushi_params.yml (with
    readable keys + dataRoot + input_fasta_databases), an input_dataset.tsv with
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
                "input_fasta_databases": str(db),
                "quant_no_norm": "true",  # readable override
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
            self.assertTrue(params.quant.no_norm)

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
