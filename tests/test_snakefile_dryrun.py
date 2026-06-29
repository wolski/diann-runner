"""Smoke test: the Snakefile's module-level nested WORKFLOW_PARAMS access parses.

``snakemake -n`` executes the Snakefile's top-level code at parse time — including
the config bootstrap and the nested ``WORKFLOW_PARAMS["pipeline"|"inputs"|"lib"|
"output"|...]`` globals (Snakefile L80-91) introduced by the param reshape. A clean
dry-run therefore proves that nested indexing doesn't ``KeyError`` against a real
normalized TOML, which the Python unit tests (run blocks aside) cannot reach.

Skipped if snakemake is unavailable. Uses TOML mode (``load_workflow_params``) so
the params are loaded in the exact new 7-category shape, plus the shipped package
deploy config (``container_runtime=docker`` avoids host runtime auto-detection).
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

import diann_runner
from diann_runner.request import DIANNRunnerParams
from diann_runner.snakemake_helpers import parse_flat_params

SNAKEFILE = Path(diann_runner.__file__).parent / "Snakefile.DIANN3step.smk"

# A complete set of unified B-Fabric flat params (post-rename), used to write the
# normalized TOML the Snakefile reads.
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
    "lib_mods_no_peptidoforms": "false",
    "search_mass_acc_ms1": "AUTO",
    "search_mass_acc_ms2": "AUTO",
    "search_mass_acc_unrelated_runs": "false",
    "search_scoring_qvalue": "0.01",
    "search_protein_pg_level": "2_genes",
    "search_protein_ids_to_names": "false",
    "quant_scan_window": "AUTO",
    "quant_reanalyse": "true",
    "quant_no_norm": "false",
    "output_fragment_quant": "false",
    "output_include_libs": "false",
    "output_pmultiqc": "true",
    "advanced_freestyle": "None",
    "advanced_verbose": "1",
}


@unittest.skipUnless(find_spec("snakemake"), "snakemake not installed")
class TestSnakefileDryRun(unittest.TestCase):
    def test_dryrun_parses_nested_workflow_params(self):
        wd = Path(tempfile.mkdtemp(prefix="diann_smk_"))
        try:
            DIANNRunnerParams.from_parsed(parse_flat_params(FLAT)).to_toml(
                wd / "diann_runner_params.toml"
            )
            (wd / "input" / "raw").mkdir(parents=True)
            (wd / "input" / "raw" / "sample1.mzML").touch()  # detect_input_files needs >=1

            proc = subprocess.run(
                [
                    sys.executable, "-m", "snakemake",
                    "-s", str(SNAKEFILE), "-d", str(wd),
                    "-n", "-c1", "print_config_dict",
                    "--config", "container_runtime=docker", "workunit_id=0", "container_id=0",
                ],
                capture_output=True, text=True, timeout=300,
            )
            out = proc.stdout + proc.stderr
            self.assertEqual(
                proc.returncode, 0,
                f"snakemake dry-run failed (nested WORKFLOW_PARAMS access?):\n{out}",
            )
            self.assertNotIn("KeyError", out)
        finally:
            shutil.rmtree(wd, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
