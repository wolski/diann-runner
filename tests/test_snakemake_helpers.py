
import unittest
from diann_runner.snakemake_helpers import parse_flat_params

class TestSnakemakeHelpers(unittest.TestCase):
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
            '09_diann_mass_acc_ms2': 'None',
            '09_diann_mass_acc_ms1': 'None',
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
            '09_diann_mass_acc_ms2': 'None',
            '09_diann_mass_acc_ms1': 'None',
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
            '09_diann_mass_acc_ms2': 'None',
            '09_diann_mass_acc_ms1': 'None',
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
