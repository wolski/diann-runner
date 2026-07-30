
import re
import tempfile
import unittest
import zipfile
import os
from pathlib import Path

from unittest.mock import patch

from diann_runner.snakemake_helpers import (
    discover_prolfqua_reports,
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


# prolfquapp 2.4.1 report names, as declared in its own qc_result/index.md.
PROLFQUA_241_REPORTS = {
    "DATASET": "dataset.csv",
    "QC_ABUNDANCES": "QC_ProteinAbundances_tabset.html",
    "QC_SAMPLE_SIZE": "QCandSSE_tabset.html",
    "QC_XLSX": "proteinAbundances_347812.xlsx",
}

# prolfquapp 2.2.8 wrote different filenames for the same two reports.
PROLFQUA_228_REPORTS = {
    "DATASET": "dataset.csv",
    "QC_ABUNDANCES": "proteinAbundances.html",
    "QC_SAMPLE_SIZE": "QC_sampleSizeEstimation.html",
    "QC_XLSX": "proteinAbundances_347812.xlsx",
}


def make_qc_result(parent: Path, reports: dict[str, str], write_manifest: bool = True) -> Path:
    """Create a qc_result dir as prolfquapp leaves it (index.md manifest + files)."""
    qc_dir = parent / "qc_result"
    qc_dir.mkdir(exist_ok=True)
    for target in reports.values():
        (qc_dir / target).write_text("report", encoding="utf-8")
    (qc_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    if write_manifest:
        lines = ["# QC Results", "", "## Available Reports", ""]
        lines += [f"- [{key}]({target})" for key, target in reports.items()]
        (qc_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")
    return qc_dir


BASE_FLAT_PARAMS = {
    'lib_mods_variable': 'None',
    'lib_mods_no_peptidoforms': 'false',
    'lib_mods_unimod4': 'true',
    'lib_mods_met_excision': 'true',
    'lib_peptide_min_length': '7',
    'lib_peptide_max_length': '30',
    'lib_precursor_charge_min': '2',
    'lib_precursor_charge_max': '3',
    'lib_precursor_mz_min': '400',
    'lib_precursor_mz_max': '1500',
    'lib_fragment_mz_min': '200',
    'lib_fragment_mz_max': '1800',
    'lib_digestion_cut': 'K*,R*',
    'lib_digestion_missed_cleavages': '1',
    'search_mass_acc_ms2': 'AUTO',
    'search_mass_acc_ms1': 'AUTO',
    'search_scoring_qvalue': '0.01',
    'search_protein_pg_level': '1_protein_names',
    'quant_reanalyse': 'true',
    'quant_no_norm': 'false',
    'output_fragment_quant': 'false',
    'advanced_verbose': '1',
    'pipeline_is_dda': 'false',
    'input_fasta_databases': '/path/to/fasta',
    'input_fasta_use_custom': 'false',
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
            qc_dir = make_qc_result(tmp_path, PROLFQUA_241_REPORTS)
            final_outputs = get_final_quantification_outputs(
                "out-DIANN", "347812", enable_step_c=True
            )

            write_result_index(
                tmp_path / "index.md",
                tmp_path / "index.html",
                workunit_id="347812",
                quant_dir=quant_dir,
                qc_dir=qc_dir,
                final_outputs=final_outputs,
                fasta_paths=[tmp_path / "input" / "db.fasta"],
                include_pmultiqc=True,
            )

            markdown = (tmp_path / "index.md").read_text(encoding="utf-8")
            html = (tmp_path / "index.html").read_text(encoding="utf-8")
            self.assertIn(
                "[Quality control overview (prolfqua)](qc_result/index.html)", markdown
            )
            self.assertIn(
                "[Interactive QC report (pmultiqc)]"
                "(pmultiqc_result/pmultiqc_diann_report.html)",
                markdown,
            )
            self.assertIn(
                "[DIA-NN report, native (parquet)]"
                "(out-DIANN_quantC/WU347812_report.parquet)",
                markdown,
            )
            # The DIA-NN QC PDF is grouped under QC Reports, not Data Files.
            self.assertIn("## QC Reports", markdown)
            self.assertIn(
                "[DIA-NN quality control report (PDF)]"
                "(out-DIANN_quantC/WU347812_qc_report.pdf)",
                markdown,
            )
            self.assertIn(
                "[Sample annotation table (CSV)](out-DIANN_quantC/dataset.csv)", markdown
            )
            self.assertIn(
                "[FASTA database: db.fasta](out-DIANN_quantC/db.fasta)", markdown
            )
            self.assertIn("pmultiqc_result/pmultiqc_diann_report.html", html)

            # Both sections are present, in order, in the markdown.
            self.assertIn("## QC Reports", markdown)
            self.assertIn("## Data Files", markdown)
            self.assertLess(
                markdown.index("## QC Reports"), markdown.index("## Data Files")
            )
            # Descriptions are emitted alongside the link.
            self.assertIn(
                "(qc_result/index.html) - Landing page linking all prolfqua",
                markdown,
            )

            # The HTML carries the section headers, description spans and charset.
            self.assertIn("<meta charset='UTF-8'>", html)
            self.assertIn("<h2>QC Reports</h2>", html)
            self.assertIn("<h2>Data Files</h2>", html)
            self.assertIn("<span class='desc'>", html)

    def test_write_result_index_renders_all_data_files_with_relative_quant_dir(self):
        """A relative quant_dir is used as-is, and every Data Files entry renders."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            final_outputs = get_final_quantification_outputs(
                "out-DIANN", "347812", enable_step_c=True
            )

            write_result_index(
                tmp_path / "index.md",
                tmp_path / "index.html",
                workunit_id="347812",
                quant_dir="out-DIANN_quantC",  # relative -> used verbatim
                qc_dir=make_qc_result(tmp_path, PROLFQUA_241_REPORTS),
                final_outputs=final_outputs,
                fasta_paths=[],
                include_pmultiqc=False,
            )

            markdown = (tmp_path / "index.md").read_text(encoding="utf-8")
            for label in (
                "DIA-NN report, native (parquet)",
                "DIA-NN report, protein-inferred (prozor, parquet)",
                "Protein group abundance matrix (TSV)",
                "DIA-NN run statistics (TSV)",
                "DIA-NN run log (text)",
                "Sample annotation table (CSV)",
            ):
                self.assertIn(f"[{label}]", markdown)
            # Relative quant_dir is used verbatim (not reduced to its basename).
            self.assertIn(
                "[Sample annotation table (CSV)](out-DIANN_quantC/dataset.csv)", markdown
            )

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
                qc_dir=make_qc_result(tmp_path, PROLFQUA_241_REPORTS),
                final_outputs=final_outputs,
                fasta_paths=[],
                include_pmultiqc=False,
            )

            markdown = (tmp_path / "index.md").read_text(encoding="utf-8")
            self.assertNotIn("pmultiqc", markdown)
            self.assertIn(
                "[DIA-NN report, native (parquet)]"
                "(out-DIANN_quantB/WU347812_report.parquet)",
                markdown,
            )

    def test_write_result_index_omits_prozor_when_no_digestion(self):
        """No-digestion runs bypass prozor: the prozor link must not appear, while
        the native report and other data files still do."""
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
                qc_dir=make_qc_result(tmp_path, PROLFQUA_241_REPORTS),
                final_outputs=final_outputs,
                fasta_paths=[],
                include_pmultiqc=False,
                include_prozor=False,
            )

            markdown = (tmp_path / "index.md").read_text(encoding="utf-8")
            self.assertNotIn("prozor", markdown)
            self.assertNotIn("protein-inferred", markdown)
            # The native report and other data files are still present.
            self.assertIn("[DIA-NN report, native (parquet)]", markdown)
            self.assertIn("[Protein group abundance matrix (TSV)]", markdown)
            self.assertIn("[DIA-NN run statistics (TSV)]", markdown)

    def test_write_result_index_links_prolfqua_reports_by_actual_filename(self):
        """Every QC Reports link must resolve to a file that exists in qc_result.

        prolfquapp renamed its reports in 2.4.1, which silently left the index
        pointing at 2.2.8 filenames. Both naming schemes must produce live links.
        """
        for label, reports in (
            ("2.4.1", PROLFQUA_241_REPORTS),
            ("2.2.8", PROLFQUA_228_REPORTS),
        ):
            with self.subTest(prolfquapp=label), tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                qc_dir = make_qc_result(tmp_path, reports)
                final_outputs = get_final_quantification_outputs(
                    "out-DIANN", "347812", enable_step_c=False
                )

                write_result_index(
                    tmp_path / "index.md",
                    tmp_path / "index.html",
                    workunit_id="347812",
                    quant_dir=tmp_path / "out-DIANN_quantB",
                    qc_dir=qc_dir,
                    final_outputs=final_outputs,
                    fasta_paths=[],
                )

                markdown = (tmp_path / "index.md").read_text(encoding="utf-8")
                self.assertIn(
                    f"[Protein abundance QC report (prolfqua)](qc_result/{reports['QC_ABUNDANCES']})",
                    markdown,
                )
                self.assertIn(
                    "[Sample size and power estimation (prolfqua)]"
                    f"(qc_result/{reports['QC_SAMPLE_SIZE']})",
                    markdown,
                )
                # No link into qc_result may dangle.
                for target in re.findall(r"\]\((qc_result/[^)]+)\)", markdown):
                    self.assertTrue(
                        (tmp_path / target).is_file(), f"dangling link: {target}"
                    )

    def test_discover_prolfqua_reports_excludes_non_reports(self):
        """Only existing HTML reports are linked; data files and index.html are not."""
        with tempfile.TemporaryDirectory() as tmpdir:
            qc_dir = make_qc_result(Path(tmpdir), PROLFQUA_241_REPORTS)

            targets = [target for _, target, _ in discover_prolfqua_reports(qc_dir)]

            self.assertEqual(
                targets,
                [
                    "qc_result/QC_ProteinAbundances_tabset.html",
                    "qc_result/QCandSSE_tabset.html",
                ],
            )

    def test_discover_prolfqua_reports_skips_declared_but_missing_report(self):
        """A report prolfquapp declared but did not write yields no link."""
        with tempfile.TemporaryDirectory() as tmpdir:
            qc_dir = make_qc_result(Path(tmpdir), PROLFQUA_241_REPORTS)
            (qc_dir / PROLFQUA_241_REPORTS["QC_SAMPLE_SIZE"]).unlink()

            targets = [target for _, target, _ in discover_prolfqua_reports(qc_dir)]

            self.assertEqual(targets, ["qc_result/QC_ProteinAbundances_tabset.html"])

    def test_discover_prolfqua_reports_falls_back_to_glob_without_manifest(self):
        """Without index.md the HTML reports are still found by globbing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            qc_dir = make_qc_result(
                Path(tmpdir), PROLFQUA_241_REPORTS, write_manifest=False
            )

            reports = discover_prolfqua_reports(qc_dir)

            self.assertEqual(
                [target for _, target, _ in reports],
                [
                    "qc_result/QC_ProteinAbundances_tabset.html",
                    "qc_result/QCandSSE_tabset.html",
                ],
            )
            # Unmapped keys fall back to the raw stem rather than being dropped.
            self.assertIn("QCandSSE_tabset (prolfqua)", [label for label, _, _ in reports])

    def test_get_fasta_paths_skips_missing_or_empty_order_fasta(self):
        """Custom sequences default ON: a missing/empty order.fasta is skipped, not fatal."""
        original_dir = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                fasta_config = {
                    "fasta_databases": ["input/database.fasta"],
                    "fasta_use_custom": True,
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
            'lib_mods_variable': 'None',
            'lib_mods_no_peptidoforms': 'false',
            'lib_mods_unimod4': 'true',
            'lib_mods_met_excision': 'true',
            'lib_peptide_min_length': '7',
            'lib_peptide_max_length': '30',
            'lib_precursor_charge_min': '2',
            'lib_precursor_charge_max': '3',
            'lib_precursor_mz_min': '400',
            'lib_precursor_mz_max': '1500',
            'lib_fragment_mz_min': '200',
            'lib_fragment_mz_max': '1800',
            'lib_digestion_cut': 'K*,R*',
            'lib_digestion_missed_cleavages': '1',
            'search_mass_acc_ms2': 'AUTO',
            'search_mass_acc_ms1': 'AUTO',
            'search_scoring_qvalue': '0.01',
            'search_protein_pg_level': '1_protein_names',
            'quant_reanalyse': 'true',
            'quant_no_norm': 'false',
            'advanced_verbose': '1',
            'pipeline_is_dda': 'false',
            'input_fasta_databases': '/path/to/fasta',
            'input_fasta_use_custom': 'false',
            'quant_scan_window': 'AUTO'
        }

        params = parse_flat_params(flat_params)
        self.assertEqual(params['quant']['scan_window'], 'AUTO')

    def test_parse_scan_window_integer(self):
        flat_params = {
            'lib_mods_variable': 'None',
            'lib_mods_no_peptidoforms': 'false',
            'lib_mods_unimod4': 'true',
            'lib_mods_met_excision': 'true',
            'lib_peptide_min_length': '7',
            'lib_peptide_max_length': '30',
            'lib_precursor_charge_min': '2',
            'lib_precursor_charge_max': '3',
            'lib_precursor_mz_min': '400',
            'lib_precursor_mz_max': '1500',
            'lib_fragment_mz_min': '200',
            'lib_fragment_mz_max': '1800',
            'lib_digestion_cut': 'K*,R*',
            'lib_digestion_missed_cleavages': '1',
            'search_mass_acc_ms2': 'AUTO',
            'search_mass_acc_ms1': 'AUTO',
            'search_scoring_qvalue': '0.01',
            'search_protein_pg_level': '1_protein_names',
            'quant_reanalyse': 'true',
            'quant_no_norm': 'false',
            'advanced_verbose': '1',
            'pipeline_is_dda': 'false',
            'input_fasta_databases': '/path/to/fasta',
            'input_fasta_use_custom': 'false',
            'quant_scan_window': '8'
        }

        params = parse_flat_params(flat_params)
        self.assertEqual(params['quant']['scan_window'], 8)

    def test_parse_diann_version_default(self):
        params = parse_flat_params(dict(BASE_FLAT_PARAMS))
        self.assertEqual(params['pipeline']['diann_version'], '2.3.2')

    def test_parse_diann_bin_is_internal_default(self):
        params = parse_flat_params(dict(BASE_FLAT_PARAMS))
        self.assertEqual(params['diann_bin'], 'diann-docker')

    def test_parse_diann_version_explicit(self):
        flat = dict(BASE_FLAT_PARAMS)
        flat['pipeline_diann_version'] = '2.5.0'
        params = parse_flat_params(flat)
        self.assertEqual(params['pipeline']['diann_version'], '2.5.0')

    def test_parse_raw_converter_native(self):
        # 'native' = no conversion, DIA-NN reads .raw directly. Renamed from
        # 'NO' so PyYAML doesn't booleanize the XML enum on unquoted load.
        flat = dict(BASE_FLAT_PARAMS)
        flat['pipeline_raw_converter'] = 'native'
        params = parse_flat_params(flat)
        self.assertEqual(params['pipeline']['raw_converter'], 'native')

    def test_parse_flat_params_full_contract(self):
        # Frozen expected output — locks the BFABRIC_TO_DRUNNER + param_core
        # refactor against any future drift in the shared transform core.
        expected = {
            'pipeline': {
                'diann_version': '2.3.2',
                'workflow_mode': 'two_step',
                'is_dda': False,
                'raw_converter': 'thermoraw',
            },
            'inputs': {
                'fasta_databases': ['/path/to/fasta'],
                'fasta_use_custom': False,
            },
            'lib': {
                'digestion_cut': 'K*,R*',
                'digestion_missed_cleavages': 1,
                'peptide_min_length': 7,
                'peptide_max_length': 30,
                'precursor_charge_min': 2,
                'precursor_charge_max': 3,
                'precursor_mz_min': 400,
                'precursor_mz_max': 1500,
                'fragment_mz_min': 200,
                'fragment_mz_max': 1800,
                'mods_variable': [],
                'mods_unimod4': True,
                'mods_met_excision': True,
                'mods_no_peptidoforms': False,
            },
            'search': {
                'mass_acc_ms1': 'AUTO',
                'mass_acc_ms2': 'AUTO',
                'mass_acc_unrelated_runs': False,
                'scoring_qvalue': 0.01,
                'protein_pg_level': 1,
                'protein_ids_to_names': False,
            },
            'quant': {
                'scan_window': 'AUTO',
                'reanalyse': True,
                'no_norm': False,
            },
            'output': {
                'fragment_quant': False,
                'include_libs': False,
                'pmultiqc': True,
            },
            'advanced': {
                'freestyle': [],
                'verbose': 1,
            },
            'cores': 24,
            'diann_bin': 'diann-docker',
            'library_predictor': 'diann',
            'enable_step_c': False,
        }
        self.assertEqual(parse_flat_params(dict(BASE_FLAT_PARAMS)), expected)

    def test_parse_flat_params_explicit_cores(self):
        params = parse_flat_params(dict(BASE_FLAT_PARAMS, cores='48'))
        self.assertEqual(params['cores'], 48)

    def test_parse_flat_params_no_digestion_sentinel(self):
        """AppRunner path: 'no digestion' -> empty digestion_cut (digestion off)."""
        flat = dict(BASE_FLAT_PARAMS, lib_digestion_cut='no digestion')
        parsed = parse_flat_params(flat)
        self.assertEqual(parsed['lib']['digestion_cut'], '')

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
        # Missing scan_window should default to AUTO
        flat_params = {
            'lib_mods_variable': 'None',
            'lib_mods_no_peptidoforms': 'false',
            'lib_mods_unimod4': 'true',
            'lib_mods_met_excision': 'true',
            'lib_peptide_min_length': '7',
            'lib_peptide_max_length': '30',
            'lib_precursor_charge_min': '2',
            'lib_precursor_charge_max': '3',
            'lib_precursor_mz_min': '400',
            'lib_precursor_mz_max': '1500',
            'lib_fragment_mz_min': '200',
            'lib_fragment_mz_max': '1800',
            'lib_digestion_cut': 'K*,R*',
            'lib_digestion_missed_cleavages': '1',
            'search_mass_acc_ms2': 'AUTO',
            'search_mass_acc_ms1': 'AUTO',
            'search_scoring_qvalue': '0.01',
            'search_protein_pg_level': '1_protein_names',
            'quant_reanalyse': 'true',
            'quant_no_norm': 'false',
            'advanced_verbose': '1',
            'pipeline_is_dda': 'false',
            'input_fasta_databases': '/path/to/fasta',
            'input_fasta_use_custom': 'false',
        }

        params = parse_flat_params(flat_params)
        self.assertEqual(params['quant']['scan_window'], 'AUTO')


CONFIG_WITH_BOTH_BLOCKS = """\
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
        self.assertNotIn("threads", deploy_dict)
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
                "images:\n  apptainer:\n    diann_docker_image: x\n"
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
