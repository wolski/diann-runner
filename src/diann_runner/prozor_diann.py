"""
CLI tool to run prozor protein inference on DIA-NN report files.

This tool:
1. Reads a DIA-NN report parquet file
2. Extracts unique peptides
3. Annotates peptides against a FASTA database using Aho-Corasick
4. Runs greedy parsimony to find minimal protein set
5. Updates protein columns while preserving file structure
"""

import sys
from pathlib import Path

import cyclopts
import pandas as pd
from loguru import logger

# Import prozor from the package
sys.path.insert(0, str(Path(__file__).parent.parent))
from prozor import annotate_peptides, greedy_parsimony, read_fasta

app = cyclopts.App(
    name="prozor-diann",
    help="Run prozor protein inference on DIA-NN report files",
)


def _extract_protein_id(header: str) -> str:
    """Extract protein ID from FASTA header.

    Handles formats like:
    - sp|P12345|NAME_SPECIES -> P12345
    - tr|Q12345|NAME_SPECIES -> Q12345
    - >aa|id|description -> id
    - Simple ID -> Simple ID
    """
    # Remove > if present
    header = header.lstrip(">")

    # Try UniProt format: sp|ID|NAME or tr|ID|NAME
    parts = header.split("|")
    if len(parts) >= 2:
        # Return the second part (accession)
        return parts[1]

    # Fall back to first word
    return header.split()[0]


def run_prozor_inference(
    report_path: Path,
    fasta_path: Path,
    output_path: Path,
    min_peptide_length: int = 6,
) -> pd.DataFrame:
    """Run prozor protein inference on a DIA-NN report.

    Args:
        report_path: Path to DIA-NN report parquet file
        fasta_path: Path to FASTA database
        output_path: Path for output parquet file
        min_peptide_length: Minimum peptide length to consider

    Returns:
        Updated DataFrame with new protein assignments
    """
    logger.info(f"Reading report from {report_path}")
    df = pd.read_parquet(report_path)
    logger.info(f"Report shape: {df.shape}")

    # Extract unique peptides
    peptides = df["Stripped.Sequence"].unique().tolist()
    logger.info(f"Unique peptides: {len(peptides)}")

    # Filter by length
    peptides = [p for p in peptides if len(p) >= min_peptide_length]
    logger.info(f"Peptides after length filter (>={min_peptide_length}): {len(peptides)}")

    # Read FASTA and create protein dict with extracted IDs
    logger.info(f"Reading FASTA from {fasta_path}")
    raw_proteins = read_fasta(fasta_path)

    # Map headers to extracted IDs
    proteins = {}
    header_to_id = {}
    for header, sequence in raw_proteins.items():
        protein_id = _extract_protein_id(header)
        proteins[protein_id] = sequence
        header_to_id[header] = protein_id

    logger.info(f"Proteins in database: {len(proteins)}")

    # Annotate peptides against proteins
    logger.info("Annotating peptides against proteins...")
    annotations = annotate_peptides(peptides, proteins)
    logger.info(f"Peptide-protein matches: {len(annotations)}")

    # Build sparse matrix
    logger.info("Building peptide-protein matrix...")
    matrix = annotations.to_sparse_matrix()
    logger.info(f"Matrix shape: {matrix.matrix.shape}")

    # Run greedy parsimony
    logger.info("Running greedy parsimony...")
    protein_groups = greedy_parsimony(matrix)
    logger.info(f"Protein groups after parsimony: {len(protein_groups)}")

    # Build peptide -> protein group mapping
    # Each peptide maps to the protein group(s) that contain it
    peptide_to_proteins = {}
    peptide_to_group = {}

    for group in protein_groups:
        # The representative protein is the first one (most peptides)
        representative = group.proteins[0]
        group_proteins = ";".join(group.proteins)

        for peptide in group.peptides:
            if peptide not in peptide_to_proteins:
                peptide_to_proteins[peptide] = set()
                peptide_to_group[peptide] = representative
            peptide_to_proteins[peptide].update(group.proteins)

    # For peptides mapping to multiple groups, join all proteins
    peptide_to_protein_str = {
        pep: ";".join(sorted(prots))
        for pep, prots in peptide_to_proteins.items()
    }

    # Update the DataFrame
    logger.info("Updating protein columns...")

    # Create new columns
    df["Protein.Ids.Original"] = df["Protein.Ids"]
    df["Protein.Group.Original"] = df["Protein.Group"]

    # Map peptides to new protein assignments
    df["Protein.Ids"] = df["Stripped.Sequence"].map(peptide_to_protein_str)
    df["Protein.Group"] = df["Stripped.Sequence"].map(peptide_to_group)

    # Handle unmapped peptides (keep original)
    unmapped_mask = df["Protein.Ids"].isna()
    unmapped_count = unmapped_mask.sum()
    if unmapped_count > 0:
        logger.warning(f"Unmapped peptides (keeping original): {unmapped_count} rows")
        df.loc[unmapped_mask, "Protein.Ids"] = df.loc[unmapped_mask, "Protein.Ids.Original"]
        df.loc[unmapped_mask, "Protein.Group"] = df.loc[unmapped_mask, "Protein.Group.Original"]

    # Write output
    logger.info(f"Writing output to {output_path}")
    df.to_parquet(output_path, index=False)

    # Summary stats
    new_protein_ids = df["Protein.Ids"].nunique()
    new_protein_groups = df["Protein.Group"].nunique()
    logger.info(f"Original unique Protein.Ids: {df['Protein.Ids.Original'].nunique()}")
    logger.info(f"New unique Protein.Ids: {new_protein_ids}")
    logger.info(f"New unique Protein.Group: {new_protein_groups}")

    return df


@app.default
def main(
    report: Path,
    fasta: Path,
    output: Path | None = None,
    min_length: int = 6,
) -> None:
    """Run prozor protein inference on a DIA-NN report.

    Args:
        report: Path to DIA-NN report parquet file
        fasta: Path to FASTA database file
        output: Output parquet path (default: {report}_prozor.parquet)
        min_length: Minimum peptide length to consider
    """
    if output is None:
        output = report.with_name(report.stem + "_prozor.parquet")

    run_prozor_inference(
        report_path=report,
        fasta_path=fasta,
        output_path=output,
        min_peptide_length=min_length,
    )
    logger.info("Done!")


if __name__ == "__main__":
    app()
