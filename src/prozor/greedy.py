"""
Greedy parsimony algorithm for protein inference.

Implements Occam's razor principle: find the minimal set of proteins
that explains all observed peptides.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy import sparse

from prozor.sparse_matrix import PeptideProteinMatrix


@dataclass
class ProteinGroup:
    """
    A group of proteins that share identical peptide evidence.

    When multiple proteins have exactly the same peptides, they are
    grouped together as indistinguishable.

    Attributes:
        proteins: List of protein IDs in this group (semicolon-joined in output)
        peptides: List of peptides assigned to this group
    """

    proteins: list[str] = field(default_factory=list)
    peptides: list[str] = field(default_factory=list)

    @property
    def protein_id(self) -> str:
        """Semicolon-joined protein IDs (like R prozor output)."""
        return ";".join(self.proteins)

    @property
    def n_peptides(self) -> int:
        return len(self.peptides)

    @property
    def n_proteins(self) -> int:
        return len(self.proteins)


@dataclass
class GreedyResult:
    """Result of greedy parsimony protein inference."""

    groups: list[ProteinGroup]

    def __len__(self) -> int:
        return len(self.groups)

    def __iter__(self):
        return iter(self.groups)

    @property
    def n_proteins(self) -> int:
        """Total number of proteins (counting each in a group)."""
        return sum(g.n_proteins for g in self.groups)

    @property
    def n_groups(self) -> int:
        """Number of protein groups."""
        return len(self.groups)

    @property
    def n_peptides(self) -> int:
        """Total number of unique peptides assigned."""
        all_peps = set()
        for g in self.groups:
            all_peps.update(g.peptides)
        return len(all_peps)

    def to_dict(self) -> dict[str, str]:
        """
        Convert to peptide -> protein_group mapping.

        Returns:
            Dict mapping each peptide to its protein group ID
            (like R prozor::greedy_parsimony output)
        """
        result = {}
        for group in self.groups:
            protein_id = group.protein_id
            for peptide in group.peptides:
                result[peptide] = protein_id
        return result

    def to_dataframe(self):
        """
        Convert to pandas DataFrame.

        Returns:
            DataFrame with columns: peptide, protein_group, n_proteins_in_group
        """
        import pandas as pd

        rows = []
        for group in self.groups:
            protein_id = group.protein_id
            n_prots = group.n_proteins
            for peptide in group.peptides:
                rows.append(
                    {
                        "peptide": peptide,
                        "protein_group": protein_id,
                        "n_proteins_in_group": n_prots,
                    }
                )
        return pd.DataFrame(rows)


def _find_indistinguishable_proteins(
    matrix: sparse.csr_matrix, candidate_indices: np.ndarray
) -> list[int]:
    """
    Find proteins with identical peptide patterns among candidates.

    When there's a tie (multiple proteins with same max peptide count),
    check if they share all peptides. If so, group them.

    Args:
        matrix: Peptide-protein sparse matrix
        candidate_indices: Column indices of tied proteins

    Returns:
        List of indices for proteins to group together
    """
    if len(candidate_indices) == 1:
        return list(candidate_indices)

    # Extract columns for candidates
    submatrix = matrix[:, candidate_indices].toarray()

    # Check pairwise if proteins have identical patterns
    # Two proteins are indistinguishable if their columns are identical
    n_candidates = len(candidate_indices)
    groups = []
    used = set()

    for i in range(n_candidates):
        if i in used:
            continue
        group = [i]
        used.add(i)
        for j in range(i + 1, n_candidates):
            if j in used:
                continue
            if np.array_equal(submatrix[:, i], submatrix[:, j]):
                group.append(j)
                used.add(j)
        groups.append(group)

    # Return the largest group (or first if tied)
    # This matches R behavior: group indistinguishable, pick one group
    largest_group = max(groups, key=len)
    return [candidate_indices[i] for i in largest_group]


def greedy_parsimony(pep_prot: PeptideProteinMatrix) -> GreedyResult:
    """
    Find minimal protein set explaining all peptides using greedy algorithm.

    Implements Occam's razor: iteratively select the protein that explains
    the most unexplained peptides, remove those peptides, and repeat.

    Proteins with identical peptide evidence are grouped together.

    Args:
        pep_prot: PeptideProteinMatrix from annotations

    Returns:
        GreedyResult with protein groups and their assigned peptides

    Example:
        >>> from prozor import annotate_peptides, greedy_parsimony
        >>> result = annotate_peptides(peptides, proteins)
        >>> matrix = result.to_sparse_matrix()
        >>> inference = greedy_parsimony(matrix)
        >>> print(f"Reduced to {inference.n_groups} protein groups")
    """
    # Work with a copy as CSC for efficient column operations
    matrix = pep_prot.matrix.tocsc().astype(np.float64)
    n_peptides, n_proteins = matrix.shape

    # Track which peptides/proteins are still active
    active_peptides = np.ones(n_peptides, dtype=bool)
    active_proteins = np.ones(n_proteins, dtype=bool)

    groups = []

    for _ in range(n_proteins):
        # Count peptides per protein (only active peptides)
        active_matrix = matrix[active_peptides, :][:, active_proteins]

        if active_matrix.shape[0] == 0 or active_matrix.nnz == 0:
            break

        peps_per_prot = np.asarray(active_matrix.sum(axis=0)).ravel()

        if peps_per_prot.max() == 0:
            break

        # Find protein(s) with most peptides
        max_count = peps_per_prot.max()
        candidates = np.where(peps_per_prot == max_count)[0]

        # Map back to original indices
        active_protein_indices = np.where(active_proteins)[0]
        candidate_orig_indices = active_protein_indices[candidates]

        # Check for indistinguishable proteins (identical peptide patterns)
        grouped_indices = _find_indistinguishable_proteins(
            matrix[active_peptides, :], candidate_orig_indices
        )

        # Get protein names for this group
        group_proteins = [pep_prot.proteins[i] for i in grouped_indices]

        # Find peptides covered by this group (use first protein, they're identical)
        winner_col = matrix[active_peptides, grouped_indices[0]]
        covered_mask = np.asarray(winner_col.toarray()).ravel() > 0

        # Map back to original peptide indices
        active_peptide_indices = np.where(active_peptides)[0]
        covered_orig_indices = active_peptide_indices[covered_mask]
        group_peptides = [pep_prot.peptides[i] for i in covered_orig_indices]

        # Create protein group
        groups.append(ProteinGroup(proteins=group_proteins, peptides=group_peptides))

        # Remove covered peptides and grouped proteins from active sets
        active_peptides[covered_orig_indices] = False
        active_proteins[grouped_indices] = False

    return GreedyResult(groups=groups)
