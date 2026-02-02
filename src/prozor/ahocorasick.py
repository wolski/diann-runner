"""
Aho-Corasick abstraction layer for peptide-protein matching.

Provides a unified API over multiple Aho-Corasick implementations:
- ahocorapy: Pure Python, always available
- ahocorasick_rs: Rust-based, optional but faster

Usage:
    from prozor.ahocorasick import create_automaton

    ac = create_automaton(peptides, backend="auto")
    for match in ac.find_all(protein_sequence):
        print(f"{match.keyword} at {match.start}-{match.end}")
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, Iterator


@dataclass(frozen=True, slots=True)
class Match:
    """A peptide match in a protein sequence."""

    keyword: str
    start: int
    end: int


class AhoCorasickBase(ABC):
    """Abstract base class for Aho-Corasick implementations."""

    @abstractmethod
    def find_all(self, text: str) -> Iterator[Match]:
        """Find all keyword matches in text.

        Args:
            text: The text to search (e.g., protein sequence)

        Yields:
            Match objects with keyword, start, and end positions
        """
        ...


class AhoCorasickPure(AhoCorasickBase):
    """Pure Python implementation using ahocorapy."""

    def __init__(self, keywords: Iterable[str], case_sensitive: bool = True):
        from ahocorapy.keywordtree import KeywordTree

        self._tree = KeywordTree(case_insensitive=not case_sensitive)
        for kw in keywords:
            self._tree.add(kw)
        self._tree.finalize()

    def find_all(self, text: str) -> Iterator[Match]:
        for keyword, start in self._tree.search_all(text):
            yield Match(keyword=keyword, start=start, end=start + len(keyword))


class AhoCorasickRust(AhoCorasickBase):
    """Fast Rust implementation using ahocorasick_rs."""

    def __init__(self, keywords: Iterable[str], case_sensitive: bool = True):
        import ahocorasick_rs

        self._keywords = list(keywords)
        self._case_sensitive = case_sensitive
        # Note: ahocorasick_rs doesn't have built-in case insensitivity
        # For case-insensitive, we'd need to lowercase keywords and search text
        if case_sensitive:
            self._ac = ahocorasick_rs.AhoCorasick(self._keywords)
        else:
            self._keywords_lower = [k.lower() for k in self._keywords]
            self._ac = ahocorasick_rs.AhoCorasick(self._keywords_lower)

    def find_all(self, text: str) -> Iterator[Match]:
        search_text = text if self._case_sensitive else text.lower()
        for idx, start, end in self._ac.find_matches_as_indexes(search_text):
            # Return original keyword (not lowercased)
            yield Match(keyword=self._keywords[idx], start=start, end=end)


def create_automaton(
    keywords: Iterable[str],
    backend: str = "auto",
    case_sensitive: bool = True,
) -> AhoCorasickBase:
    """
    Create an Aho-Corasick automaton for multi-pattern matching.

    Args:
        keywords: Patterns to search for (e.g., peptide sequences)
        backend: Backend selection:
            - "auto": Prefer ahocorasick_rs if available, fallback to ahocorapy
            - "ahocorapy": Force pure Python implementation
            - "ahocorasick_rs": Force Rust implementation (raises if unavailable)
        case_sensitive: Whether matching is case-sensitive (default True)

    Returns:
        AhoCorasickBase implementation

    Raises:
        ImportError: If requested backend is not available

    Example:
        >>> ac = create_automaton(["PEPTIDE", "SEQUENCE"])
        >>> list(ac.find_all("MYPEPTIDESEQUENCE"))
        [Match(keyword='PEPTIDE', start=2, end=9),
         Match(keyword='SEQUENCE', start=9, end=17)]
    """
    keywords = list(keywords)  # Materialize once

    if backend == "ahocorasick_rs":
        return AhoCorasickRust(keywords, case_sensitive)

    if backend == "ahocorapy":
        return AhoCorasickPure(keywords, case_sensitive)

    # auto: try rust first, fall back to pure python
    try:
        import ahocorasick_rs  # noqa: F401

        return AhoCorasickRust(keywords, case_sensitive)
    except ImportError:
        return AhoCorasickPure(keywords, case_sensitive)


def get_available_backends() -> list[str]:
    """Return list of available Aho-Corasick backends.

    Returns:
        List of backend names that can be used with create_automaton()
    """
    backends = ["ahocorapy"]  # Always available
    try:
        import ahocorasick_rs  # noqa: F401

        backends.append("ahocorasick_rs")
    except ImportError:
        pass
    return backends
