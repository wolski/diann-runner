"""
Sparse matrix representation of peptide-protein relationships.

Provides efficient storage and manipulation of the peptide × protein
binary (or weighted) matrix used for protein inference.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from scipy import sparse

if TYPE_CHECKING:
    from diann_runner.prozor.annotate import AnnotationResult


@dataclass
class PeptideProteinMatrix:
    """
    Sparse matrix representing peptide-protein relationships.

    Rows are peptides, columns are proteins.
    Values are 1 (binary) or weights (if inverse weighting is used).

    Attributes:
        matrix: scipy sparse CSR matrix
        peptides: List of peptide sequences (row labels)
        proteins: List of protein IDs (column labels)
    """

    matrix: sparse.csr_matrix
    peptides: list[str] = field(default_factory=list)
    proteins: list[str] = field(default_factory=list)

    @property
    def shape(self) -> tuple[int, int]:
        """(n_peptides, n_proteins)"""
        return self.matrix.shape

    @property
    def n_peptides(self) -> int:
        return len(self.peptides)

    @property
    def n_proteins(self) -> int:
        return len(self.proteins)

    @property
    def density(self) -> float:
        """Fraction of non-zero entries."""
        return self.matrix.nnz / (self.matrix.shape[0] * self.matrix.shape[1])

    def peptides_per_protein(self) -> np.ndarray:
        """Number of peptides matching each protein."""
        return np.asarray(self.matrix.sum(axis=0)).ravel()

    def proteins_per_peptide(self) -> np.ndarray:
        """Number of proteins matching each peptide."""
        return np.asarray(self.matrix.sum(axis=1)).ravel()

    def proteotypic_peptides(self) -> list[str]:
        """Return peptides that match exactly one protein."""
        counts = self.proteins_per_peptide()
        return [pep for pep, count in zip(self.peptides, counts) if count == 1]

    def proteotypic_fraction(self) -> float:
        """Fraction of peptides that are proteotypic (match 1 protein)."""
        counts = self.proteins_per_peptide()
        return np.sum(counts == 1) / len(counts) if len(counts) > 0 else 0.0

    @classmethod
    def from_annotations(
        cls,
        annotations: "AnnotationResult",
        weighting: str | None = None,
    ) -> "PeptideProteinMatrix":
        """
        Build sparse matrix from annotation result.

        Args:
            annotations: AnnotationResult from annotate_peptides()
            weighting: Weight scheme:
                - None: Binary matrix (1 if peptide matches protein)
                - "inverse": Weight by 1/(number of proteins per peptide)

        Returns:
            PeptideProteinMatrix
        """
        # Build peptide and protein indices
        peptide_set = sorted(annotations.peptides)
        protein_set = sorted(annotations.proteins)

        peptide_to_idx = {p: i for i, p in enumerate(peptide_set)}
        protein_to_idx = {p: i for i, p in enumerate(protein_set)}

        # Build COO format arrays
        rows = []
        cols = []
        for ann in annotations:
            rows.append(peptide_to_idx[ann.peptide])
            cols.append(protein_to_idx[ann.protein_id])

        # Create sparse matrix
        data = np.ones(len(rows), dtype=np.float64)
        matrix = sparse.csr_matrix(
            (data, (rows, cols)),
            shape=(len(peptide_set), len(protein_set)),
        )

        # Ensure binary (deduplicate multiple matches of same peptide to same protein)
        matrix.data = np.ones_like(matrix.data)

        # Apply weighting
        if weighting == "inverse":
            # Weight each peptide by 1/(number of proteins it matches)
            proteins_per_pep = np.asarray(matrix.sum(axis=1)).ravel()
            # Avoid division by zero
            proteins_per_pep[proteins_per_pep == 0] = 1
            # Divide each row by its sum
            matrix = sparse.diags(1.0 / proteins_per_pep) @ matrix

        return cls(matrix=matrix, peptides=peptide_set, proteins=protein_set)

    @classmethod
    def from_dataframe(
        cls,
        df,
        peptide_col: str = "peptide",
        protein_col: str = "protein_id",
        weighting: str | None = None,
    ) -> "PeptideProteinMatrix":
        """
        Build sparse matrix from pandas DataFrame.

        Args:
            df: DataFrame with peptide and protein columns
            peptide_col: Name of peptide column
            protein_col: Name of protein column
            weighting: Weight scheme (None or "inverse")

        Returns:
            PeptideProteinMatrix
        """
        # Build peptide and protein indices
        peptide_set = sorted(df[peptide_col].unique())
        protein_set = sorted(df[protein_col].unique())

        peptide_to_idx = {p: i for i, p in enumerate(peptide_set)}
        protein_to_idx = {p: i for i, p in enumerate(protein_set)}

        rows = df[peptide_col].map(peptide_to_idx).values
        cols = df[protein_col].map(protein_to_idx).values

        data = np.ones(len(rows), dtype=np.float64)
        matrix = sparse.csr_matrix(
            (data, (rows, cols)),
            shape=(len(peptide_set), len(protein_set)),
        )
        matrix.data = np.ones_like(matrix.data)

        if weighting == "inverse":
            proteins_per_pep = np.asarray(matrix.sum(axis=1)).ravel()
            proteins_per_pep[proteins_per_pep == 0] = 1
            matrix = sparse.diags(1.0 / proteins_per_pep) @ matrix

        return cls(matrix=matrix, peptides=peptide_set, proteins=protein_set)

    def to_dense(self) -> np.ndarray:
        """Convert to dense numpy array."""
        return self.matrix.toarray()

    def subset_peptides(self, peptide_indices: np.ndarray) -> "PeptideProteinMatrix":
        """Return a new matrix with only the specified peptide rows."""
        new_matrix = self.matrix[peptide_indices, :]
        new_peptides = [self.peptides[i] for i in peptide_indices]
        return PeptideProteinMatrix(
            matrix=new_matrix, peptides=new_peptides, proteins=self.proteins.copy()
        )

    def subset_proteins(self, protein_indices: np.ndarray) -> "PeptideProteinMatrix":
        """Return a new matrix with only the specified protein columns."""
        new_matrix = self.matrix[:, protein_indices]
        new_proteins = [self.proteins[i] for i in protein_indices]
        return PeptideProteinMatrix(
            matrix=new_matrix, peptides=self.peptides.copy(), proteins=new_proteins
        )

    def remove_zero_rows(self) -> "PeptideProteinMatrix":
        """Remove peptide rows with no protein matches."""
        row_sums = np.asarray(self.matrix.sum(axis=1)).ravel()
        nonzero_mask = row_sums > 0
        nonzero_indices = np.where(nonzero_mask)[0]
        return self.subset_peptides(nonzero_indices)

    def remove_zero_cols(self) -> "PeptideProteinMatrix":
        """Remove protein columns with no peptide matches."""
        col_sums = np.asarray(self.matrix.sum(axis=0)).ravel()
        nonzero_mask = col_sums > 0
        nonzero_indices = np.where(nonzero_mask)[0]
        return self.subset_proteins(nonzero_indices)
