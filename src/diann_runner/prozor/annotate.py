"""
Peptide annotation using Aho-Corasick multi-pattern matching.

This module provides efficient peptide-to-protein mapping by searching
for all peptide sequences within protein sequences simultaneously.
"""

from dataclasses import dataclass
from typing import Iterable

from diann_runner.prozor.ahocorasick import create_automaton


@dataclass(frozen=True, slots=True)
class PeptideAnnotation:
    """A single peptide-protein match."""

    peptide: str
    protein_id: str
    start: int
    end: int

    @property
    def length(self) -> int:
        """Length of the peptide."""
        return len(self.peptide)


@dataclass
class AnnotationResult:
    """Collection of peptide-protein annotations."""

    annotations: list[PeptideAnnotation]

    def __len__(self) -> int:
        return len(self.annotations)

    def __iter__(self):
        return iter(self.annotations)

    @property
    def peptides(self) -> set[str]:
        """Unique peptides in the annotations."""
        return {a.peptide for a in self.annotations}

    @property
    def proteins(self) -> set[str]:
        """Unique proteins in the annotations."""
        return {a.protein_id for a in self.annotations}

    def filter_tryptic(
        self,
        proteins: dict[str, str],
        prefix_residues: str = "RK",
        allow_n_term: bool = True,
        allow_after_init_met: bool = True,
    ) -> "AnnotationResult":
        """Filter to only tryptic peptides.

        A peptide is considered tryptic if it's preceded by R, K,
        or is at the N-terminus (optionally after initial M).

        Args:
            proteins: Dict mapping protein_id to sequence
            prefix_residues: Residues that indicate valid cleavage (default "RK")
            allow_n_term: Allow peptides at protein N-terminus
            allow_after_init_met: Allow peptides after initial methionine

        Returns:
            New AnnotationResult with only tryptic peptides
        """
        filtered = []
        for ann in self.annotations:
            seq = proteins.get(ann.protein_id, "")
            if not seq:
                continue

            if ann.start == 0:
                if allow_n_term:
                    filtered.append(ann)
            elif ann.start == 1 and allow_after_init_met and seq[0] == "M":
                filtered.append(ann)
            elif ann.start > 0 and seq[ann.start - 1] in prefix_residues:
                filtered.append(ann)

        return AnnotationResult(annotations=filtered)

    def to_dataframe(self):
        """Convert to pandas DataFrame.

        Returns:
            DataFrame with columns: peptide, protein_id, start, end, length
        """
        import pandas as pd

        return pd.DataFrame(
            [
                {
                    "peptide": a.peptide,
                    "protein_id": a.protein_id,
                    "start": a.start,
                    "end": a.end,
                    "length": a.length,
                }
                for a in self.annotations
            ]
        )

    def to_sparse_matrix(self, weighting: str | None = None):
        """Convert to sparse peptide-protein matrix.

        Args:
            weighting: Weight scheme - None (binary), "inverse" (1/n_proteins)

        Returns:
            PeptideProteinMatrix
        """
        from diann_runner.prozor.sparse_matrix import PeptideProteinMatrix

        return PeptideProteinMatrix.from_annotations(self, weighting=weighting)


def annotate_peptides(
    peptides: Iterable[str],
    proteins: dict[str, str],
    backend: str = "auto",
    filter_tryptic: bool = False,
) -> AnnotationResult:
    """
    Annotate peptides with their matching proteins.

    Uses Aho-Corasick algorithm for efficient multi-pattern matching.
    All peptides are searched simultaneously in each protein sequence.

    Args:
        peptides: Iterable of peptide sequences to search for
        proteins: Dict mapping protein_id to protein sequence
        backend: Aho-Corasick backend ("auto", "ahocorapy", "ahocorasick_rs")
        filter_tryptic: If True, only keep tryptic peptides (preceded by R/K or at N-term)

    Returns:
        AnnotationResult containing all peptide-protein matches

    Example:
        >>> proteins = {
        ...     "sp|P12345|PROT1": "MKWVTFISLLFSSAYSRGVFRRDTHK",
        ...     "sp|P67890|PROT2": "MRGVFRRDTHKSEQ",
        ... }
        >>> peptides = ["GVFRR", "DTHK"]
        >>> result = annotate_peptides(peptides, proteins)
        >>> len(result)
        4
        >>> result.proteins
        {'sp|P12345|PROT1', 'sp|P67890|PROT2'}
    """
    peptide_list = list(set(peptides))  # Deduplicate

    if not peptide_list:
        return AnnotationResult(annotations=[])

    # Build automaton from peptides
    ac = create_automaton(peptide_list, backend=backend)

    # Search each protein
    annotations = []
    for protein_id, sequence in proteins.items():
        for match in ac.find_all(sequence):
            annotations.append(
                PeptideAnnotation(
                    peptide=match.keyword,
                    protein_id=protein_id,
                    start=match.start,
                    end=match.end,
                )
            )

    result = AnnotationResult(annotations=annotations)

    if filter_tryptic:
        result = result.filter_tryptic(proteins)

    return result


def read_fasta(filepath: str) -> dict[str, str]:
    """Read a FASTA file into a dict of protein_id -> sequence.

    Args:
        filepath: Path to FASTA file (can be gzipped)

    Returns:
        Dict mapping protein identifiers to sequences
    """
    import gzip
    from pathlib import Path

    proteins = {}
    current_id = None
    current_seq = []

    path = Path(filepath)
    opener = gzip.open if path.suffix == ".gz" else open

    with opener(path, "rt") as f:
        for line in f:
            line = line.strip()
            if line.startswith(">"):
                if current_id is not None:
                    proteins[current_id] = "".join(current_seq)
                # Extract ID from header (first word after >)
                current_id = line[1:].split()[0]
                current_seq = []
            else:
                current_seq.append(line)

        # Don't forget last sequence
        if current_id is not None:
            proteins[current_id] = "".join(current_seq)

    return proteins
