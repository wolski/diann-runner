"""Guards create_diann_workflow's nested-params -> flat DiannWorkflow mapping.

create_diann_workflow is the only nested<->flat boundary and was previously
unguarded. This verifies every kwarg is read from the correct category sub-dict,
including the previously-dropped ``no_peptidoforms`` (a latent bug fixed in the
rename) now reaching the emitted DIA-NN command.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from diann_runner.snakemake_helpers import create_diann_workflow, parse_flat_params

# Complete B-Fabric flat params (unified keys) with distinctive values so each
# category->attr mapping is individually observable.
FLAT = {
    "pipeline_diann_version": "2.3.2",
    "pipeline_workflow_mode": "two_step",
    "pipeline_is_dda": "false",
    "pipeline_raw_converter": "native",
    "input_fasta_databases": "/data/db.fasta",
    "input_fasta_additional": "None",
    "input_fasta_use_custom": "false",
    "lib_digestion_cut": "K*,R*",
    "lib_digestion_missed_cleavages": "1",
    "lib_peptide_min_length": "7",
    "lib_peptide_max_length": "30",
    "lib_precursor_charge_min": "2",
    "lib_precursor_charge_max": "3",
    "lib_precursor_mz_min": "400",
    "lib_precursor_mz_max": "1500",
    "lib_fragment_mz_min": "200",
    "lib_fragment_mz_max": "1800",
    "lib_mods_variable": "--var-mods 1 --var-mod UniMod:35,15.994915,M",
    "lib_mods_unimod4": "true",
    "lib_mods_met_excision": "true",
    "lib_mods_no_peptidoforms": "true",
    "search_mass_acc_ms1": "AUTO",
    "search_mass_acc_ms2": "10",
    "search_mass_acc_unrelated_runs": "false",
    "search_scoring_qvalue": "0.01",
    "search_protein_pg_level": "2_genes",
    "search_protein_ids_to_names": "false",
    "quant_scan_window": "5",
    "quant_reanalyse": "true",
    "quant_no_norm": "false",
    "output_fragment_quant": "true",
    "output_include_libs": "false",
    "output_pmultiqc": "true",
    "advanced_freestyle": "None",
    "advanced_verbose": "1",
}
DEPLOY = {"threads": 8, "diann_docker_image": "diann:test"}


def _make(flat):
    params = parse_flat_params(flat)
    return create_diann_workflow(
        "123", "out-DIANN", "diann-temp",
        flat["input_fasta_databases"], params["lib"]["mods_variable"],
        params, DEPLOY,
    )


class TestCreateWorkflowMapping(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="diann_map_")
        self.cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_nested_params_map_to_correct_workflow_attrs(self):
        """Each DiannWorkflow attr must come from the right nested category."""
        wf = _make(FLAT)
        self.assertEqual(wf.no_peptidoforms, True)   # lib.mods_no_peptidoforms (C3 fix)
        self.assertEqual(wf.mass_acc, 10)            # search.mass_acc_ms2 -> --mass-acc
        self.assertEqual(wf.mass_acc_ms1, "AUTO")    # search.mass_acc_ms1
        self.assertEqual(wf.scan_window, 5)          # quant.scan_window -> --window
        self.assertEqual(wf.pg_level, 2)             # search.protein_pg_level=2_genes
        self.assertEqual(wf.export_quant, True)      # output.fragment_quant
        self.assertEqual(wf.is_dda, False)           # pipeline.is_dda
        self.assertEqual(wf.reanalyse, True)         # quant.reanalyse
        self.assertEqual(wf.no_norm, False)          # quant.no_norm
        self.assertEqual(wf.ids_to_names, False)     # search.protein_ids_to_names
        self.assertEqual(wf.unrelated_runs, False)   # search.mass_acc_unrelated_runs
        self.assertEqual(wf.cut, "K*,R*")            # lib.digestion_cut
        self.assertEqual(wf.missed_cleavages, 1)     # lib.digestion_missed_cleavages
        self.assertEqual(wf.min_pep_len, 7)          # lib.peptide_min_length
        self.assertEqual(wf.max_pr_charge, 3)        # lib.precursor_charge_max
        self.assertEqual(wf.verbose, 1)              # advanced.verbose
        self.assertEqual(wf.unimod4, True)           # lib.mods_unimod4
        self.assertEqual(wf.met_excision, True)      # lib.mods_met_excision

    def test_no_peptidoforms_flag_reaches_command(self):
        """The C3 fix: --no-peptidoforms (and the ms2/window mappings) reach the script."""
        wf = _make(FLAT)
        path = wf.generate_step_a_library(fasta_paths=FLAT["input_fasta_databases"], script_name="a.sh")
        content = Path(path).read_text()
        self.assertIn("--no-peptidoforms", content)
        self.assertIn("--mass-acc 10", content)
        self.assertIn("--window 5", content)

    def test_no_peptidoforms_off_omits_flag(self):
        """Negative control: the flag is conditional, not always emitted."""
        wf = _make(dict(FLAT, lib_mods_no_peptidoforms="false"))
        self.assertEqual(wf.no_peptidoforms, False)
        path = wf.generate_step_a_library(fasta_paths=FLAT["input_fasta_databases"], script_name="a2.sh")
        self.assertNotIn("--no-peptidoforms", Path(path).read_text())


if __name__ == "__main__":
    unittest.main()
