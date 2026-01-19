"""Markdown-based QC report generation for DIA-NN results.

Generates comprehensive QC reports by:
1. Saving individual figures as PDF files in a subfolder
2. Generating a Markdown document with explanatory text between figures
3. Optionally rendering to PDF using Pandoc + LaTeX
"""

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Annotated

import cyclopts
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import variation

from diann_runner.report_figures import (
    create_consistency_histograms,
    create_correlation_matrix,
    create_cv_analysis_plots,
    create_rt_heatmaps,
    create_run_statistics_plots,
    remove_common,
    save_figure,
)

app = cyclopts.App(
    name="diann-qc-report",
    help="Generate Markdown-based QC reports from DIA-NN outputs",
)


def _normalize_file_column(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize File.Name column for compatibility with DIA-NN 2.3+ parquet.

    DIA-NN 2.3+ parquet files use 'Run' instead of 'File.Name'.
    This function ensures the DataFrame has a 'File.Name' column.

    Args:
        df: DataFrame to normalize.

    Returns:
        DataFrame with 'File.Name' column.
    """
    if "File.Name" not in df.columns and "Run" in df.columns:
        df = df.rename(columns={"Run": "File.Name"})
    return df


def _compute_cv_stats(
    df: pd.DataFrame,
    matrix: pd.DataFrame,
    condition: str,
    files: pd.Series,
    prefix: str,
) -> None:
    """Compute CV statistics for a given matrix and update the stats DataFrame.

    Args:
        df: Stats DataFrame to update (modified in-place).
        matrix: Pivot table (precursors, protein groups, or genes).
        condition: Condition name to filter by.
        files: File names belonging to this condition.
        prefix: Column prefix ("Precursor", "PG", or "Gene").
    """
    matching_cols = [c for c in matrix.columns if c in list(files)]
    if len(matching_cols) == 0:
        return

    cvs = np.ma.filled(
        variation(matrix[files], axis=1, nan_policy="omit"), float("nan")
    )
    cvs[cvs == 0] = float("nan")

    df.loc[df["Condition"] == condition, f"{prefix}.CV"] = np.nanmedian(cvs)
    df.loc[df["Condition"] == condition, f"{prefix}.CV.20"] = len(cvs[cvs <= 0.2])
    df.loc[df["Condition"] == condition, f"{prefix}.CV.10"] = len(cvs[cvs <= 0.1])
    df.loc[df["Condition"] == condition, f"{prefix}.N"] = np.mean(
        matrix[files].count()
    ).astype(int)


def _load_report_data(stats: Path, main: Path) -> tuple[
    pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame
]:
    """Load and prepare data for report generation.

    Args:
        stats: Path to the stats TSV file.
        main: Path to the main report file (TSV or parquet).

    Returns:
        Tuple of (df, quant, pr, pg, genes) DataFrames.
    """
    df = pd.read_csv(stats, sep="\t")
    df.loc[:, "File.Name"] = remove_common(df["File.Name"])

    if str(main).endswith(".parquet"):
        quant = pd.read_parquet(main)
        quant = _normalize_file_column(quant)
    else:
        quant = pd.read_csv(main, sep="\t")
    quant = quant[quant["Q.Value"] <= 0.01].reset_index(drop=True)
    quant.loc[:, "File.Name"] = remove_common(quant["File.Name"])

    quant_pg = (
        quant[quant["PG.Q.Value"] <= 0.01][["File.Name", "Protein.Group", "PG.MaxLFQ"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    quant_gene = (
        quant[quant["GG.Q.Value"] <= 0.01][["File.Name", "Genes", "Genes.MaxLFQ"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    pr = quant.pivot_table(
        values=["Precursor.Normalised"],
        columns=["File.Name"],
        index=["Precursor.Id"],
        aggfunc="sum",
    )
    pg = quant_pg.pivot_table(
        values=["PG.MaxLFQ"],
        columns=["File.Name"],
        index=["Protein.Group"],
        aggfunc="sum",
    )
    genes = quant_gene.pivot_table(
        values=["Genes.MaxLFQ"],
        columns=["File.Name"],
        index=["Genes"],
        aggfunc="sum",
    )
    pr.columns, pg.columns, genes.columns = (
        pr.columns.droplevel(),
        pg.columns.droplevel(),
        genes.columns.droplevel(),
    )

    return df, quant, pr, pg, genes


def _compute_conditions_and_cvs(
    df: pd.DataFrame, pr: pd.DataFrame, pg: pd.DataFrame, genes: pd.DataFrame
) -> bool:
    """Compute CV statistics per condition.

    Args:
        df: Stats DataFrame to update.
        pr: Precursor pivot table.
        pg: Protein group pivot table.
        genes: Gene pivot table.

    Returns:
        True if conditions were successfully computed, False otherwise.
    """
    try:
        df["Replicate"] = [re.findall(r"\d+", file)[-1] for file in df["File.Name"]]
        df["Condition"] = [
            file[: file.rfind(re.findall(r"\d+", file)[-1])]
            + file[
                file.rfind(re.findall(r"\d+", file)[-1])
                + len(re.findall(r"\d+", file)[-1]) :
            ]
            for file in df["File.Name"]
        ]
        conditions = df["Condition"].unique()
        for col in ["Precursor.CV", "Precursor.CV.20", "Precursor.CV.10", "Precursor.N",
                    "PG.CV", "PG.CV.20", "PG.CV.10", "PG.N",
                    "Gene.CV", "Gene.CV.20", "Gene.CV.10", "Gene.N"]:
            df[col] = 0
        for condition in conditions:
            files = df["File.Name"][df["Condition"] == condition]
            _compute_cv_stats(df, pr, condition, files, "Precursor")
            _compute_cv_stats(df, pg, condition, files, "PG")
            _compute_cv_stats(df, genes, condition, files, "Gene")
        return True
    except (KeyError, IndexError, ValueError) as e:
        print(f"Cannot infer conditions/replicates: {e}")
        return False


# Section descriptions for the Markdown report
SECTION_DESCRIPTIONS = {
    "id_consistency": """
The identification consistency plots show the cumulative distribution of missing values
across all runs. Ideally, most identifications should have few missing values, indicating
consistent detection across samples. A steep curve rising early indicates good data
completeness.
""",
    "rt_heatmaps": """
These heatmaps visualize the relationship between predicted and observed retention times.
The left panel shows library iRT vs. observed RT, the middle panel shows predicted RT vs.
observed RT, and the right panel shows normalization factors across the RT range.
Good calibration is indicated by tight correlation along the diagonal.
""",
    "correlation_matrix": """
The correlation matrix shows pairwise Pearson correlations of log2-transformed protein
quantities between samples. High correlations (red colors) indicate good reproducibility.
Technical replicates should show very high correlation (>0.95), while biological
replicates typically show somewhat lower but still strong correlations.
""",
    "total_quantity": """
Total quantified intensity at 1% FDR. This should be relatively consistent across runs
in a well-controlled experiment. Large variations may indicate loading differences or
technical issues.
""",
    "ms1_signal": """
MS1 (survey scan) signal intensity. Higher values indicate more abundant precursors
detected at the MS1 level.
""",
    "ms2_signal": """
MS2 (fragmentation scan) signal intensity. This reflects the total signal from
fragmentation spectra used for identification and quantification.
""",
    "signal_ratios": """
Signal ratios help identify runs with unusual behavior. The Total quantity/MS2 ratio
reflects quantification efficiency, while the MS1/MS2 ratio can indicate differences
in fragmentation efficiency or scan timing.
""",
    "precursors": """
Number of precursors identified at 1% FDR. This is a key metric for data quality and
should be consistent across similar sample types.
""",
    "proteins": """
Number of unique proteins identified at 1% protein-level FDR. This represents the
proteome coverage achieved in each run.
""",
    "fwhm": """
Full Width at Half Maximum (FWHM) of chromatographic peaks. Narrower peaks (lower FWHM)
indicate better chromatographic separation. The FWHM in minutes reflects the actual
peak width, while FWHM in scans indicates how many MS2 scans cover each peak.
""",
    "rt_accuracy": """
Retention time prediction accuracy. Lower values indicate better RT calibration,
which improves identification confidence and enables better alignment across runs.
""",
    "mass_accuracy": """
Mass accuracy in parts per million (ppm) for MS1 and MS2 spectra. The plots show
both uncorrected and corrected values. Good mass accuracy (<5 ppm) is essential
for confident identification.
""",
    "peptide_characteristics": """
Average peptide length and charge state. These should be relatively consistent
across runs unless there are systematic differences in sample preparation or
instrument parameters.
""",
    "missed_cleavages": """
Average number of missed tryptic cleavages. Higher values may indicate incomplete
digestion or the presence of modified lysines/arginines that prevent cleavage.
""",
    "cv_analysis": """
Coefficient of Variation (CV) analysis across conditions. The plots show the number
of features with CV below different thresholds (10%, 20%) and the median CV.
Lower CVs indicate better quantitative reproducibility within conditions.
""",
}


def _generate_markdown(
    title: str,
    figures_dir: Path,
    figure_files: dict[str, str],
    has_cv_analysis: bool,
) -> str:
    """Generate the Markdown report content.

    Args:
        title: Report title.
        figures_dir: Path to the figures directory (relative to report.md).
        figure_files: Mapping of section names to figure filenames.
        has_cv_analysis: Whether CV analysis figures were generated.

    Returns:
        Markdown content as a string.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")

    md = f"""---
title: "{title}"
date: "{date_str}"
geometry: margin=2cm
---

# Quality Control Report

This report provides quality control metrics and visualizations for DIA-NN
mass spectrometry data analysis results.

"""

    # Identification consistency
    if "id_consistency" in figure_files:
        md += f"""## 1. Identification Consistency

{SECTION_DESCRIPTIONS['id_consistency'].strip()}

![Identification consistency]({figures_dir}/{figure_files['id_consistency']})

"""

    # RT heatmaps
    if "rt_heatmaps" in figure_files:
        md += f"""## 2. Retention Time Analysis

{SECTION_DESCRIPTIONS['rt_heatmaps'].strip()}

![RT heatmaps]({figures_dir}/{figure_files['rt_heatmaps']})

"""

    # Correlation matrix
    if "correlation_matrix" in figure_files:
        md += f"""## 3. Sample Correlation

{SECTION_DESCRIPTIONS['correlation_matrix'].strip()}

![Correlation matrix]({figures_dir}/{figure_files['correlation_matrix']})

"""

    # Run statistics section
    md += """## 4. Per-Run Statistics

The following plots show various metrics for each run in the experiment.

"""

    # Signal plots
    if "total_quantity" in figure_files:
        md += f"""### Total Quantity

{SECTION_DESCRIPTIONS['total_quantity'].strip()}

![Total quantity]({figures_dir}/{figure_files['total_quantity']})

"""

    if "ms1_signal" in figure_files:
        md += f"""### MS1 Signal

{SECTION_DESCRIPTIONS['ms1_signal'].strip()}

![MS1 signal]({figures_dir}/{figure_files['ms1_signal']})

"""

    if "ms2_signal" in figure_files:
        md += f"""### MS2 Signal

{SECTION_DESCRIPTIONS['ms2_signal'].strip()}

![MS2 signal]({figures_dir}/{figure_files['ms2_signal']})

"""

    # Ratios
    if "quantity_ms2_ratio" in figure_files or "ms1_ms2_ratio" in figure_files:
        md += f"""### Signal Ratios

{SECTION_DESCRIPTIONS['signal_ratios'].strip()}

"""
        if "quantity_ms2_ratio" in figure_files:
            md += f"""![Quantity/MS2 ratio]({figures_dir}/{figure_files['quantity_ms2_ratio']})

"""
        if "ms1_ms2_ratio" in figure_files:
            md += f"""![MS1/MS2 ratio]({figures_dir}/{figure_files['ms1_ms2_ratio']})

"""

    # Identifications
    if "precursors_identified" in figure_files:
        md += f"""### Precursor Identifications

{SECTION_DESCRIPTIONS['precursors'].strip()}

![Precursors identified]({figures_dir}/{figure_files['precursors_identified']})

"""

    if "proteins_identified" in figure_files:
        md += f"""### Protein Identifications

{SECTION_DESCRIPTIONS['proteins'].strip()}

![Proteins identified]({figures_dir}/{figure_files['proteins_identified']})

"""

    # Chromatography
    if "fwhm_rt" in figure_files or "fwhm_scans" in figure_files:
        md += f"""### Chromatographic Peak Width

{SECTION_DESCRIPTIONS['fwhm'].strip()}

"""
        if "fwhm_rt" in figure_files:
            md += f"""![FWHM (minutes)]({figures_dir}/{figure_files['fwhm_rt']})

"""
        if "fwhm_scans" in figure_files:
            md += f"""![FWHM (scans)]({figures_dir}/{figure_files['fwhm_scans']})

"""

    # RT accuracy
    if "rt_prediction_accuracy" in figure_files:
        md += f"""### Retention Time Prediction Accuracy

{SECTION_DESCRIPTIONS['rt_accuracy'].strip()}

![RT prediction accuracy]({figures_dir}/{figure_files['rt_prediction_accuracy']})

"""

    # Mass accuracy
    if "mass_accuracy_ms2" in figure_files or "mass_accuracy_ms1" in figure_files:
        md += f"""### Mass Accuracy

{SECTION_DESCRIPTIONS['mass_accuracy'].strip()}

"""
        if "mass_accuracy_ms2" in figure_files:
            md += f"""![MS2 mass accuracy]({figures_dir}/{figure_files['mass_accuracy_ms2']})

"""
        if "mass_accuracy_ms1" in figure_files:
            md += f"""![MS1 mass accuracy]({figures_dir}/{figure_files['mass_accuracy_ms1']})

"""

    # Peptide characteristics
    if "peptide_characteristics" in figure_files:
        md += f"""### Peptide Characteristics

{SECTION_DESCRIPTIONS['peptide_characteristics'].strip()}

![Peptide characteristics]({figures_dir}/{figure_files['peptide_characteristics']})

"""

    if "missed_cleavages" in figure_files:
        md += f"""### Missed Cleavages

{SECTION_DESCRIPTIONS['missed_cleavages'].strip()}

![Missed cleavages]({figures_dir}/{figure_files['missed_cleavages']})

"""

    # CV analysis
    if has_cv_analysis:
        md += f"""## 5. CV Analysis

{SECTION_DESCRIPTIONS['cv_analysis'].strip()}

"""
        cv_sections = [
            ("precursor_cv_counts", "Precursor CV Distribution"),
            ("precursor_cv_median", "Median Precursor CV"),
            ("pg_cv_counts", "Protein Group CV Distribution"),
            ("pg_cv_median", "Median Protein Group CV"),
            ("gene_cv_counts", "Gene Group CV Distribution"),
            ("gene_cv_median", "Median Gene Group CV"),
        ]
        for key, section_title in cv_sections:
            if key in figure_files:
                md += f"""### {section_title}

![{section_title}]({figures_dir}/{figure_files[key]})

"""

    return md


def _render_pdf(markdown_path: Path, output_path: Path) -> bool:
    """Render Markdown to PDF using pandoc.

    Args:
        markdown_path: Path to the Markdown file.
        output_path: Path for the output PDF.

    Returns:
        True if successful, False otherwise.
    """
    if shutil.which("pandoc") is None:
        print("Warning: pandoc not found. Skipping PDF generation.")
        print("Install pandoc to enable PDF rendering: brew install pandoc")
        return False

    try:
        subprocess.run(
            [
                "pandoc",
                str(markdown_path),
                "-o", str(output_path),
                "--pdf-engine=xelatex",
                "-V", "geometry:margin=2cm",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Warning: PDF generation failed: {e.stderr}")
        print("Make sure you have LaTeX installed (e.g., mactex-no-gui or basictex)")
        return False
    except FileNotFoundError:
        print("Warning: xelatex not found. Skipping PDF generation.")
        return False


@app.default
def generate(
    stats: Annotated[Path, cyclopts.Parameter(help="Path to the stats TSV file")],
    main_report: Annotated[Path, cyclopts.Parameter(help="Path to the main report file (TSV or parquet)")],
    output_dir: Annotated[Path, cyclopts.Parameter(help="Output directory for the report")] = Path("qc_report"),
    title: Annotated[str, cyclopts.Parameter(help="Report title")] = "DIA-NN QC Report",
    render_pdf: Annotated[bool, cyclopts.Parameter(help="Render Markdown to PDF using pandoc")] = True,
) -> None:
    """Generate comprehensive QC report with figures and explanatory text.

    Creates a Markdown report with individual figures saved as PDF files in a
    subfolder. Optionally renders the final report to PDF using pandoc.

    Args:
        stats: Path to the stats TSV file (e.g., report.stats.tsv).
        main_report: Path to the main report file (TSV or parquet).
        output_dir: Output directory for the report.
        title: Report title for the Markdown header.
        render_pdf: Whether to render the Markdown to PDF using pandoc.
    """
    print(f"Generating QC report from {stats} and {main_report}")
    print(f"Output directory: {output_dir}")

    # Create output directories
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(exist_ok=True)

    # Load data
    df, quant, pr, pg, genes = _load_report_data(stats, main_report)

    # Calculate missing value counts for histograms
    fnames = len(pg.columns)
    pr_ids = fnames - pr.count(axis=1)
    pg_ids = fnames - pg.count(axis=1)
    gene_ids = fnames - genes.count(axis=1)

    # Compute CV statistics
    has_cv_analysis = _compute_conditions_and_cvs(df, pr, pg, genes)

    # Track generated figures
    figure_files: dict[str, str] = {}
    figure_counter = 1

    # 1. Identification consistency
    fig = create_consistency_histograms(pr_ids, pg_ids, gene_ids, fnames, len(genes) > 0)
    if fig is not None:
        filename = f"{figure_counter:02d}_id_consistency.pdf"
        save_figure(fig, figures_dir / filename)
        figure_files["id_consistency"] = filename
        figure_counter += 1
        print(f"  Created: {filename}")

    # 2. RT heatmaps
    fig = create_rt_heatmaps(quant)
    if fig is not None:
        filename = f"{figure_counter:02d}_rt_heatmaps.pdf"
        save_figure(fig, figures_dir / filename)
        figure_files["rt_heatmaps"] = filename
        figure_counter += 1
        print(f"  Created: {filename}")

    # 3. Correlation matrix
    fig = create_correlation_matrix(pg)
    if fig is not None:
        filename = f"{figure_counter:02d}_correlation_matrix.pdf"
        save_figure(fig, figures_dir / filename)
        figure_files["correlation_matrix"] = filename
        figure_counter += 1
        print(f"  Created: {filename}")

    # 4. Run statistics
    run_stats_plots = create_run_statistics_plots(df)
    for fig, name in run_stats_plots:
        filename = f"{figure_counter:02d}_{name}.pdf"
        save_figure(fig, figures_dir / filename)
        figure_files[name] = filename
        figure_counter += 1
        print(f"  Created: {filename}")

    # 5. CV analysis
    if has_cv_analysis:
        cv_plots = create_cv_analysis_plots(df)
        for fig, name in cv_plots:
            filename = f"{figure_counter:02d}_{name}.pdf"
            save_figure(fig, figures_dir / filename)
            figure_files[name] = filename
            figure_counter += 1
            print(f"  Created: {filename}")

    # Generate Markdown
    markdown_content = _generate_markdown(title, Path("figures"), figure_files, has_cv_analysis)
    markdown_path = output_dir / "report.md"
    markdown_path.write_text(markdown_content)
    print(f"  Created: report.md")

    # Render PDF
    if render_pdf:
        pdf_path = output_dir / "report.pdf"
        if _render_pdf(markdown_path, pdf_path):
            print(f"  Created: report.pdf")

    # Close all matplotlib figures
    plt.close("all")

    print(f"\nReport generation complete. Output: {output_dir}")


def main() -> None:
    """Main entry point for the diann-qc-report command."""
    app()


if __name__ == "__main__":
    main()
