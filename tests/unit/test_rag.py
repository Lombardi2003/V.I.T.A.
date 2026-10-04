"""RAG: retrieval split between specialty and general documents, queries, and index cleaning (no real index used)."""
import types
import unittest
from unittest import mock

try:
    from . import helpers  # noqa: F401  (sets up the environment: project path, UTF-8)
except ImportError:
    import helpers  # noqa: F401

from src.rag import retriever
from src.rag.build_index import MIN_CHUNK_CHARS, clean_pages, discard_reason, specialty_from_filename

PROSE = ("Il paziente con dolore toracico tipico va sottoposto a ECG entro 10 minuti dall'arrivo; "
         "in presenza di sopraslivellamento del tratto ST si attiva la rete per l'angioplastica primaria.")


class FakeIndex:
    """HELPER FakeIndex: in-memory index; each specialty has chunks with fixed scores, every search is recorded."""

    def __init__(self, chunks):
        self.chunks = chunks          # {specialty: [(text, score), ...]}
        self.searches = []

    def similarity_search_with_score(self, query, k, filter):
        self.searches.append((query, filter["specialty"], k))
        found = sorted(self.chunks.get(filter["specialty"], []), key=lambda c: c[1])[:k]
        return [(types.SimpleNamespace(page_content=f"passage: {text}",
                                       metadata={"source_file": f"{filter['specialty']}_doc.pdf", "page_number": 1}), score)
                for text, score in found]


class TestRetrieve(unittest.TestCase):
    def retrieve(self, index, *args, **kwargs):
        """HELPER retrieve: calls retrieve() on the fake index."""
        with mock.patch.object(retriever, "_get_vectorstore", lambda: index):
            return retriever.retrieve(*args, **kwargs)

    def test_missing_index_returns_nothing(self):
        """TEST retrieve: without an index on disk, retrieve returns an empty list instead of an error."""
        self.assertEqual(self.retrieve(None, "dolore toracico", "cardiologist"), [])

    def test_specialty_and_general_split(self):
        """TEST retrieve: with k=3, two chunks come from the role's specialty and one from the general documents."""
        index = FakeIndex({"cardio": [("c1", 0.1), ("c2", 0.2), ("c3", 0.3)], "generale": [("g1", 0.05), ("g2", 0.4)]})
        chunks = self.retrieve(index, ["Cardiologia - dolore toracico"], "cardiologist", k=3)
        self.assertEqual([c.text for c in chunks], ["g1", "c1", "c2"])     # ordered by score
        self.assertEqual(chunks[0].citation, "generale_doc, p. 1")
        self.assertFalse(any(c.text.startswith("passage:") for c in chunks))

    def test_specialty_with_few_documents_is_filled_with_general_ones(self):
        """TEST retrieve: if the specialty has fewer chunks than expected, the rest comes from the general documents."""
        index = FakeIndex({"ent": [("e1", 0.3)], "generale": [("g1", 0.1), ("g2", 0.2)]})
        chunks = self.retrieve(index, "vertigini", "ent", k=3)
        self.assertEqual(sorted(c.text for c in chunks), ["e1", "g1", "g2"])

    def test_general_practitioner_uses_only_general_documents(self):
        """TEST retrieve: the GP (and no role) search only the general documents."""
        index = FakeIndex({"generale": [("g1", 0.1), ("g2", 0.2), ("g3", 0.3)], "cardio": [("c1", 0.0)]})
        for role in ("general_practitioner", None):
            with self.subTest(role=role):
                self.assertEqual([c.text for c in self.retrieve(index, "febbre", role)], ["g1", "g2", "g3"])
        self.assertEqual({s[1] for s in index.searches}, {"generale"})

    def test_same_chunk_from_two_queries_counted_once(self):
        """TEST retrieve: a chunk found by two symptom queries appears once, with its best score."""
        index = FakeIndex({"generale": [("g1", 0.1), ("g2", 0.2)]})
        chunks = self.retrieve(index, ["Medicina - tosse", "Medicina - febbre"], "general_practitioner", k=3)
        self.assertEqual([c.text for c in chunks], ["g1", "g2"])
        self.assertTrue(all(q.startswith("query: ") for q, _, _ in index.searches))

    def test_one_query_per_symptom_plus_the_consult(self):
        """TEST build_queries: one query per symptom, empty symptoms skipped, plus one for the consult text."""
        self.assertEqual(retriever.build_queries("Neurologia", ["mal di testa", " ", "vista sfocata"], extra="serve una TC?"),
                         ["Neurologia - mal di testa", "Neurologia - vista sfocata", "Neurologia - serve una TC?"])
        self.assertEqual(retriever.build_queries("Neurologia", []), ["Neurologia"])


class TestIndexCleaning(unittest.TestCase):
    def test_headers_page_numbers_and_hyphens_removed(self):
        """TEST clean_pages: repeated headers, page-number lines and words split by a hyphen are fixed."""
        bodies = ["La diagno-\nsi si basa  sull'ECG.", "Troponina seriata.", "Terapia antiaggregante.",
                  "Criteri di dimissione.", "Follow-up ambulatoriale."]
        pages = [f"PDTA Dolore Toracico Versione 00 Pag. {n} a 72\n{n}\n{body}" for n, body in enumerate(bodies, 1)]
        cleaned = clean_pages(pages)
        self.assertEqual(cleaned[0], "La diagnosi si basa sull'ECG.")
        self.assertEqual(cleaned[1:], bodies[1:])

    def test_short_documents_keep_their_lines(self):
        """TEST clean_pages: with fewer than 4 pages no line is treated as a repeated header."""
        pages = ["Titolo comune\nTesto uno", "Titolo comune\nTesto due"]
        self.assertEqual(clean_pages(pages), pages)

    def test_noise_chunks_are_discarded(self):
        """TEST discard_reason: short pieces, bibliographies, tables of contents and glossaries are discarded."""
        cases = {
            "too short": "Pag. 3",
            "bibliography": "Rossi A et al. N Engl J Med 2019; 380: 11. Bianchi B et al. Lancet 2020; 395: 1. "
                            "Verdi C et al. doi: 10.1000/xyz",
            "table of contents": "Introduzione ........ 3\nMetodi ........ 5\nRisultati ........ 9\nDiscussione ........ 12",
            "glossary": "Acronimi\nECG Elettrocardiogramma\nPA Pressione arteriosa\nFC Frequenza cardiaca\n"
                         "TC Tomografia computerizzata",
        }
        for reason, text in cases.items():
            with self.subTest(reason=reason):
                self.assertEqual(discard_reason(text.ljust(MIN_CHUNK_CHARS) if reason != "too short" else text), reason)

    def test_clinical_prose_is_kept(self):
        """TEST discard_reason: an ordinary clinical paragraph is kept."""
        self.assertIsNone(discard_reason(PROSE))

    def test_excluded_pages_point_to_real_documents(self):
        """TEST EXCLUDED_PAGES: every excluded page belongs to a PDF that exists in data/guidelines, with a reason."""
        from src.rag.build_index import EXCLUDED_PAGES, GUIDELINES_DIR
        for name, pages in EXCLUDED_PAGES.items():
            with self.subTest(document=name):
                self.assertTrue((GUIDELINES_DIR / name).exists())
                self.assertTrue(all(isinstance(n, int) and n >= 1 and reason.strip() for n, reason in pages.items()))

    def test_specialty_from_file_name(self):
        """TEST specialty_from_filename: the specialty is the file name prefix before the first underscore."""
        self.assertEqual(specialty_from_filename("cardio_fvg_pdta_stemi_2022.pdf"), "cardio")
        self.assertEqual(specialty_from_filename("generale_triage_piemonte.pdf"), "generale")


if __name__ == "__main__":
    unittest.main()
