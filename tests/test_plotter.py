"""Integration tests for plotter module."""

import os
import tempfile
from pathlib import Path

import pytest

from diann_runner.plotter import report

# Test data paths
TEST_DATA_DIR = Path(__file__).parent / "bfabric_integration/WU338923/work/out-DIANN_quantB"
STATS_FILE = TEST_DATA_DIR / "WU338923_report.stats.tsv"
REPORT_FILE = TEST_DATA_DIR / "WU338923_report.tsv"
PARQUET_FILE = TEST_DATA_DIR / "WU338923_report.parquet"


@pytest.fixture
def temp_pdf():
    """Create a temporary file for PDF output."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        yield f.name
    if os.path.exists(f.name):
        os.unlink(f.name)


class TestPlotterIntegration:
    """Integration tests for the plotter module."""

    @pytest.mark.skipif(not STATS_FILE.exists(), reason="Test data not available")
    def test_report_generates_pdf(self, temp_pdf):
        """Test that report() generates a valid PDF."""
        report(str(STATS_FILE), str(REPORT_FILE), temp_pdf)

        assert os.path.exists(temp_pdf)
        assert os.path.getsize(temp_pdf) > 0

        # Verify it's a PDF (check magic bytes)
        with open(temp_pdf, "rb") as f:
            header = f.read(4)
        assert header == b"%PDF"

    @pytest.mark.skipif(not STATS_FILE.exists(), reason="Test data not available")
    def test_report_with_parquet_input(self, temp_pdf):
        """Test that report() works with parquet input."""
        if not PARQUET_FILE.exists():
            pytest.skip("Parquet test file not available")

        report(str(STATS_FILE), str(PARQUET_FILE), temp_pdf)

        assert os.path.exists(temp_pdf)
        assert os.path.getsize(temp_pdf) > 0

        # Verify it's a PDF (check magic bytes)
        with open(temp_pdf, "rb") as f:
            header = f.read(4)
        assert header == b"%PDF"
