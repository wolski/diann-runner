
import tempfile
import unittest
import zipfile
import os
from pathlib import Path

from diann_runner.snakemake_helpers import (
    get_fasta_paths,
    parse_flat_params,
    write_outputs_yml,
    zip_diann_results,
)

class TestSnakemakeHelpers(unittest.TestCase):
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

    def test_get_fasta_paths_requires_selected_custom_fasta(self):
        original_dir = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                fasta_config = {
                    "database_path": "input/database.fasta",
                    "use_custom_fasta": True,
                }

                with self.assertRaises(FileNotFoundError):
                    get_fasta_paths(fasta_config)

                Path("input").mkdir()
                Path("input/order.fasta").write_text("", encoding="utf-8")
                with self.assertRaises(ValueError):
                    get_fasta_paths(fasta_config)

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
            '11a_diann_protein_pg_level': 'protein_names_1',
            '11b_diann_protein_relaxed_prot_inf': 'true',
            '12a_diann_quantification_reanalyse': 'true',
            '12b_diann_quantification_no_norm': 'false',
            '99_other_verbose': '1',
            '98_diann_binary': 'diann-docker',
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
            '11a_diann_protein_pg_level': 'protein_names_1',
            '11b_diann_protein_relaxed_prot_inf': 'true',
            '12a_diann_quantification_reanalyse': 'true',
            '12b_diann_quantification_no_norm': 'false',
            '99_other_verbose': '1',
            '98_diann_binary': 'diann-docker',
            '05_diann_is_dda': 'false',
            '03_fasta_database_path': '/path/to/fasta',
            '03_fasta_use_custom': 'false',
            '05b_diann_scan_window': '8'
        }
        
        params = parse_flat_params(flat_params)
        self.assertEqual(params['diann']['scan_window'], 8)

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
            '11a_diann_protein_pg_level': 'protein_names_1',
            '11b_diann_protein_relaxed_prot_inf': 'true',
            '12a_diann_quantification_reanalyse': 'true',
            '12b_diann_quantification_no_norm': 'false',
            '99_other_verbose': '1',
            '98_diann_binary': 'diann-docker',
            '05_diann_is_dda': 'false',
            '03_fasta_database_path': '/path/to/fasta',
            '03_fasta_use_custom': 'false',
        }
        
        params = parse_flat_params(flat_params)
        self.assertEqual(params['diann']['scan_window'], 'AUTO')
