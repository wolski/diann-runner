
import tempfile
import unittest
import zipfile
import os
from pathlib import Path

from unittest.mock import patch

from diann_runner.snakemake_helpers import (
    get_diann_input_dependency,
    get_diann_input_path,
    get_fasta_paths,
    get_final_quantification_outputs,
    load_deploy_config,
    parse_flat_params,
    resolve_diann_docker_image,
    resolve_raw_converter_image,
    write_result_index,
    write_outputs_yml,
    zip_diann_results,
)


BASE_FLAT_PARAMS = {
    '06a_diann_mods_variable': 'None',
    '06b_diann_mods_no_peptidoforms': 'false',
    '06c_diann_mods_unimod4': 'true',
    '06d_diann_mods_met_excision': 'true',
    '07_diann_peptide_min_length': '7',
    '07_diann_peptide_max_length': '30',
    '07_diann_peptide_precursor_charge_min': '2',
    '07_diann_peptide_precursor_charge_max': '3',
    '07_diann_peptide_precursor_mz_min': '400',
    '07_diann_peptide_precursor_mz_max': '1500',
    '07_diann_peptide_fragment_mz_min': '200',
    '07_diann_peptide_fragment_mz_max': '1800',
    '08_diann_digestion_cut': 'K*,R*',
    '08_diann_digestion_missed_cleavages': '1',
    '09_diann_mass_acc_ms2': 'AUTO',
    '09_diann_mass_acc_ms1': 'AUTO',
    '10_diann_scoring_qvalue': '0.01',
    '11a_diann_protein_pg_level': '1_protein_names',
    '12a_diann_quantification_reanalyse': 'true',
    '12b_diann_quantification_no_norm': 'false',
    '12c_diann_quantification_export_quant': 'false',
    '99_other_verbose': '1',
    '05_diann_is_dda': 'false',
    '03_fasta_database_path': '/path/to/fasta',
    '03_fasta_use_custom': 'false',
}

class TestSnakemakeHelpers(unittest.TestCase):
    def test_convert_d_zip_validation_path_is_wildcard_callable(self):
        snakefile = (
            Path(__file__).parents[1]
            / "src"
            / "diann_runner"
            / "Snakefile.DIANN3step.smk"
        )
        content = snakefile.read_text(encoding="utf-8")

        self.assertIn('folder = lambda wildcards: CONVERTED_DIR / f"{wildcards.sample}.d"', content)
        self.assertNotIn('folder = CONVERTED_DIR / "{sample}.d"', content)

    def test_zip_diann_results_includes_extra_files_at_archive_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            output_dir = tmp_path / "out-DIANN_quantC"
            output_dir.mkdir()
            (output_dir / "report.tsv").write_text("protein\tquantity\n", encoding="utf-8")
            (output_dir / "report-lib.parquet").write_text("library", encoding="utf-8")
            dataset_csv = tmp_path / "dataset.csv"
            dataset_csv.write_text("sample,condition\nsample1,A\n", encoding="utf-8")

            zip_path = tmp_path / "Result_WUTEST.zip"
            zip_diann_results(str(output_dir), str(zip_path), extra_files=[dataset_csv])

            with zipfile.ZipFile(zip_path) as zip_file:
                names = set(zip_file.namelist())

            self.assertIn("out-DIANN_quantC/report.tsv", names)
            self.assertIn("dataset.csv", names)
            self.assertNotIn("out-DIANN_quantC/report-lib.parquet", names)

    def test_zip_diann_results_includes_extra_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            output_dir = tmp_path / "out-DIANN_quantC"
            output_dir.mkdir()
            (output_dir / "WU1_report.tsv").write_text("protein\tquantity\n", encoding="utf-8")
            qc_dir = tmp_path / "qc_result"
            qc_dir.mkdir()
            (qc_dir / "dataset.csv").write_text("sample,condition\nsample1,A\n", encoding="utf-8")

            zip_path = tmp_path / "Result_WUTEST.zip"
            zip_diann_results(str(output_dir), str(zip_path), extra_dirs=[qc_dir])

            with zipfile.ZipFile(zip_path) as zip_file:
                names = set(zip_file.namelist())

            self.assertIn("out-DIANN_quantC/WU1_report.tsv", names)
            self.assertIn("qc_result/dataset.csv", names)

    def test_write_outputs_yml_can_register_single_combined_zip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            zip_path = tmp_path / "Result_WUTEST.zip"
            zip_path.write_text("zip", encoding="utf-8")
            outputs_yml = tmp_path / "outputs.yml"

            write_outputs_yml(str(outputs_yml), str(zip_path))

            content = outputs_yml.read_text(encoding="utf-8")
            self.assertIn("Result_WUTEST.zip", content)
            self.assertEqual(content.count("store_entry_path:"), 1)

    def test_write_result_index_links_key_outputs_conditionally(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            quant_dir = tmp_path / "out-DIANN_quantC"
            quant_dir.mkdir()
            (quant_dir / "db.fasta").write_text(">x\nPEPTIDE\n", encoding="utf-8")
            final_outputs = get_final_quantification_outputs(
                "out-DIANN", "347812", enable_step_c=True
            )

            write_result_index(
                tmp_path / "index.md",
                tmp_path / "index.html",
                workunit_id="347812",
                quant_dir=quant_dir,
                final_outputs=final_outputs,
                fasta_paths=[tmp_path / "input" / "db.fasta"],
                include_pmultiqc=True,
            )

            markdown = (tmp_path / "index.md").read_text(encoding="utf-8")
            html = (tmp_path / "index.html").read_text(encoding="utf-8")
            self.assertIn("[prolfqua QC overview](qc_result/index.html)", markdown)
            self.assertIn(
                "[pmultiqc DIA-NN report](pmultiqc_result/pmultiqc_diann_report.html)",
                markdown,
            )
            self.assertIn(
                "[Native DIA-NN report parquet](out-DIANN_quantC/WU347812_report.parquet)",
                markdown,
            )
            self.assertIn("[Dataset](out-DIANN_quantC/dataset.csv)", markdown)
            self.assertIn("[FASTA: db.fasta](out-DIANN_quantC/db.fasta)", markdown)
            self.assertIn("pmultiqc_result/pmultiqc_diann_report.html", html)

    def test_write_result_index_omits_pmultiqc_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            final_outputs = get_final_quantification_outputs(
                "out-DIANN", "347812", enable_step_c=False
            )

            write_result_index(
                tmp_path / "index.md",
                tmp_path / "index.html",
                workunit_id="347812",
                quant_dir=tmp_path / "out-DIANN_quantB",
                final_outputs=final_outputs,
                fasta_paths=[],
                include_pmultiqc=False,
            )

            markdown = (tmp_path / "index.md").read_text(encoding="utf-8")
            self.assertNotIn("pmultiqc", markdown)
            self.assertIn(
                "[Native DIA-NN report parquet](out-DIANN_quantB/WU347812_report.parquet)",
                markdown,
            )

    def test_get_fasta_paths_skips_missing_or_empty_order_fasta(self):
        """Custom sequences default ON: a missing/empty order.fasta is skipped, not fatal."""
        original_dir = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                fasta_config = {
                    "database_path": "input/database.fasta",
                    "use_custom_fasta": True,
                }

                # order.fasta missing -> skipped, database FASTA only (no raise)
                self.assertEqual(get_fasta_paths(fasta_config), ["input/database.fasta"])

                Path("input").mkdir()
                Path("input/order.fasta").write_text("", encoding="utf-8")
                # order.fasta empty -> skipped, database FASTA only (no raise)
                self.assertEqual(get_fasta_paths(fasta_config), ["input/database.fasta"])

                # order.fasta non-empty -> included
                Path("input/order.fasta").write_text(">custom\nPEPTIDE\n", encoding="utf-8")
                self.assertEqual(
                    get_fasta_paths(fasta_config),
                    ["input/database.fasta", "input/order.fasta"],
                )
            finally:
                os.chdir(original_dir)

    def test_parse_scan_window_auto(self):
        flat_params = {
            '06a_diann_mods_variable': 'None',
            '06b_diann_mods_no_peptidoforms': 'false',
            '06c_diann_mods_unimod4': 'true',
            '06d_diann_mods_met_excision': 'true',
            '07_diann_peptide_min_length': '7',
            '07_diann_peptide_max_length': '30',
            '07_diann_peptide_precursor_charge_min': '2',
            '07_diann_peptide_precursor_charge_max': '3',
            '07_diann_peptide_precursor_mz_min': '400',
            '07_diann_peptide_precursor_mz_max': '1500',
            '07_diann_peptide_fragment_mz_min': '200',
            '07_diann_peptide_fragment_mz_max': '1800',
            '08_diann_digestion_cut': 'K*,R*',
            '08_diann_digestion_missed_cleavages': '1',
            '09_diann_mass_acc_ms2': 'AUTO',
            '09_diann_mass_acc_ms1': 'AUTO',
            '10_diann_scoring_qvalue': '0.01',
            '11a_diann_protein_pg_level': '1_protein_names',
            '12a_diann_quantification_reanalyse': 'true',
            '12b_diann_quantification_no_norm': 'false',
            '99_other_verbose': '1',
            '05_diann_is_dda': 'false',
            '03_fasta_database_path': '/path/to/fasta',
            '03_fasta_use_custom': 'false',
            '05b_diann_scan_window': 'AUTO'
        }
        
        params = parse_flat_params(flat_params)
        self.assertEqual(params['diann']['scan_window'], 'AUTO')

    def test_parse_scan_window_integer(self):
        flat_params = {
            '06a_diann_mods_variable': 'None',
            '06b_diann_mods_no_peptidoforms': 'false',
            '06c_diann_mods_unimod4': 'true',
            '06d_diann_mods_met_excision': 'true',
            '07_diann_peptide_min_length': '7',
            '07_diann_peptide_max_length': '30',
            '07_diann_peptide_precursor_charge_min': '2',
            '07_diann_peptide_precursor_charge_max': '3',
            '07_diann_peptide_precursor_mz_min': '400',
            '07_diann_peptide_precursor_mz_max': '1500',
            '07_diann_peptide_fragment_mz_min': '200',
            '07_diann_peptide_fragment_mz_max': '1800',
            '08_diann_digestion_cut': 'K*,R*',
            '08_diann_digestion_missed_cleavages': '1',
            '09_diann_mass_acc_ms2': 'AUTO',
            '09_diann_mass_acc_ms1': 'AUTO',
            '10_diann_scoring_qvalue': '0.01',
            '11a_diann_protein_pg_level': '1_protein_names',
            '12a_diann_quantification_reanalyse': 'true',
            '12b_diann_quantification_no_norm': 'false',
            '99_other_verbose': '1',
            '05_diann_is_dda': 'false',
            '03_fasta_database_path': '/path/to/fasta',
            '03_fasta_use_custom': 'false',
            '05b_diann_scan_window': '8'
        }
        
        params = parse_flat_params(flat_params)
        self.assertEqual(params['diann']['scan_window'], 8)

    def test_parse_diann_version_default(self):
        params = parse_flat_params(dict(BASE_FLAT_PARAMS))
        self.assertEqual(params['diann']['diann_version'], '2.3.2')

    def test_parse_diann_bin_is_internal_default(self):
        params = parse_flat_params(dict(BASE_FLAT_PARAMS))
        self.assertEqual(params['diann']['diann_bin'], 'diann-docker')

    def test_parse_diann_version_explicit(self):
        flat = dict(BASE_FLAT_PARAMS)
        flat['01_diann_version'] = '2.5.0'
        params = parse_flat_params(flat)
        self.assertEqual(params['diann']['diann_version'], '2.5.0')

    def test_parse_raw_converter_native(self):
        # 'native' = no conversion, DIA-NN reads .raw directly. Renamed from
        # 'NO' so PyYAML doesn't booleanize the XML enum on unquoted load.
        flat = dict(BASE_FLAT_PARAMS)
        flat['97_raw_converter'] = 'native'
        params = parse_flat_params(flat)
        self.assertEqual(params['raw_converter'], 'native')

    def test_parse_flat_params_full_contract(self):
        # Frozen expected output — locks the BFABRIC_TO_DRUNNER + param_core
        # refactor against any future drift in the shared transform core.
        expected = {
            'diann': {
                'diann_bin': 'diann-docker',
                'no_peptidoforms': False,
                'unimod4': True,
                'met_excision': True,
                'min_pep_len': 7,
                'max_pep_len': 30,
                'min_pr_charge': 2,
                'max_pr_charge': 3,
                'min_pr_mz': 400,
                'max_pr_mz': 1500,
                'min_fr_mz': 200,
                'max_fr_mz': 1800,
                'cut': 'K*,R*',
                'missed_cleavages': 1,
                'mass_acc': 'AUTO',
                'mass_acc_ms1': 'AUTO',
                'scan_window': 'AUTO',
                'qvalue': 0.01,
                'pg_level': 1,
                'ids_to_names': False,
                'reanalyse': True,
                'no_norm': False,
                'export_quant': False,
                'unrelated_runs': False,
                'freestyle': [],
                'verbose': 1,
                'is_dda': False,
                'diann_version': '2.3.2',
                'var_mods': [],
            },
            'fasta': {'database_path': '/path/to/fasta', 'use_custom_fasta': False},
            'var_mods': [],
            'library_predictor': 'diann',
            'enable_step_c': False,
            'workflow_mode': 'two_step',
            'raw_converter': 'thermoraw',
            'include_libs': False,
            'generate_pmultiqc': True,
        }
        self.assertEqual(parse_flat_params(dict(BASE_FLAT_PARAMS)), expected)

    def test_resolve_diann_docker_image_uses_version_map(self):
        deploy = {
            'diann_images': {
                '2.3.2': 'diann:2.3.2',
                '2.5.0': 'diann:2.5.0',
                '2.5.1': 'diann:2.5.1',
            },
            'diann_docker_image': 'diann:2.3.2',
        }
        self.assertEqual(resolve_diann_docker_image('2.5.0', deploy), 'diann:2.5.0')
        self.assertEqual(resolve_diann_docker_image('2.5.1', deploy), 'diann:2.5.1')
        self.assertEqual(resolve_diann_docker_image('2.3.2', deploy), 'diann:2.3.2')

    def test_resolve_diann_docker_image_falls_back_to_legacy(self):
        deploy = {'diann_docker_image': 'diann:2.3.2'}
        # Unknown version + no map -> legacy single image
        self.assertEqual(resolve_diann_docker_image('2.5.0', deploy), 'diann:2.3.2')
        # None version -> legacy
        self.assertEqual(resolve_diann_docker_image(None, deploy), 'diann:2.3.2')

    def test_resolve_diann_docker_image_raises_when_unresolvable(self):
        with self.assertRaises(KeyError):
            resolve_diann_docker_image('2.5.0', {})

    def test_resolve_raw_converter_image_uses_thermoraw_image(self):
        deploy = {
            'thermoraw_image': 'thermorawfileparser:2.0.0',
            'msconvert_docker': 'chambm/pwiz-skyline-i-agree-to-the-vendor-licenses',
        }
        self.assertEqual(
            resolve_raw_converter_image('thermoraw', deploy),
            'thermorawfileparser:2.0.0',
        )

    def test_resolve_raw_converter_image_uses_msconvert_image(self):
        deploy = {
            'thermoraw_image': 'thermorawfileparser:2.0.0',
            'msconvert_docker': 'chambm/pwiz-skyline-i-agree-to-the-vendor-licenses',
        }
        self.assertEqual(
            resolve_raw_converter_image('msconvert', deploy),
            'chambm/pwiz-skyline-i-agree-to-the-vendor-licenses',
        )
        self.assertEqual(
            resolve_raw_converter_image('msconvert-demultiplex', deploy),
            'chambm/pwiz-skyline-i-agree-to-the-vendor-licenses',
        )

    def test_resolve_raw_converter_image_raises_for_unknown_converter(self):
        with self.assertRaises(ValueError):
            resolve_raw_converter_image('unknown', {})

    def test_resolve_raw_converter_image_raises_for_native(self):
        # 'native' means DIA-NN reads .raw directly (no conversion) — it must
        # never resolve to a converter image; convert_raw never runs for it.
        with self.assertRaises(ValueError):
            resolve_raw_converter_image('native', {})

    def test_get_diann_input_path_matrix(self):
        raw_dir = Path('input/raw')
        cases = [
            # (converter, input_type, sample, expected_name)
            # 'native' = .raw passthrough (every image we ship reads .raw)
            ('native', 'raw', 's1', 's1.raw'),
            # every converter converts .raw -> mzML first
            ('thermoraw', 'raw', 's1', 's1.mzML'),
            ('msconvert', 'raw', 's1', 's1.mzML'),
            ('msconvert-demultiplex', 'raw', 's1', 's1.mzML'),
            # passthroughs / non-raw inputs ignore the converter
            ('native', 'mzML', 's1', 's1.mzML'),
            ('thermoraw', 'mzML', 's1', 's1.mzML'),
            ('native', 'd.zip', 's1', 's1.d'),
            ('thermoraw', 'd.zip', 's1', 's1.d'),
        ]
        for converter, input_type, sample, expected in cases:
            with self.subTest(converter=converter, input_type=input_type):
                result = get_diann_input_path(sample, input_type, converter, raw_dir)
                self.assertEqual(result, raw_dir / expected)

    def test_get_diann_input_dependency_uses_marker_for_dzip(self):
        raw_dir = Path('input/raw')
        result = get_diann_input_dependency('s1', 'd.zip', 'thermoraw', raw_dir)
        self.assertEqual(result, raw_dir / 's1.done')

    def test_get_diann_input_dependency_uses_diann_input_path_for_other_types(self):
        raw_dir = Path('input/raw')
        cases = [
            ('thermoraw', 'raw', 's1.mzML'),
            ('native', 'raw', 's1.raw'),
            ('thermoraw', 'mzML', 's1.mzML'),
        ]
        for converter, input_type, expected in cases:
            with self.subTest(converter=converter, input_type=input_type):
                result = get_diann_input_dependency('s1', input_type, converter, raw_dir)
                self.assertEqual(result, raw_dir / expected)

    def test_parse_scan_window_default(self):
        # Missing scan_window should default to 0
        flat_params = {
            '06a_diann_mods_variable': 'None',
            '06b_diann_mods_no_peptidoforms': 'false',
            '06c_diann_mods_unimod4': 'true',
            '06d_diann_mods_met_excision': 'true',
            '07_diann_peptide_min_length': '7',
            '07_diann_peptide_max_length': '30',
            '07_diann_peptide_precursor_charge_min': '2',
            '07_diann_peptide_precursor_charge_max': '3',
            '07_diann_peptide_precursor_mz_min': '400',
            '07_diann_peptide_precursor_mz_max': '1500',
            '07_diann_peptide_fragment_mz_min': '200',
            '07_diann_peptide_fragment_mz_max': '1800',
            '08_diann_digestion_cut': 'K*,R*',
            '08_diann_digestion_missed_cleavages': '1',
            '09_diann_mass_acc_ms2': 'AUTO',
            '09_diann_mass_acc_ms1': 'AUTO',
            '10_diann_scoring_qvalue': '0.01',
            '11a_diann_protein_pg_level': '1_protein_names',
            '12a_diann_quantification_reanalyse': 'true',
            '12b_diann_quantification_no_norm': 'false',
            '99_other_verbose': '1',
            '05_diann_is_dda': 'false',
            '03_fasta_database_path': '/path/to/fasta',
            '03_fasta_use_custom': 'false',
        }
        
        params = parse_flat_params(flat_params)
        self.assertEqual(params['diann']['scan_window'], 'AUTO')


CONFIG_WITH_BOTH_BLOCKS = """\
threads: 8
app_runner: fgcz_app_runner
images:
  docker:
    diann_images:
      "2.3.2": "diann:2.3.2"
    diann_docker_image: "diann:2.3.2"
    thermoraw_image: "thermorawfileparser:2.0.0"
    msconvert_docker: "chambm/pwiz-skyline-i-agree-to-the-vendor-licenses"
    prolfquapp_image: "prolfqua/prolfquapp:2.0.10"
  apptainer:
    diann_images:
      "2.3.2": "/opt/sif/diann_2.3.2.sif"
    diann_docker_image: "/opt/sif/diann_2.3.2.sif"
    thermoraw_image: "/opt/sif/thermorawfileparser_2.0.0.sif"
    msconvert_docker: "/opt/sif/pwiz.sif"
    prolfquapp_image: "/opt/sif/prolfquapp_2.0.10.sif"
"""


class TestLoadDeployConfig(unittest.TestCase):
    """load_deploy_config must auto-detect runtime and flatten the right block."""

    def setUp(self) -> None:
        # Pin the environment so the temp defaults_local.yml fixtures below are
        # the file under test. Otherwise on a server host (where /home/bfabric
        # exists) is_server_environment() is True and load_deploy_config reads
        # the packaged defaults_server.yml instead, masking these assertions.
        p = patch("diann_runner.snakemake_helpers.is_server_environment",
                  return_value=False)
        p.start()
        self.addCleanup(p.stop)

    def _write_config(self, tmp_path: Path) -> None:
        (tmp_path / "defaults_local.yml").write_text(CONFIG_WITH_BOTH_BLOCKS)

    @patch("diann_runner.container_utils.shutil.which",
           side_effect=lambda n: "/usr/bin/docker" if n == "docker" else None)
    def test_flattens_docker_block(self, _):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._write_config(tmp_path)
            deploy_dict = load_deploy_config(tmp_path)
        self.assertEqual(deploy_dict["container_runtime"], "docker")
        self.assertEqual(deploy_dict["diann_docker_image"], "diann:2.3.2")
        self.assertEqual(deploy_dict["thermoraw_image"], "thermorawfileparser:2.0.0")
        self.assertEqual(deploy_dict["threads"], 8)
        self.assertNotIn("images", deploy_dict)

    @patch("diann_runner.container_utils.shutil.which",
           side_effect=lambda n: "/usr/bin/apptainer" if n == "apptainer" else None)
    def test_flattens_apptainer_block(self, _):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._write_config(tmp_path)
            deploy_dict = load_deploy_config(tmp_path)
        self.assertEqual(deploy_dict["container_runtime"], "apptainer")
        self.assertEqual(deploy_dict["diann_docker_image"], "/opt/sif/diann_2.3.2.sif")
        self.assertEqual(deploy_dict["msconvert_docker"], "/opt/sif/pwiz.sif")

    @patch("diann_runner.container_utils.shutil.which",
           side_effect=lambda n: f"/usr/bin/{n}")  # both installed
    def test_apptainer_wins_when_both_installed(self, _):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._write_config(tmp_path)
            deploy_dict = load_deploy_config(tmp_path)
        self.assertEqual(deploy_dict["container_runtime"], "apptainer")

    @patch("diann_runner.container_utils.shutil.which",
           side_effect=lambda n: "/usr/bin/docker" if n == "docker" else None)
    def test_missing_runtime_block_raises(self, _):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "defaults_local.yml").write_text(
                "threads: 4\nimages:\n  apptainer:\n    diann_docker_image: x\n"
            )
            with self.assertRaises(KeyError):
                load_deploy_config(tmp_path)

    @patch("diann_runner.container_utils.shutil.which",
           side_effect=lambda n: "/usr/bin/apptainer" if n == "apptainer" else None)
    def test_explicit_container_runtime_overrides_detection(self, _):
        # apptainer is the only runtime on PATH, but the config pins docker:
        # the explicit key wins and the docker block is flattened.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "defaults_local.yml").write_text(
                "container_runtime: docker\n" + CONFIG_WITH_BOTH_BLOCKS
            )
            deploy_dict = load_deploy_config(tmp_path)
        self.assertEqual(deploy_dict["container_runtime"], "docker")
        self.assertEqual(deploy_dict["diann_docker_image"], "diann:2.3.2")

    @patch("diann_runner.container_utils.shutil.which",
           side_effect=lambda n: "/usr/bin/docker" if n == "docker" else None)
    def test_invalid_container_runtime_raises(self, _):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "defaults_local.yml").write_text(
                "container_runtime: podman\n" + CONFIG_WITH_BOTH_BLOCKS
            )
            with self.assertRaises(ValueError):
                load_deploy_config(tmp_path)


class TestFinalQuantificationOutputs(unittest.TestCase):
    """get_final_quantification_outputs after dropping the prolfqua-format TSV.

    The native parquet is the single report source; report_tsv is gone and a
    runlog key (for pmultiqc / the DIA-NN version badge) is exposed.
    """

    def test_step_c_outputs(self):
        out = get_final_quantification_outputs("out-DIANN", "347715", enable_step_c=True)
        self.assertEqual(
            out["report_parquet"], "out-DIANN_quantC/WU347715_report.parquet"
        )
        self.assertEqual(out["runlog"], "out-DIANN_quantC/diann_quantC.log.txt")
        # The prolfqua-format Run->File.Name TSV is no longer produced or exposed.
        self.assertNotIn("report_tsv", out)

    def test_step_b_outputs_when_step_c_disabled(self):
        out = get_final_quantification_outputs("out-DIANN", "347715", enable_step_c=False)
        self.assertEqual(
            out["report_parquet"], "out-DIANN_quantB/WU347715_report.parquet"
        )
        self.assertEqual(out["runlog"], "out-DIANN_quantB/diann_quantB.log.txt")
        self.assertNotIn("report_tsv", out)


if __name__ == "__main__":
    unittest.main()
