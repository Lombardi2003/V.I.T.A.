"""Retrieval of guideline chunks for a specialist's turn, from the index built by build_index.py."""

from dataclasses import dataclass
from functools import lru_cache

from langchain_chroma import Chroma

from .build_index import CHROMA_DIR, COLLECTION_NAME, load_embeddings

# Role -> prefix of the documents of its specialty.
ROLE_SPECIALTY = {
    "cardiologist": "cardio",
    "neurologist": "neuro",
    "dermatologist": "dermatologia",
    "orthopedist": "ortopedia",
    "gastroenterologist": "gastro",
    "pulmonologist": "pneumo",
    "ent": "ent",
    "ophthalmologist": "oftalmologia",
    "urologist": "urologia",
    "general_practitioner": "generale",
}

GENERAL_SPECIALTY = "generale"  # Documents shared by every specialist (triage, sepsis).


@dataclass
class RetrievedChunk:
    """One retrieved chunk, with where it comes from."""
    text: str
    source_file: str
    page_number: int
    score: float  # Distance from the query: lower is closer.

    @property
    def citation(self) -> str:
        """The reference shown to the specialist: document and page."""
        return f"{self.source_file.removesuffix('.pdf')}, p. {self.page_number}"


@lru_cache
def _get_vectorstore() -> Chroma | None:
    """The index, opened once; None if it has not been built."""
    if not CHROMA_DIR.exists():
        return None
    return Chroma(
        embedding_function=load_embeddings(),
        persist_directory=str(CHROMA_DIR),
        collection_name=COLLECTION_NAME,
    )


def warm_up() -> None:
    """Loads the embedding model and the index at startup."""
    _get_vectorstore()


def build_queries(display_name: str, symptoms: list[str], extra: str = "") -> list[str]:
    """One query per symptom, plus one for a question addressed to the specialist."""
    queries = [f"{display_name} - {s}" for s in symptoms if s.strip()] or [display_name]
    if extra.strip():
        queries.append(f"{display_name} - {extra}")
    return queries


def _search(vectorstore: Chroma, query: str, specialty: str, k: int) -> list[RetrievedChunk]:
    """The k chunks of one specialty closest to one query."""
    if k <= 0:
        return []
    results = vectorstore.similarity_search_with_score(
        # The embedding model requires the "query: " prefix on searches.
        f"query: {query}", k=k, filter={"specialty": specialty}
    )
    return [
        RetrievedChunk(
            text=doc.page_content.removeprefix("passage: "),
            source_file=doc.metadata.get("source_file", "?"),
            page_number=doc.metadata.get("page_number", 0),
            score=score,
        )
        for doc, score in results
    ]


def _search_all(vectorstore: Chroma, queries: list[str], specialty: str, k: int) -> list[RetrievedChunk]:
    """The k best chunks over all the queries, without duplicates."""
    best: dict[tuple, RetrievedChunk] = {}
    for query in queries:
        for chunk in _search(vectorstore, query, specialty, k):
            key = (chunk.source_file, chunk.page_number, chunk.text)
            if key not in best or chunk.score < best[key].score:
                best[key] = chunk
    return sorted(best.values(), key=lambda chunk: chunk.score)[:k]


def retrieve(queries: str | list[str], role: str | None = None, k: int = 3) -> list[RetrievedChunk]:
    """Up to k chunks: k-1 from the role's own documents and one from the general ones."""
    vectorstore = _get_vectorstore()
    # No index: return nothing, the table works without guidelines.
    if vectorstore is None:
        return []
    if isinstance(queries, str):
        queries = [queries]

    specialty = ROLE_SPECIALTY.get(role or "", GENERAL_SPECIALTY)
    if specialty == GENERAL_SPECIALTY:
        return _search_all(vectorstore, queries, GENERAL_SPECIALTY, k)

    # Without this split the general triage manual took every place.
    own = _search_all(vectorstore, queries, specialty, k - 1)
    general = _search_all(vectorstore, queries, GENERAL_SPECIALTY, k - len(own))
    return sorted(own + general, key=lambda chunk: chunk.score)
