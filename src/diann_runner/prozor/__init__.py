"""
prozor - Python port of the R prozor package for protein inference.

This package provides tools for:
- Peptide-to-protein annotation using Aho-Corasick multi-pattern matching
- Sparse matrix representation of peptide-protein relationships
- Greedy parsimony algorithm for minimal protein set inference

Example:
    >>> from prozor import annotate_peptides, greedy_parsimony
    >>>
    >>> # Load proteins from FASTA
    >>> proteins = {"sp|P12345|PROT1": "MKWVTFISLLLLFSSAYSRGVFRR..."}
    >>> peptides = ["VFRR", "SLLLF", "MKWV"]
    >>>
    >>> # Find peptide-protein matches
    >>> matches = annotate_peptides(peptides, proteins)
    >>>
    >>> # Build sparse matrix and run protein inference
    >>> matrix = matches.to_sparse_matrix()
    >>> result = greedy_parsimony(matrix)
"""

from diann_runner.prozor.annotate import annotate_peptides, PeptideAnnotation, read_fasta
from diann_runner.prozor.greedy import greedy_parsimony, ProteinGroup
from diann_runner.prozor.sparse_matrix import PeptideProteinMatrix

__all__ = [
    "annotate_peptides",
    "PeptideAnnotation",
    "greedy_parsimony",
    "ProteinGroup",
    "PeptideProteinMatrix",
    "read_fasta",
]

__version__ = "0.1.0"
