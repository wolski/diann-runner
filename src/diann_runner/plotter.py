#!/usr/bin/python3
"""QC plotting utilities for DIA-NN results.

Generates multi-page PDF reports with various quality control plots
including identification consistency, retention time accuracy, correlation
matrices, and per-run statistics.
"""

import re
import sys
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from scipy.stats import variation

# Import shared utilities and figure generation functions from report_figures
from diann_runner.report_figures import (
    create_consistency_histograms,
    create_correlation_matrix,
    create_cv_analysis_plots,
    create_rt_heatmaps,
    create_run_statistics_plots,
    remove_common,
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

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        # Suppress SmallSampleWarning - expected when conditions have few replicates
        warnings.filterwarnings("ignore", message=".*too small.*")
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


def _plot_consistency_histograms(
    pdf: PdfPages,
    pr_ids: pd.Series,
    pg_ids: pd.Series,
    gene_ids: pd.Series,
    fnames: int,
    genes: pd.DataFrame,
) -> None:
    """Plot identification consistency histograms (CDFs) for precursors, proteins, genes."""
    fig = create_consistency_histograms(pr_ids, pg_ids, gene_ids, fnames, len(genes) > 0)
    if fig is not None:
        pdf.savefig(fig)
        plt.close(fig)


def _plot_rt_heatmaps(pdf: PdfPages, quant: pd.DataFrame) -> None:
    """Plot retention time and normalization factor heatmaps."""
    fig = create_rt_heatmaps(quant)
    if fig is not None:
        pdf.savefig(fig)
        plt.close(fig)


def _plot_run_statistics(pdf: PdfPages, df: pd.DataFrame) -> None:
    """Plot per-run statistics bar plots."""
    plots = create_run_statistics_plots(df)
    for fig, _ in plots:
        pdf.savefig(fig)
        plt.close(fig)


def _plot_cv_analysis(pdf: PdfPages, df: pd.DataFrame) -> None:
    """Plot CV analysis bar plots for precursors, protein groups, and genes."""
    plots = create_cv_analysis_plots(df)
    for fig, _ in plots:
        pdf.savefig(fig)
        plt.close(fig)


def _load_report_data(stats: str, main: str) -> tuple[
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

    if main.endswith(".parquet"):
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


def report(stats: str, main: str, out: str) -> None:
    """Generate a QC report PDF from DIA-NN output files.

    Args:
        stats: Path to the stats TSV file (e.g., report.stats.tsv).
        main: Path to the main report file (TSV or parquet).
        out: Path for the output PDF file.
    """
    print(f"Generating report. Stats, main report, output file: {stats}, {main}, {out}")

    # Load and prepare data
    df, quant, pr, pg, genes = _load_report_data(stats, main)

    # Calculate missing value counts for histograms
    fnames = len(pg.columns)
    pr_ids = fnames - pr.count(axis=1)
    pg_ids = fnames - pg.count(axis=1)
    gene_ids = fnames - genes.count(axis=1)

    # Compute CV statistics per condition
    skip_conditions = False
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
            df[col] = 0.0
        for condition in conditions:
            files = df["File.Name"][df["Condition"] == condition]
            _compute_cv_stats(df, pr, condition, files, "Precursor")
            _compute_cv_stats(df, pg, condition, files, "PG")
            _compute_cv_stats(df, genes, condition, files, "Gene")
    except (KeyError, IndexError, ValueError) as e:
        print(f"Cannot infer conditions/replicates: {e}")
        skip_conditions = True

    # Generate PDF report
    with PdfPages(out) as pdf:
        _plot_consistency_histograms(pdf, pr_ids, pg_ids, gene_ids, fnames, genes)
        _plot_rt_heatmaps(pdf, quant)

        try:
            fig = create_correlation_matrix(pg)
            if fig is not None:
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
        except (KeyError, ValueError, TypeError, IndexError):
            pass

        _plot_run_statistics(pdf, df)

        if not skip_conditions:
            _plot_cv_analysis(pdf, df)


def main() -> None:
    """Main entry point for the diann-qc command."""
    report(sys.argv[1], sys.argv[2], sys.argv[3])


if __name__ == "__main__":
    main()
