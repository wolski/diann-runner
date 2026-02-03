"""
Greedy parsimony algorithm for protein inference.

Implements Occam's razor principle: find the minimal set of proteins
that explains all observed peptides.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy import sparse

from diann_runner.prozor.sparse_matrix import PeptideProteinMatrix


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


def greedy_parsimony(
    pep_prot: PeptideProteinMatrix,
    subsume: bool = True,
) -> GreedyResult:
    """
    Find minimal protein set explaining all peptides using greedy algorithm.

    Implements Occam's razor: iteratively select the protein that explains
    the most unexplained peptides, remove those peptides, and repeat.

    Proteins with identical peptide evidence are grouped together.
    If subsume=True, proteins whose peptides become fully covered by a winner
    are added to that winner's group (subset relationship).

    Args:
        pep_prot: PeptideProteinMatrix from annotations
        subsume: If True, add subsumed proteins to winner's group (default True)

    Returns:
        GreedyResult with protein groups and their assigned peptides

    Example:
        >>> from prozor import annotate_peptides, greedy_parsimony
        >>> result = annotate_peptides(peptides, proteins)
        >>> matrix = result.to_sparse_matrix()
        >>> inference = greedy_parsimony(matrix)
        >>> print(f"Reduced to {inference.n_groups} protein groups")
    """
    # Convert to LIL for efficient row access, then to CSC for column sums
    matrix = pep_prot.matrix.tocsc().astype(np.float64)
    n_peptides, n_proteins = matrix.shape

    # Build peptide->protein lookup using sparse structure for efficiency
    # peptide_proteins[i] = set of protein indices that contain peptide i
    matrix_csr = matrix.tocsr()
    peptide_proteins = []
    for i in range(n_peptides):
        row = matrix_csr.getrow(i)
        peptide_proteins.append(set(row.indices))

    # Build protein->peptide lookup
    # protein_peptides[j] = set of peptide indices that protein j contains
    protein_peptides = []
    for j in range(n_proteins):
        col = matrix.getcol(j)
        protein_peptides.append(set(col.indices))

    # Track which peptides/proteins are still active (as sets for O(1) operations)
    active_peptides = set(range(n_peptides))
    active_proteins = set(range(n_proteins))

    # Compute initial peptide counts per protein
    pep_counts = np.array([len(protein_peptides[j]) for j in range(n_proteins)])

    groups = []

    while active_peptides and active_proteins:
        # Find protein(s) with most active peptides
        # Only consider active proteins
        active_prot_list = np.array(list(active_proteins))
        if len(active_prot_list) == 0:
            break

        active_counts = pep_counts[active_prot_list]
        max_count = active_counts.max()

        if max_count == 0:
            break

        # Find all proteins tied for max count
        candidates = active_prot_list[active_counts == max_count]

        # Group indistinguishable proteins (same peptide sets among active peptides)
        # Use frozenset of active peptides for each candidate
        peptide_signatures = {}
        for prot_idx in candidates:
            # Get active peptides for this protein
            active_peps = protein_peptides[prot_idx] & active_peptides
            sig = frozenset(active_peps)
            if sig not in peptide_signatures:
                peptide_signatures[sig] = []
            peptide_signatures[sig].append(prot_idx)

        # Pick the largest group (or first if tied)
        best_group = max(peptide_signatures.values(), key=len)

        # Get peptides covered by this group (all have same peptides)
        covered_peptides = protein_peptides[best_group[0]] & active_peptides
        group_peptides = [pep_prot.peptides[i] for i in covered_peptides]

        # Find subsumed proteins: proteins whose remaining peptides are
        # a subset of the winner's peptides (they become "empty" after this round)
        subsumed_proteins = []
        if subsume:
            # Only check proteins that share at least one peptide with winner
            # Build set of proteins that share peptides with winner
            candidate_subsumed = set()
            for pep_idx in covered_peptides:
                candidate_subsumed.update(peptide_proteins[pep_idx])
            candidate_subsumed -= set(best_group)
            candidate_subsumed &= active_proteins

            for prot_idx in candidate_subsumed:
                prot_active_peps = protein_peptides[prot_idx] & active_peptides
                if prot_active_peps <= covered_peptides:
                    # This protein's peptides are a subset of winner's
                    subsumed_proteins.append(prot_idx)

        # Get protein names for this group (winners + subsumed)
        all_group_indices = list(best_group) + subsumed_proteins
        group_proteins = [pep_prot.proteins[i] for i in all_group_indices]

        # Create protein group
        groups.append(ProteinGroup(proteins=group_proteins, peptides=group_peptides))

        # Update active sets
        active_peptides -= covered_peptides
        active_proteins -= set(all_group_indices)

        # Update peptide counts for remaining proteins
        # Subtract counts for removed peptides
        for pep_idx in covered_peptides:
            for prot_idx in peptide_proteins[pep_idx]:
                if prot_idx in active_proteins:
                    pep_counts[prot_idx] -= 1

    return GreedyResult(groups=groups)
