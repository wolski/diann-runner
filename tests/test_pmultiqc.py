"""End-to-end check of the pmultiqc staging + MultiQC invocation.

Mirrors the `pmultiqc_diann_report` Snakemake rule: stage the native DIA-NN
parquet (renamed to report.parquet) and the run log (report.log.txt) into a
clean input dir, then run `multiqc --diann-plugin`. Uses a completed DIA-NN
output fixture (Result_WU347715.zip), never RAW. Skipped when `multiqc` is not
installed so the fast unit suite stays dependency-light.
"""

import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path

FIXTURE = Path(__file__).parent / "DIANN" / "Result_WU347715.zip"
PARQUET_MEMBER = "out-DIANN_quantB/WU347715_report.parquet"
LOG_MEMBER = "out-DIANN_quantB/diann_quantB.log.txt"


def _pmultiqc_multiqc() -> str | None:
    """Path to a multiqc whose pmultiqc plugin registers `--diann-plugin`.

    A bare multiqc on PATH is not enough — the runner needs the pmultiqc plugin
    (a first-class dependency). Gate on the option actually being offered so the
    test runs where the workflow can run and skips otherwise (e.g. a dev venv
    where `uv pip install -e .` has not pulled pmultiqc in yet)."""
    mq = shutil.which("multiqc")
    if not mq:
        return None
    help_txt = subprocess.run([mq, "--help"], capture_output=True, text=True).stdout
    return mq if "--diann-plugin" in help_txt else None


@unittest.skipUnless(_pmultiqc_multiqc(), "multiqc with pmultiqc plugin not installed")
@unittest.skipUnless(FIXTURE.exists(), f"fixture missing: {FIXTURE}")
class TestPmultiqcDiannReport(unittest.TestCase):
    """The rule must build a non-empty HTML from the parquet, never the TSV."""

    def _extract(self, dest: Path) -> tuple[Path, Path]:
        with zipfile.ZipFile(FIXTURE) as zf:
            zf.extract(PARQUET_MEMBER, dest)
            zf.extract(LOG_MEMBER, dest)
        return dest / PARQUET_MEMBER, dest / LOG_MEMBER

    def test_stages_parquet_and_builds_report(self):
        import tempfile

        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            parquet, runlog = self._extract(tmp)

            # Stage exactly as the rule does.
            staging = tmp / "pmultiqc_input"
            staging.mkdir()
            shutil.copy2(parquet, staging / "report.parquet")
            shutil.copy2(runlog, staging / "report.log.txt")

            # Regression guard: the prolfqua-format TSV must never be staged
            # (pmultiqc tries the *report.tsv pattern first and crashes on the
            # missing native Run column).
            self.assertEqual(list(staging.glob("*report.tsv")), [])

            result_dir = tmp / "pmultiqc_result"
            html = result_dir / "pmultiqc_diann_report.html"
            proc = subprocess.run(
                [
                    "multiqc", str(staging), "--diann-plugin",
                    "-o", str(result_dir),
                    "--filename", "pmultiqc_diann_report.html",
                    "--force",
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(
                proc.returncode, 0,
                msg=f"multiqc failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
            )
            self.assertTrue(html.exists(), f"report not created at {html}")
            self.assertGreater(html.stat().st_size, 0, "report is empty")


if __name__ == "__main__":
    unittest.main()
