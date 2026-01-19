"""Tests for the qc_report module."""

import os
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from diann_runner.qc_report import generate, _generate_markdown, _render_pdf
from diann_runner.report_figures import (
    create_consistency_histograms,
    create_correlation_matrix,
    create_cv_analysis_plots,
    create_rt_heatmaps,
    create_run_statistics_plots,
    bar_plot,
    remove_common,
)

# Test data paths
TEST_DATA_DIR = Path(__file__).parent / "bfabric_integration/WU338923/work/out-DIANN_quantB"
STATS_FILE = TEST_DATA_DIR / "WU338923_report.stats.tsv"
REPORT_FILE = TEST_DATA_DIR / "WU338923_report.tsv"
PARQUET_FILE = TEST_DATA_DIR / "WU338923_report.parquet"


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestReportFigures:
    """Tests for report_figures.py functions."""

    def test_remove_common(self):
        """Test remove_common function."""
        # The function finds common prefix and suffix and removes both
        strs = ["prefix_sample1_suffix", "prefix_sample2_suffix", "prefix_sample3_suffix"]
        result = remove_common(strs)
        # Common prefix is "prefix_sample" and common suffix is "_suffix"
        # So only the varying parts remain: "1", "2", "3"
        assert result == ["1", "2", "3"]

    def test_remove_common_no_common(self):
        """Test remove_common with no common prefix/suffix."""
        strs = ["abc", "def", "ghi"]
        result = remove_common(strs)
        assert result == ["abc", "def", "ghi"]

    def test_remove_common_empty_list(self):
        """Test remove_common with empty list."""
        result = remove_common([])
        assert result == []

    def test_bar_plot_creates_figure(self):
        """Test that bar_plot returns a matplotlib Figure."""
        x = ["a", "b", "c"]
        y = [1.0, 2.0, 3.0]
        fig = bar_plot("Test", x, y)
        assert fig is not None
        assert hasattr(fig, "savefig")
        plt.close(fig)

    def test_create_consistency_histograms(self):
        """Test create_consistency_histograms function."""
        pr_ids = pd.Series([0, 1, 2, 3, 4])
        pg_ids = pd.Series([0, 0, 1, 1, 2])
        gene_ids = pd.Series([0, 0, 0, 1, 1])
        fnames = 5
        has_genes = True

        fig = create_consistency_histograms(pr_ids, pg_ids, gene_ids, fnames, has_genes)
        assert fig is not None
        plt.close(fig)

    def test_create_consistency_histograms_no_genes(self):
        """Test create_consistency_histograms with no genes."""
        pr_ids = pd.Series([0, 1, 2, 3, 4])
        pg_ids = pd.Series([0, 0, 1, 1, 2])
        gene_ids = pd.Series([])
        fnames = 5
        has_genes = False

        fig = create_consistency_histograms(pr_ids, pg_ids, gene_ids, fnames, has_genes)
        assert fig is not None
        plt.close(fig)


class TestMarkdownGeneration:
    """Tests for Markdown report generation."""

    def test_generate_markdown_basic(self):
        """Test basic Markdown generation."""
        figure_files = {
            "id_consistency": "01_id_consistency.pdf",
            "rt_heatmaps": "02_rt_heatmaps.pdf",
        }
        md = _generate_markdown(
            title="Test Report",
            figures_dir=Path("figures"),
            figure_files=figure_files,
            has_cv_analysis=False,
        )

        assert "Test Report" in md
        assert "## 1. Identification Consistency" in md
        assert "figures/01_id_consistency.pdf" in md
        assert "## 2. Retention Time Analysis" in md
        assert "figures/02_rt_heatmaps.pdf" in md

    def test_generate_markdown_with_cv_analysis(self):
        """Test Markdown generation with CV analysis."""
        figure_files = {
            "precursor_cv_counts": "20_precursor_cv_counts.pdf",
            "precursor_cv_median": "21_precursor_cv_median.pdf",
        }
        md = _generate_markdown(
            title="Test Report",
            figures_dir=Path("figures"),
            figure_files=figure_files,
            has_cv_analysis=True,
        )

        assert "## 5. CV Analysis" in md
        assert "Precursor CV Distribution" in md

    def test_generate_markdown_empty_figures(self):
        """Test Markdown generation with no figures."""
        md = _generate_markdown(
            title="Empty Report",
            figures_dir=Path("figures"),
            figure_files={},
            has_cv_analysis=False,
        )

        assert "Empty Report" in md
        assert "## 4. Per-Run Statistics" in md


class TestQCReportIntegration:
    """Integration tests for the qc_report module."""

    @pytest.mark.skipif(not STATS_FILE.exists(), reason="Test data not available")
    def test_generate_creates_output(self, temp_output_dir):
        """Test that generate() creates output files."""
        generate(
            stats=STATS_FILE,
            main_report=REPORT_FILE,
            output_dir=temp_output_dir,
            title="Test QC Report",
            render_pdf=False,  # Skip PDF rendering to avoid pandoc dependency
        )

        # Check that output directory was created
        figures_dir = temp_output_dir / "figures"
        assert figures_dir.exists()

        # Check that figures were created
        pdf_files = list(figures_dir.glob("*.pdf"))
        assert len(pdf_files) > 0

        # Check that Markdown was created
        markdown_file = temp_output_dir / "report.md"
        assert markdown_file.exists()
        content = markdown_file.read_text()
        assert "Test QC Report" in content

    @pytest.mark.skipif(not STATS_FILE.exists(), reason="Test data not available")
    def test_generate_with_parquet(self, temp_output_dir):
        """Test generate() with parquet input."""
        if not PARQUET_FILE.exists():
            pytest.skip("Parquet test file not available")

        generate(
            stats=STATS_FILE,
            main_report=PARQUET_FILE,
            output_dir=temp_output_dir,
            title="Parquet Test Report",
            render_pdf=False,
        )

        # Check that output files were created
        assert (temp_output_dir / "figures").exists()
        assert (temp_output_dir / "report.md").exists()

    @pytest.mark.skipif(not STATS_FILE.exists(), reason="Test data not available")
    def test_generate_figure_numbering(self, temp_output_dir):
        """Test that figures are numbered correctly."""
        generate(
            stats=STATS_FILE,
            main_report=REPORT_FILE,
            output_dir=temp_output_dir,
            title="Test Report",
            render_pdf=False,
        )

        figures_dir = temp_output_dir / "figures"
        pdf_files = sorted(figures_dir.glob("*.pdf"))

        # Check that files are numbered sequentially
        for i, pdf_file in enumerate(pdf_files, 1):
            expected_prefix = f"{i:02d}_"
            assert pdf_file.name.startswith(expected_prefix), f"Expected {pdf_file.name} to start with {expected_prefix}"


class TestPDFRendering:
    """Tests for PDF rendering functionality."""

    def test_render_pdf_missing_pandoc(self, temp_output_dir):
        """Test that missing pandoc is handled gracefully."""
        import shutil

        # Only run if pandoc is not available
        if shutil.which("pandoc") is not None:
            pytest.skip("Test only runs when pandoc is not installed")

        markdown_file = temp_output_dir / "test.md"
        markdown_file.write_text("# Test\n\nThis is a test.")

        pdf_file = temp_output_dir / "test.pdf"
        result = _render_pdf(markdown_file, pdf_file)

        assert result is False

    def test_render_pdf_with_pandoc(self, temp_output_dir):
        """Test PDF rendering with pandoc (if available)."""
        import shutil

        if shutil.which("pandoc") is None:
            pytest.skip("Pandoc not installed")

        markdown_file = temp_output_dir / "test.md"
        markdown_file.write_text("# Test\n\nThis is a test.")

        pdf_file = temp_output_dir / "test.pdf"
        result = _render_pdf(markdown_file, pdf_file)

        # Result depends on whether LaTeX is also available
        if result:
            assert pdf_file.exists()
            assert pdf_file.stat().st_size > 0
