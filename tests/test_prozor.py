"""Tests for the prozor protein inference package."""

import numpy as np
import pytest

from diann_runner.prozor import (
    PeptideAnnotation,
    PeptideProteinMatrix,
    ProteinGroup,
    annotate_peptides,
    greedy_parsimony,
)
from diann_runner.prozor.ahocorasick import Match, create_automaton, get_available_backends


class TestAhoCorasick:
    """Test Aho-Corasick abstraction layer."""

    def test_get_available_backends(self):
        """ahocorapy should always be available."""
        backends = get_available_backends()
        assert "ahocorapy" in backends

    def test_create_automaton_default(self):
        """Should create automaton with default backend."""
        keywords = ["PEPTIDE", "SEQ"]
        ac = create_automaton(keywords)
        assert ac is not None

    def test_find_all_single_match(self):
        """Should find a single pattern match."""
        ac = create_automaton(["PEPTIDE"])
        matches = list(ac.find_all("MYPEPTIDESEQUENCE"))
        assert len(matches) == 1
        assert matches[0].keyword == "PEPTIDE"
        assert matches[0].start == 2
        assert matches[0].end == 9

    def test_find_all_multiple_matches(self):
        """Should find multiple pattern matches."""
        ac = create_automaton(["PEPTIDE", "SEQUENCE"])
        matches = list(ac.find_all("MYPEPTIDESEQUENCE"))
        assert len(matches) == 2
        keywords = {m.keyword for m in matches}
        assert keywords == {"PEPTIDE", "SEQUENCE"}

    def test_find_all_overlapping(self):
        """Should find overlapping matches."""
        ac = create_automaton(["ABC", "BCD"])
        matches = list(ac.find_all("XABCDY"))
        assert len(matches) == 2

    def test_find_all_no_match(self):
        """Should return empty when no match."""
        ac = create_automaton(["XYZ"])
        matches = list(ac.find_all("MYPEPTIDE"))
        assert len(matches) == 0

    def test_find_all_repeated_pattern(self):
        """Should find same pattern multiple times (including overlaps)."""
        ac = create_automaton(["AA"])
        matches = list(ac.find_all("XAAAXAAAX"))
        # "AAA" contains 2 overlapping "AA" matches (positions 1-3 and 2-4)
        # Two "AAA" sequences = 4 total matches
        assert len(matches) == 4
        assert all(m.keyword == "AA" for m in matches)

    def test_match_dataclass(self):
        """Match should be frozen and have correct attributes."""
        m = Match(keyword="PEP", start=0, end=3)
        assert m.keyword == "PEP"
        assert m.start == 0
        assert m.end == 3
        with pytest.raises(AttributeError):
            m.keyword = "OTHER"  # type: ignore

    def test_ahocorapy_backend_explicit(self):
        """Should use ahocorapy when explicitly requested."""
        ac = create_automaton(["TEST"], backend="ahocorapy")
        matches = list(ac.find_all("TESTING"))
        assert len(matches) == 1

    @pytest.mark.parametrize("backend", get_available_backends())
    def test_all_backends_consistent(self, backend):
        """All available backends should give same results."""
        keywords = ["PEPT", "TIDE", "SEQ"]
        text = "PEPTIDESEQUENCE"
        ac = create_automaton(keywords, backend=backend)
        matches = list(ac.find_all(text))
        keywords_found = {m.keyword for m in matches}
        assert keywords_found == {"PEPT", "TIDE", "SEQ"}


class TestAnnotatePeptides:
    """Test peptide-protein annotation."""

    @pytest.fixture
    def proteins(self):
        """Sample proteins for testing."""
        return {
            "sp|P12345|PROT1": "MKWVTFISLLFSSAYSRGVFRRDTHK",
            "sp|P67890|PROT2": "MRGVFRRDTHKSEQ",
            "sp|Q11111|PROT3": "MXXUNIQUESEQXXX",
        }

    def test_annotate_basic(self, proteins):
        """Should find peptides in proteins."""
        peptides = ["GVFRR", "DTHK"]
        result = annotate_peptides(peptides, proteins)
        assert len(result) == 4  # Each peptide in 2 proteins
        assert result.peptides == {"GVFRR", "DTHK"}
        assert len(result.proteins) == 2

    def test_annotate_unique_peptide(self, proteins):
        """Should correctly identify unique peptide."""
        peptides = ["UNIQUE"]
        result = annotate_peptides(peptides, proteins)
        assert len(result) == 1
        assert result.proteins == {"sp|Q11111|PROT3"}

    def test_annotate_no_match(self, proteins):
        """Should return empty result for no matches."""
        peptides = ["ZZZZZ"]
        result = annotate_peptides(peptides, proteins)
        assert len(result) == 0

    def test_annotate_empty_peptides(self, proteins):
        """Should handle empty peptide list."""
        result = annotate_peptides([], proteins)
        assert len(result) == 0

    def test_annotate_deduplicates_peptides(self, proteins):
        """Should deduplicate input peptides."""
        peptides = ["GVFRR", "GVFRR", "GVFRR"]
        result = annotate_peptides(peptides, proteins)
        assert len(result.peptides) == 1

    def test_annotation_result_properties(self, proteins):
        """AnnotationResult should have correct properties."""
        peptides = ["GVFRR", "UNIQUE"]
        result = annotate_peptides(peptides, proteins)
        assert result.peptides == {"GVFRR", "UNIQUE"}
        assert "sp|Q11111|PROT3" in result.proteins

    def test_peptide_annotation_dataclass(self):
        """PeptideAnnotation should be frozen with correct attributes."""
        ann = PeptideAnnotation(
            peptide="TEST", protein_id="PROT1", start=5, end=9
        )
        assert ann.peptide == "TEST"
        assert ann.protein_id == "PROT1"
        assert ann.start == 5
        assert ann.end == 9
        assert ann.length == 4

    def test_to_dataframe(self, proteins):
        """Should convert to pandas DataFrame."""
        peptides = ["GVFRR"]
        result = annotate_peptides(peptides, proteins)
        df = result.to_dataframe()
        assert len(df) == 2
        assert set(df.columns) == {"peptide", "protein_id", "start", "end", "length"}


class TestFilterTryptic:
    """Test tryptic peptide filtering."""

    @pytest.fixture
    def proteins(self):
        return {
            "P1": "MKPEPTIDEARK",  # M at 0, K at 2, R at 10, K at 11
        }

    def test_filter_after_k(self, proteins):
        """Peptide after K should be tryptic."""
        peptides = ["PEPTIDE"]
        result = annotate_peptides(peptides, proteins)
        filtered = result.filter_tryptic(proteins)
        assert len(filtered) == 1

    def test_filter_at_nterm(self, proteins):
        """Peptide at N-terminus should be tryptic by default."""
        peptides = ["MK"]
        result = annotate_peptides(peptides, proteins)
        filtered = result.filter_tryptic(proteins, allow_n_term=True)
        assert len(filtered) == 1

    def test_filter_not_at_nterm(self, proteins):
        """Peptide at N-terminus rejected when allow_n_term=False."""
        peptides = ["MK"]
        result = annotate_peptides(peptides, proteins)
        filtered = result.filter_tryptic(proteins, allow_n_term=False)
        assert len(filtered) == 0


class TestSparseMatrix:
    """Test PeptideProteinMatrix."""

    @pytest.fixture
    def simple_annotations(self):
        """Simple annotation result for testing."""
        from diann_runner.prozor.annotate import AnnotationResult

        annotations = [
            PeptideAnnotation("PEP1", "PROT1", 0, 4),
            PeptideAnnotation("PEP1", "PROT2", 5, 9),  # Shared peptide
            PeptideAnnotation("PEP2", "PROT1", 10, 14),
            PeptideAnnotation("PEP3", "PROT3", 0, 4),  # Unique peptide
        ]
        return AnnotationResult(annotations=annotations)

    def test_from_annotations_shape(self, simple_annotations):
        """Matrix should have correct shape."""
        matrix = PeptideProteinMatrix.from_annotations(simple_annotations)
        assert matrix.shape == (3, 3)  # 3 peptides x 3 proteins
        assert matrix.n_peptides == 3
        assert matrix.n_proteins == 3

    def test_from_annotations_binary(self, simple_annotations):
        """Default matrix should be binary."""
        matrix = PeptideProteinMatrix.from_annotations(simple_annotations)
        dense = matrix.to_dense()
        assert set(dense.flatten()) <= {0.0, 1.0}

    def test_from_annotations_inverse_weighting(self, simple_annotations):
        """Inverse weighting should normalize rows."""
        matrix = PeptideProteinMatrix.from_annotations(
            simple_annotations, weighting="inverse"
        )
        dense = matrix.to_dense()
        # Each row should sum to 1.0
        row_sums = dense.sum(axis=1)
        np.testing.assert_allclose(row_sums, [1.0, 1.0, 1.0])

    def test_peptides_per_protein(self, simple_annotations):
        """Should count peptides per protein correctly."""
        matrix = PeptideProteinMatrix.from_annotations(simple_annotations)
        counts = matrix.peptides_per_protein()
        # PROT1 has 2 peptides (PEP1, PEP2), PROT2 has 1 (PEP1), PROT3 has 1 (PEP3)
        assert counts.sum() == 4

    def test_proteins_per_peptide(self, simple_annotations):
        """Should count proteins per peptide correctly."""
        matrix = PeptideProteinMatrix.from_annotations(simple_annotations)
        counts = matrix.proteins_per_peptide()
        # PEP1 in 2 proteins, PEP2 in 1, PEP3 in 1
        assert sorted(counts) == [1, 1, 2]

    def test_proteotypic_peptides(self, simple_annotations):
        """Should identify proteotypic peptides."""
        matrix = PeptideProteinMatrix.from_annotations(simple_annotations)
        proteotypic = matrix.proteotypic_peptides()
        assert len(proteotypic) == 2  # PEP2 and PEP3
        assert "PEP1" not in proteotypic

    def test_proteotypic_fraction(self, simple_annotations):
        """Should calculate proteotypic fraction."""
        matrix = PeptideProteinMatrix.from_annotations(simple_annotations)
        fraction = matrix.proteotypic_fraction()
        assert fraction == pytest.approx(2 / 3)

    def test_density(self, simple_annotations):
        """Should calculate density correctly."""
        matrix = PeptideProteinMatrix.from_annotations(simple_annotations)
        # 4 non-zero entries / (3 * 3) = 4/9
        assert matrix.density == pytest.approx(4 / 9)

    def test_subset_peptides(self, simple_annotations):
        """Should create subset with specified peptide rows."""
        matrix = PeptideProteinMatrix.from_annotations(simple_annotations)
        subset = matrix.subset_peptides(np.array([0, 1]))
        assert subset.n_peptides == 2
        assert subset.n_proteins == 3

    def test_remove_zero_rows(self, simple_annotations):
        """Should remove rows with no protein matches."""
        matrix = PeptideProteinMatrix.from_annotations(simple_annotations)
        # All rows have matches, so nothing removed
        cleaned = matrix.remove_zero_rows()
        assert cleaned.n_peptides == 3


class TestGreedyParsimony:
    """Test greedy parsimony protein inference."""

    def test_simple_inference(self):
        """Basic protein inference test."""
        from diann_runner.prozor.annotate import AnnotationResult

        # PROT1 has unique peptide, PROT2 and PROT3 share all peptides
        annotations = [
            PeptideAnnotation("PEP1", "PROT1", 0, 4),
            PeptideAnnotation("PEP2", "PROT2", 0, 4),
            PeptideAnnotation("PEP2", "PROT3", 0, 4),
            PeptideAnnotation("PEP3", "PROT2", 5, 9),
            PeptideAnnotation("PEP3", "PROT3", 5, 9),
        ]
        result = AnnotationResult(annotations=annotations)
        matrix = PeptideProteinMatrix.from_annotations(result)
        inference = greedy_parsimony(matrix)

        assert inference.n_groups == 2  # PROT1 alone, PROT2+PROT3 grouped
        assert inference.n_peptides == 3

    def test_indistinguishable_proteins(self):
        """Proteins with identical peptides should be grouped."""
        from diann_runner.prozor.annotate import AnnotationResult

        # PROT1 and PROT2 have exactly the same peptides
        annotations = [
            PeptideAnnotation("PEP1", "PROT1", 0, 4),
            PeptideAnnotation("PEP1", "PROT2", 0, 4),
            PeptideAnnotation("PEP2", "PROT1", 5, 9),
            PeptideAnnotation("PEP2", "PROT2", 5, 9),
        ]
        result = AnnotationResult(annotations=annotations)
        matrix = PeptideProteinMatrix.from_annotations(result)
        inference = greedy_parsimony(matrix)

        assert inference.n_groups == 1
        assert inference.groups[0].n_proteins == 2
        assert set(inference.groups[0].proteins) == {"PROT1", "PROT2"}

    def test_greedy_selects_largest_first(self):
        """Should select protein with most peptides first."""
        from diann_runner.prozor.annotate import AnnotationResult

        # PROT1 has 3 peptides, PROT2 has 1 peptide
        annotations = [
            PeptideAnnotation("PEP1", "PROT1", 0, 4),
            PeptideAnnotation("PEP2", "PROT1", 5, 9),
            PeptideAnnotation("PEP3", "PROT1", 10, 14),
            PeptideAnnotation("PEP4", "PROT2", 0, 4),
        ]
        result = AnnotationResult(annotations=annotations)
        matrix = PeptideProteinMatrix.from_annotations(result)
        inference = greedy_parsimony(matrix)

        assert inference.n_groups == 2
        # First group should have 3 peptides
        assert inference.groups[0].n_peptides == 3

    def test_protein_group_dataclass(self):
        """ProteinGroup should have correct attributes."""
        group = ProteinGroup(
            proteins=["PROT1", "PROT2"],
            peptides=["PEP1", "PEP2"],
        )
        assert group.protein_id == "PROT1;PROT2"
        assert group.n_peptides == 2
        assert group.n_proteins == 2

    def test_greedy_result_to_dict(self):
        """Should convert result to peptide->protein mapping."""
        from diann_runner.prozor.annotate import AnnotationResult

        annotations = [
            PeptideAnnotation("PEP1", "PROT1", 0, 4),
            PeptideAnnotation("PEP2", "PROT2", 0, 4),
        ]
        result = AnnotationResult(annotations=annotations)
        matrix = PeptideProteinMatrix.from_annotations(result)
        inference = greedy_parsimony(matrix)

        mapping = inference.to_dict()
        assert "PEP1" in mapping
        assert "PEP2" in mapping

    def test_greedy_result_to_dataframe(self):
        """Should convert result to DataFrame."""
        from diann_runner.prozor.annotate import AnnotationResult

        annotations = [
            PeptideAnnotation("PEP1", "PROT1", 0, 4),
        ]
        result = AnnotationResult(annotations=annotations)
        matrix = PeptideProteinMatrix.from_annotations(result)
        inference = greedy_parsimony(matrix)

        df = inference.to_dataframe()
        assert len(df) == 1
        assert set(df.columns) == {"peptide", "protein_group", "n_proteins_in_group"}

    def test_empty_matrix(self):
        """Should handle empty input gracefully."""
        from diann_runner.prozor.annotate import AnnotationResult

        result = AnnotationResult(annotations=[])
        matrix = PeptideProteinMatrix.from_annotations(result)
        inference = greedy_parsimony(matrix)
        assert inference.n_groups == 0


class TestIntegration:
    """Integration tests for full workflow."""

    def test_full_workflow(self):
        """Test complete annotation -> matrix -> inference pipeline."""
        proteins = {
            "PROT_A": "MKPEPTIDESEQUENCER",
            "PROT_B": "MSEQUENCEROTHER",
            "PROT_C": "MXUNIQUEPEPTIDEX",
        }
        peptides = ["PEPTIDE", "SEQUENCER", "UNIQUE"]

        # Annotate
        annotations = annotate_peptides(peptides, proteins)
        assert len(annotations) > 0

        # Build matrix
        matrix = annotations.to_sparse_matrix()
        assert matrix.n_peptides == 3
        assert matrix.n_proteins == 3

        # Run inference
        inference = greedy_parsimony(matrix)
        assert inference.n_peptides == 3

        # PROT_A and PROT_B share SEQUENCER, but PROT_A has PEPTIDE too
        # So PROT_A should be selected first (most peptides)
        # PROT_C has unique UNIQUE peptide

    def test_weighted_matrix_in_inference(self):
        """Verify inverse weighting doesn't break inference."""
        proteins = {
            "PROT_A": "MKSHAREDPEPTIDE",
            "PROT_B": "MXSHAREDPEPTIDE",
        }
        peptides = ["SHARED"]

        annotations = annotate_peptides(peptides, proteins)
        matrix = annotations.to_sparse_matrix(weighting="inverse")
        inference = greedy_parsimony(matrix)

        # Both proteins are indistinguishable (same peptide)
        assert inference.n_groups == 1
        assert inference.groups[0].n_proteins == 2
