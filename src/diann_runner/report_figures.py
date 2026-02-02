"""Figure generation functions for DIA-NN QC reports.

This module provides functions that create matplotlib Figure objects for various
QC plots. These functions are designed to be reusable for both PDF generation
and Markdown-based reports.
"""

import copy
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure


def split(obj: list[Any], n: int) -> list[list[Any]]:
    """Split a list into n approximately equal parts.

    Args:
        obj: List to split.
        n: Number of parts to split into.

    Returns:
        List of sublists.
    """
    res = []
    if n == 0:
        res.append(obj)
        return res
    pos = 0.0
    length = float(len(obj)) / float(n)
    while pos < len(obj):
        res.append(obj[int(pos) : int(pos + length)])
        pos += length
    return res


def max_prefix(strs: list[str]) -> str:
    """Find the longest common prefix among a list of strings.

    Args:
        strs: List of strings to analyze.

    Returns:
        The longest common prefix string.
    """
    if len(strs) == 0:
        return ""
    res = strs[0]
    for i in range(1, len(strs)):
        while not strs[i].startswith(res):
            res = res[:-1]
            if len(res) == 0:
                return ""
    return res


def max_suffix(strs: list[str]) -> str:
    """Find the longest common suffix among a list of strings.

    Args:
        strs: List of strings to analyze.

    Returns:
        The longest common suffix string.
    """
    rev = [s[::-1] for s in strs]
    return max_prefix(rev)


def remove_common(strs: list[str]) -> list[str]:
    """Remove common prefix and suffix from a list of strings.

    Args:
        strs: List of strings to process.

    Returns:
        List with common prefix and suffix removed from each string.
    """
    res = copy.deepcopy(strs)
    prefix = len(max_prefix(res))
    suffix = len(max_suffix(res))
    for i in range(len(res)):
        res[i] = res[i][prefix:-suffix] if suffix > 0 else res[i][prefix:]
    return res


def add_labels(bars: Any, al: int = 1) -> None:
    """Add value labels to bar chart.

    Args:
        bars: Matplotlib bar container.
        al: Alignment (0=left, 1=center, 2=right).
    """
    max_height = 0
    if al == 1:
        als = "center"
    elif al == 0:
        als = "left"
    else:
        als = "right"
    for b in bars:
        if b.get_height() > max_height:
            max_height = b.get_height()
    for b in bars:
        height = b.get_height()
        label = ("%.2f" % height).rstrip("0").rstrip(".")
        if height > 0.3 * max_height:
            plt.text(
                b.get_x() + b.get_width() / 2.0,
                height - max_height * 0.01,
                label,
                ha=als,
                va="top",
                rotation="vertical",
            )
        else:
            plt.text(
                b.get_x() + b.get_width() / 2.0,
                height + max_height * 0.01,
                label,
                ha=als,
                va="bottom",
                rotation="vertical",
            )


def multi_bar_plot(
    title: str,
    x: list[str],
    series: list[tuple[list[float], str, str]],
    axis: bool = True,
    lab: bool = False,
) -> Figure:
    """Create a bar plot with one or more overlapping series.

    Args:
        title: Plot title.
        x: X-axis labels.
        series: List of (values, legend_label, color) tuples. Use empty string
            for legend_label to skip legend. Colors: "grey", "firebrick", "gold".
        axis: Whether to show x-axis labels.
        lab: Whether to add value labels to bars.

    Returns:
        Matplotlib Figure object.
    """
    n_splits = max(1, math.floor(len(x) / 40))
    xl = split(x, n_splits)
    series_split = [(split(s[0], n_splits), s[1], s[2]) for s in series]

    if len(xl) >= 2:
        axis = True

    height_mult = 5 if len(series) <= 2 else 10
    if len(x) > 20:
        f = plt.figure(figsize=(20, height_mult * len(xl)))
    else:
        f = plt.figure()

    for i in range(len(xl)):
        s = f.add_subplot(len(xl), 1, i + 1)
        bars = []
        labels = []
        alignments = [0, 2, 0]  # left, right, left for label placement
        for j, (values_split, legend, color) in enumerate(series_split):
            p = plt.bar(xl[i], values_split[i], color=color, alpha=0.5, edgecolor="black")
            if lab:
                add_labels(p, alignments[j] if len(series) > 1 else 1)
            if legend:
                bars.append(p[0])
                labels.append(legend)
        if bars:
            plt.legend(bars, labels)
        plt.title(title)
        s.set_xticks(range(len(xl[i])))
        if not axis:
            s.set_xticklabels([""] * len(xl[i]))
        else:
            s.set_xticklabels(xl[i], rotation=45, ha="right")
        plt.tight_layout()

    return f


def bar_plot(
    title: str,
    x: list[str],
    y: list[float],
    axis: bool = True,
    lab: bool = False,
) -> Figure:
    """Create a single-series bar plot. Wrapper around multi_bar_plot."""
    return multi_bar_plot(title, x, [(y, "", "grey")], axis=axis, lab=lab)


def double_bar_plot(
    title: str,
    x: list[str],
    y: list[float],
    z: list[float],
    legend_y: str,
    legend_z: str,
    axis: bool = True,
    lab: bool = False,
) -> Figure:
    """Create a double bar plot comparing two series. Wrapper around multi_bar_plot."""
    return multi_bar_plot(
        title, x, [(y, legend_y, "grey"), (z, legend_z, "firebrick")], axis=axis, lab=lab
    )


def triple_bar_plot(
    title: str,
    x: list[str],
    y: list[float],
    z: list[float],
    u: list[float],
    legend_y: str,
    legend_z: str,
    legend_u: str,
    axis: bool = True,
    lab: bool = False,
) -> Figure:
    """Create a triple bar plot comparing three series. Wrapper around multi_bar_plot."""
    return multi_bar_plot(
        title,
        x,
        [(y, legend_y, "grey"), (z, legend_z, "firebrick"), (u, legend_u, "gold")],
        axis=axis,
        lab=lab,
    )


def corr_plot(x: pd.DataFrame) -> Figure:
    """Create a correlation matrix heatmap.

    Args:
        x: DataFrame to compute correlation on.

    Returns:
        Matplotlib Figure object.
    """
    lg = x.map(np.log2)
    f = plt.figure(figsize=(20.0, 20.0))
    plt.matshow(lg.corr(), cmap=plt.cm.Reds, fignum=f.number)
    fsize = min(10, 150 / len(lg.columns))
    plt.gca().tick_params(width=min(1, 10.0 / len(lg.columns)))
    if len(lg.columns) <= 50:
        plt.xticks(range(lg.shape[1]), lg.columns, rotation=45, fontsize=fsize)
    else:
        plt.xticks(range(lg.shape[1]), lg.columns, rotation=90, fontsize=fsize)
    plt.yticks(range(lg.shape[1]), lg.columns, fontsize=fsize)
    plt.colorbar()
    return f


def save_figure(fig: Figure, path: Path) -> None:
    """Save a matplotlib figure to PDF.

    Args:
        fig: Matplotlib Figure to save.
        path: Output path for the PDF file.
    """
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def create_consistency_histograms(
    pr_ids: pd.Series,
    pg_ids: pd.Series,
    gene_ids: pd.Series,
    fnames: int,
    has_genes: bool,
) -> Figure | None:
    """Create identification consistency histograms (CDFs) for precursors, proteins, genes.

    Args:
        pr_ids: Missing value counts for precursors.
        pg_ids: Missing value counts for protein groups.
        gene_ids: Missing value counts for genes.
        fnames: Number of files.
        has_genes: Whether gene data is available.

    Returns:
        Matplotlib Figure object or None if an error occurs.
    """
    try:
        f = plt.figure(figsize=(20, 5))
        f.add_subplot(131)
        plt.hist(
            pr_ids, bins=fnames, cumulative=True,
            histtype="stepfilled", color="grey", alpha=0.5, edgecolor="black",
        )
        plt.title("Identification consistency: precursors, CDF")
        plt.xlabel("Missing values")
        plt.ylabel("IDs")

        f.add_subplot(132)
        plt.hist(
            pg_ids, bins=fnames, cumulative=True,
            histtype="stepfilled", color="grey", alpha=0.5, edgecolor="black",
        )
        plt.title("Identification consistency: protein groups, CDF")
        plt.xlabel("Missing values")
        plt.ylabel("IDs")

        f.add_subplot(133)
        if has_genes:
            plt.hist(
                gene_ids, bins=fnames, cumulative=True,
                histtype="stepfilled", color="grey", alpha=0.5, edgecolor="black",
            )
            plt.title("Identification consistency: genes groups, CDF")
            plt.xlabel("Missing values")
            plt.ylabel("IDs")

        plt.tight_layout()
        return f
    except (KeyError, ValueError, TypeError, IndexError):
        return None


def create_rt_heatmaps(quant: pd.DataFrame) -> Figure | None:
    """Create retention time and normalization factor heatmaps.

    Args:
        quant: Quantification DataFrame with RT columns.

    Returns:
        Matplotlib Figure object or None if an error occurs.
    """
    try:
        f = plt.figure(figsize=(20, 20.0 / 3.0))

        f.add_subplot(131)
        hmp, ex, ey = np.histogram2d(quant["iRT"], quant["RT"], bins=250)
        plt.imshow(
            hmp.T, origin="lower", cmap="binary",
            extent=[ex[0], ex[-1], ey[0], ey[-1]], aspect="auto", interpolation="none",
        )
        plt.title("Retention times heatmap, all runs")
        plt.xlabel("Library iRT")
        plt.ylabel("RT")

        f.add_subplot(132)
        hmp, ex, ey = np.histogram2d(quant["Predicted.RT"], quant["RT"], bins=250)
        plt.imshow(
            hmp.T, origin="lower", cmap="binary",
            extent=[ex[0], ex[-1], ey[0], ey[-1]], aspect="auto", interpolation="none",
        )
        plt.title("Retention time accuracy heatmap, all runs")
        plt.xlabel("Predicted RT")
        plt.ylabel("RT")

        f.add_subplot(133)
        ratio = quant["Precursor.Normalised"] / quant["Precursor.Quantity"]
        hmp, ex, ey = np.histogram2d(quant["RT"][ratio > 0], ratio[ratio > 0], bins=250)
        plt.imshow(
            hmp.T, origin="lower", cmap="binary",
            extent=[ex[0], ex[-1], ey[0], ey[-1]], aspect="auto", interpolation="none",
        )
        plt.title("Normalisation factor heatmap, all runs")
        plt.xlabel("RT")
        plt.ylabel("Normalisation factor")

        plt.tight_layout()
        return f
    except (KeyError, ValueError, TypeError, IndexError):
        return None


def create_correlation_matrix(pg: pd.DataFrame) -> Figure | None:
    """Create a correlation matrix heatmap for protein groups.

    Args:
        pg: Protein group pivot table.

    Returns:
        Matplotlib Figure object or None if an error occurs.
    """
    try:
        return corr_plot(pg)
    except (KeyError, ValueError, TypeError, IndexError):
        return None


def create_run_statistics_plots(df: pd.DataFrame) -> list[tuple[Figure, str]]:
    """Create per-run statistics bar plots.

    Args:
        df: Stats DataFrame with per-run metrics.

    Returns:
        List of (Figure, title) tuples for each plot.
    """
    plots = []

    try:
        fig = bar_plot("Total quantity, 1% FDR", df["File.Name"], df["Total.Quantity"])
        plots.append((fig, "total_quantity"))
    except (KeyError, ValueError, TypeError, IndexError):
        pass

    try:
        fig = bar_plot("MS1 signal", df["File.Name"], df["MS1.Signal"])
        plots.append((fig, "ms1_signal"))
    except (KeyError, ValueError, TypeError, IndexError):
        pass

    try:
        fig = bar_plot("MS2 signal", df["File.Name"], df["MS2.Signal"])
        plots.append((fig, "ms2_signal"))
    except (KeyError, ValueError, TypeError, IndexError):
        pass

    try:
        r = [x / y if y > 0 else 0 for x, y in zip(df["Total.Quantity"], df["MS2.Signal"])]
        fig = bar_plot("Total quantity/MS2 signal ratio", df["File.Name"], r, lab=True)
        plots.append((fig, "quantity_ms2_ratio"))
    except (KeyError, ValueError, TypeError, IndexError):
        pass

    try:
        r = [x / y if y > 0 else 0 for x, y in zip(df["MS1.Signal"], df["MS2.Signal"])]
        fig = bar_plot("MS1/MS2 signal ratio", df["File.Name"], r, lab=True)
        plots.append((fig, "ms1_ms2_ratio"))
    except (KeyError, ValueError, TypeError, IndexError):
        pass

    try:
        fig = bar_plot("Precursors, 1% FDR", df["File.Name"], df["Precursors.Identified"], lab=True)
        plots.append((fig, "precursors_identified"))
    except (KeyError, ValueError, TypeError, IndexError):
        pass

    try:
        if max(df["Proteins.Identified"]) > 0:
            fig = bar_plot(
                "Unique proteins, 1% protein-level FDR",
                df["File.Name"], df["Proteins.Identified"], lab=True,
            )
            plots.append((fig, "proteins_identified"))
    except (KeyError, ValueError, TypeError, IndexError):
        pass

    try:
        fig = bar_plot("Mean peak FWHM, in minutes", df["File.Name"], df["FWHM.RT"], lab=True)
        plots.append((fig, "fwhm_rt"))
    except (KeyError, ValueError, TypeError, IndexError):
        pass

    try:
        fig = bar_plot("Mean peak FWHM, in MS2 scans", df["File.Name"], df["FWHM.Scans"], lab=True)
        plots.append((fig, "fwhm_scans"))
    except (KeyError, ValueError, TypeError, IndexError):
        pass

    try:
        fig = bar_plot(
            "Median RT prediction accuracy, minutes",
            df["File.Name"], df["Median.RT.Prediction.Acc"], lab=True,
        )
        plots.append((fig, "rt_prediction_accuracy"))
    except (KeyError, ValueError, TypeError, IndexError):
        pass

    try:
        fig = double_bar_plot(
            "Median mass accuracy, MS2, ppm",
            df["File.Name"], df["Median.Mass.Acc.MS2"], df["Median.Mass.Acc.MS2.Corrected"],
            "Without correction", "Corrected",
        )
        plots.append((fig, "mass_accuracy_ms2"))
    except (KeyError, ValueError, TypeError, IndexError):
        pass

    try:
        fig = double_bar_plot(
            "Median mass accuracy, MS1, ppm",
            df["File.Name"], df["Median.Mass.Acc.MS1"], df["Median.Mass.Acc.MS1.Corrected"],
            "Without correction", "Corrected",
        )
        plots.append((fig, "mass_accuracy_ms1"))
    except (KeyError, ValueError, TypeError, IndexError):
        pass

    try:
        fig = double_bar_plot(
            "Peptide characteristics",
            df["File.Name"], df["Average.Peptide.Length"], df["Average.Peptide.Charge"],
            "Average length", "Average charge",
        )
        plots.append((fig, "peptide_characteristics"))
    except (KeyError, ValueError, TypeError, IndexError):
        pass

    try:
        fig = bar_plot(
            "Average missed tryptic cleavages",
            df["File.Name"], df["Average.Missed.Tryptic.Cleavages"], lab=True,
        )
        plots.append((fig, "missed_cleavages"))
    except (KeyError, ValueError, TypeError, IndexError):
        pass

    return plots


def create_cv_analysis_plots(df: pd.DataFrame) -> list[tuple[Figure, str]]:
    """Create CV analysis bar plots for precursors, protein groups, and genes.

    Args:
        df: Stats DataFrame with CV statistics.

    Returns:
        List of (Figure, title) tuples for each plot.
    """
    plots = []

    try:
        cvs = copy.deepcopy(df)[
            [
                "Condition", "Precursor.N", "Precursor.CV", "Precursor.CV.20", "Precursor.CV.10",
                "PG.N", "PG.CV", "PG.CV.20", "PG.CV.10",
                "Gene.N", "Gene.CV", "Gene.CV.20", "Gene.CV.10",
            ]
        ].drop_duplicates()
        cvs = cvs[cvs["Precursor.N"] > 0]
        cvs = cvs[cvs["Precursor.CV"] > 0.0]
        if len(cvs) == 0:
            return plots

        fig = triple_bar_plot(
            "Precursors, 1% FDR", cvs["Condition"],
            cvs["Precursor.N"], cvs["Precursor.CV.20"], cvs["Precursor.CV.10"],
            "Average", "CV < 20%", "CV < 10%", lab=True,
        )
        plots.append((fig, "precursor_cv_counts"))

        fig = bar_plot("Median precursor CV, 1% FDR", cvs["Condition"], cvs["Precursor.CV"], lab=True)
        plots.append((fig, "precursor_cv_median"))

        cvs = cvs[cvs["PG.N"] > 0]
        cvs = cvs[cvs["PG.CV"] > 0.0]
        if len(cvs) == 0:
            return plots

        fig = triple_bar_plot(
            "Protein groups, 1% FDR", cvs["Condition"],
            cvs["PG.N"], cvs["PG.CV.20"], cvs["PG.CV.10"],
            "Average", "CV < 20%", "CV < 10%", lab=True,
        )
        plots.append((fig, "pg_cv_counts"))

        fig = bar_plot("Median protein group CV, 1% FDR", cvs["Condition"], cvs["PG.CV"], lab=True)
        plots.append((fig, "pg_cv_median"))

        cvs = cvs[cvs["Gene.N"] > 0]
        cvs = cvs[cvs["Gene.CV"] > 0.0]
        if len(cvs) == 0:
            return plots

        fig = triple_bar_plot(
            "Gene groups, 1% FDR", cvs["Condition"],
            cvs["Gene.N"], cvs["Gene.CV.20"], cvs["Gene.CV.10"],
            "Average", "CV < 20%", "CV < 10%", lab=True,
        )
        plots.append((fig, "gene_cv_counts"))

        fig = bar_plot("Median gene group CV, 1% FDR", cvs["Condition"], cvs["Gene.CV"], lab=True)
        plots.append((fig, "gene_cv_median"))

    except (KeyError, ValueError, TypeError, IndexError):
        pass

    return plots
