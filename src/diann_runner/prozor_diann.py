"""
CLI tool to run prozor protein inference on DIA-NN report files.

This tool:
1. Reads a DIA-NN report parquet file
2. Extracts unique peptides
3. Annotates peptides against a FASTA database using Aho-Corasick
4. Runs greedy parsimony to find minimal protein set
5. Updates protein columns while preserving file structure
"""

from dataclasses import dataclass
from pathlib import Path

import cyclopts
import pandas as pd
from loguru import logger

from diann_runner.prozor import annotate_peptides, greedy_parsimony, read_fasta
from diann_runner.prozor.greedy import GreedyResult
from diann_runner.prozor.sparse_matrix import PeptideProteinMatrix

app = cyclopts.App(
    name="prozor-diann",
    help="Run prozor protein inference on DIA-NN report files",
)


@dataclass
class PeptideMappings:
    """Mappings from peptides to protein group information."""

    protein_ids: dict[str, str]  # peptide -> semicolon-joined protein IDs
    protein_group: dict[str, str]  # peptide -> representative protein
    n_peptides: dict[str, int]  # peptide -> number of peptides in group


@dataclass
class InferenceStats:
    """Statistics from protein inference."""

    # Input stats
    total_rows: int
    unique_peptides: int
    proteins_in_fasta: int

    # Matching stats
    peptide_protein_matches: int
    proteins_matched: int
    proteotypic_peptides: int
    proteotypic_fraction: float

    # Parsimony stats
    protein_groups: int
    proteins_in_groups: int
    subsumed_proteins: int

    # Comparison stats
    original_protein_ids: int
    original_protein_groups: int
    inferred_protein_ids: int
    rows_changed: int
    rows_changed_pct: float


def _setup_file_logging(log_path: Path) -> None:
    """Configure loguru to also log to a file."""
    logger.add(
        log_path,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="INFO",
        mode="w",
    )


def _extract_protein_id(header: str) -> str:
    """Extract protein ID from FASTA header.

    Handles formats like:
    - sp|P12345|NAME_SPECIES -> P12345
    - tr|Q12345|NAME_SPECIES -> Q12345
    - >aa|id|description -> id
    - Simple ID -> Simple ID
    """
    header = header.lstrip(">")
    parts = header.split("|")
    if len(parts) >= 2:
        return parts[1]
    return header.split()[0]


def _load_report(report_path: Path) -> pd.DataFrame:
    """Load DIA-NN report from parquet file."""
    logger.info(f"Reading report from {report_path}")
    df = pd.read_parquet(report_path)
    logger.info(f"Report shape: {df.shape}")
    return df


def _extract_peptides(df: pd.DataFrame, min_length: int) -> list[str]:
    """Extract unique peptides from report, filtered by length."""
    peptides = df["Stripped.Sequence"].unique().tolist()
    logger.info(f"Unique peptides: {len(peptides)}")

    peptides = [p for p in peptides if len(p) >= min_length]
    logger.info(f"Peptides after length filter (>={min_length}): {len(peptides)}")
    return peptides


def _load_fasta(fasta_path: Path) -> dict[str, str]:
    """Load FASTA and extract protein IDs from headers."""
    logger.info(f"Reading FASTA from {fasta_path}")
    raw_proteins = read_fasta(fasta_path)

    proteins = {_extract_protein_id(header): seq for header, seq in raw_proteins.items()}
    logger.info(f"Proteins in database: {len(proteins)}")
    return proteins


def _run_annotation(peptides: list[str], proteins: dict[str, str]) -> PeptideProteinMatrix:
    """Annotate peptides against proteins and build sparse matrix."""
    logger.info("Annotating peptides against proteins...")
    annotations = annotate_peptides(peptides, proteins)
    logger.info(f"Peptide-protein matches: {len(annotations)}")

    logger.info("Building peptide-protein matrix...")
    matrix = annotations.to_sparse_matrix()

    _, n_prots = matrix.matrix.shape
    n_proteotypic = len(matrix.proteotypic_peptides())
    logger.info(f"Matrix shape: {matrix.matrix.shape}")
    logger.info(f"Proteins matched by peptides: {n_prots}")
    logger.info(f"Proteotypic peptides: {n_proteotypic} ({100*matrix.proteotypic_fraction():.1f}%)")

    return matrix


def _run_parsimony(matrix: PeptideProteinMatrix) -> GreedyResult:
    """Run greedy parsimony algorithm."""
    logger.info("Running greedy parsimony...")
    protein_groups = greedy_parsimony(matrix)

    n_groups = len(protein_groups)
    n_proteins = sum(g.n_proteins for g in protein_groups)
    n_subsumed = n_proteins - n_groups

    logger.info(f"Protein groups after parsimony: {n_groups}")
    logger.info(f"Proteins in groups (incl. subsumed): {n_proteins}")
    logger.info(f"Subsumed proteins: {n_subsumed}")

    return protein_groups


def _build_peptide_mappings(protein_groups: GreedyResult) -> PeptideMappings:
    """Build peptide to protein group mappings."""
    peptide_to_proteins: dict[str, set[str]] = {}
    peptide_to_group: dict[str, str] = {}
    peptide_to_n_peptides: dict[str, int] = {}

    for group in protein_groups:
        representative = group.proteins[0]
        n_peptides_in_group = group.n_peptides

        for peptide in group.peptides:
            if peptide not in peptide_to_proteins:
                peptide_to_proteins[peptide] = set()
                peptide_to_group[peptide] = representative
                peptide_to_n_peptides[peptide] = n_peptides_in_group
            peptide_to_proteins[peptide].update(group.proteins)

    protein_ids = {pep: ";".join(sorted(prots)) for pep, prots in peptide_to_proteins.items()}

    return PeptideMappings(
        protein_ids=protein_ids,
        protein_group=peptide_to_group,
        n_peptides=peptide_to_n_peptides,
    )


def _apply_mappings(df: pd.DataFrame, mappings: PeptideMappings) -> pd.DataFrame:
    """Apply peptide mappings to update protein columns in DataFrame."""
    logger.info("Updating protein columns...")

    # Preserve original columns
    df["Protein.Ids.Original"] = df["Protein.Ids"]
    df["Protein.Group.Original"] = df["Protein.Group"]

    # Apply new mappings
    df["Protein.Ids"] = df["Stripped.Sequence"].map(mappings.protein_ids)
    df["Protein.Group"] = df["Stripped.Sequence"].map(mappings.protein_group)
    df["PG.N.Peptides"] = df["Stripped.Sequence"].map(mappings.n_peptides)

    # Check for unmapped peptides - indicates FASTA mismatch
    unmapped_mask = df["Protein.Ids"].isna()
    unmapped_count = unmapped_mask.sum()

    if unmapped_count > 0:
        unmapped_peptides = df.loc[unmapped_mask, "Stripped.Sequence"].unique()[:10]
        logger.error(f"FATAL: {unmapped_count} rows have unmapped peptides!")
        logger.error(f"First unmapped peptides: {list(unmapped_peptides)}")
        logger.error("This indicates the FASTA database does not match the one used by DIA-NN.")
        raise ValueError(
            f"Found {unmapped_count} rows with unmapped peptides. "
            f"FASTA database mismatch - ensure you use the same FASTA that DIA-NN used."
        )

    return df


def _collect_stats(
    df: pd.DataFrame,
    peptides: list[str],
    proteins: dict[str, str],
    matrix: PeptideProteinMatrix,
    protein_groups: GreedyResult,
) -> InferenceStats:
    """Collect inference statistics."""
    _, n_prots = matrix.matrix.shape
    n_proteotypic = len(matrix.proteotypic_peptides())
    n_groups = len(protein_groups)
    n_proteins_in_groups = sum(g.n_proteins for g in protein_groups)

    changed_mask = df["Protein.Ids"] != df["Protein.Ids.Original"]
    rows_changed = changed_mask.sum()

    return InferenceStats(
        total_rows=len(df),
        unique_peptides=len(peptides),
        proteins_in_fasta=len(proteins),
        peptide_protein_matches=sum(1 for _ in matrix.matrix.data),
        proteins_matched=n_prots,
        proteotypic_peptides=n_proteotypic,
        proteotypic_fraction=matrix.proteotypic_fraction(),
        protein_groups=n_groups,
        proteins_in_groups=n_proteins_in_groups,
        subsumed_proteins=n_proteins_in_groups - n_groups,
        original_protein_ids=df["Protein.Ids.Original"].nunique(),
        original_protein_groups=df["Protein.Group.Original"].nunique(),
        inferred_protein_ids=df["Protein.Ids"].nunique(),
        rows_changed=rows_changed,
        rows_changed_pct=100 * rows_changed / len(df),
    )


def _log_summary(stats: InferenceStats, report_path: Path, fasta_path: Path, output_path: Path) -> None:
    """Log inference summary."""
    logger.info("=" * 60)
    logger.info("PROZOR PROTEIN INFERENCE SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Input report:        {report_path}")
    logger.info(f"FASTA database:      {fasta_path}")
    logger.info(f"Output file:         {output_path}")
    logger.info("-" * 60)
    logger.info(f"Total rows:          {stats.total_rows:,}")
    logger.info(f"Unique peptides:     {stats.unique_peptides:,}")
    logger.info(f"Proteins in FASTA:   {stats.proteins_in_fasta:,}")
    logger.info("-" * 60)
    logger.info("PEPTIDE-PROTEIN MATCHING:")
    logger.info(f"  Proteins matched by peptides: {stats.proteins_matched:,}")
    logger.info(f"  Proteotypic peptides (unique): {stats.proteotypic_peptides:,} ({100*stats.proteotypic_fraction:.1f}%)")
    n_shared = stats.unique_peptides - stats.proteotypic_peptides
    logger.info(f"  Shared peptides: {n_shared:,} ({100*(1-stats.proteotypic_fraction):.1f}%)")
    logger.info("-" * 60)
    logger.info("GREEDY PARSIMONY:")
    logger.info(f"  Protein groups after parsimony: {stats.protein_groups:,}")
    logger.info(f"  Proteins in groups (incl. subsumed): {stats.proteins_in_groups:,}")
    logger.info(f"  Subsumed proteins (subset of winner): {stats.subsumed_proteins:,}")
    logger.info(f"  Proteins not in any group: {stats.proteins_matched - stats.proteins_in_groups:,}")
    logger.info("-" * 60)
    logger.info("COMPARISON WITH DIA-NN:")
    logger.info(f"  DIA-NN Protein.Ids:    {stats.original_protein_ids:,}")
    logger.info(f"  Prozor Protein.Ids:    {stats.inferred_protein_ids:,}")
    logger.info(f"  DIA-NN Protein.Groups: {stats.original_protein_groups:,}")
    logger.info(f"  Prozor Protein.Groups: {stats.protein_groups:,}")
    logger.info("-" * 60)
    logger.info(f"Rows with changed assignment: {stats.rows_changed:,} ({stats.rows_changed_pct:.1f}%)")
    logger.info("=" * 60)


def run_prozor_inference(
    report_path: Path,
    fasta_path: Path,
    output_path: Path,
    min_peptide_length: int = 6,
) -> InferenceStats:
    """Run prozor protein inference on a DIA-NN report.

    Args:
        report_path: Path to DIA-NN report parquet file
        fasta_path: Path to FASTA database
        output_path: Path for output parquet file
        min_peptide_length: Minimum peptide length to consider

    Returns:
        InferenceStats with inference statistics
    """
    # Step 1: Load data
    df = _load_report(report_path)
    peptides = _extract_peptides(df, min_peptide_length)
    proteins = _load_fasta(fasta_path)

    # Step 2: Run inference pipeline
    matrix = _run_annotation(peptides, proteins)
    protein_groups = _run_parsimony(matrix)

    # Step 3: Build and apply mappings
    mappings = _build_peptide_mappings(protein_groups)
    df = _apply_mappings(df, mappings)

    # Step 4: Collect stats and log summary
    stats = _collect_stats(df, peptides, proteins, matrix, protein_groups)
    _log_summary(stats, report_path, fasta_path, output_path)

    # Step 5: Write output
    logger.info(f"Writing output to {output_path}")
    df.to_parquet(output_path, index=False)

    return stats


@app.default
def main(
    report: Path,
    fasta: Path,
    output: Path | None = None,
    log: Path | None = None,
    min_length: int = 6,
) -> None:
    """Run prozor protein inference on a DIA-NN report.

    Args:
        report: Path to DIA-NN report parquet file
        fasta: Path to FASTA database file
        output: Output parquet path (default: {report}_prozor.parquet)
        log: Log file path (default: prozor.log in output directory)
        min_length: Minimum peptide length to consider
    """
    if output is None:
        output = report.with_name(report.stem + "_prozor.parquet")

    if log is None:
        log = output.parent / "prozor.log"

    _setup_file_logging(log)
    logger.info(f"Logging to {log}")

    run_prozor_inference(
        report_path=report,
        fasta_path=fasta,
        output_path=output,
        min_peptide_length=min_length,
    )
    logger.info("Done!")


if __name__ == "__main__":
    app()
