# Funzione di recupero usata da specialist_node (src/agents/clinical.py) ad
# ogni turno del tavolo rotondo - legge l'indice gia' costruito da
# build_index.py, non lo ricostruisce. Se l'indice non esiste ancora (build_index
# mai eseguito), retrieve() restituisce una lista vuota invece di sollevare un
# errore: RAG e' un contesto facoltativo in piu' (vedi SPECIALIST_PROMPT, "se
# pertinenti, tienine conto"), il tavolo rotondo deve continuare a funzionare
# anche senza, esattamente come faceva prima di oggi.
from functools import lru_cache
from pathlib import Path

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from .build_index import CHROMA_DIR, EMBEDDING_MODEL_NAME


@lru_cache
def _get_vectorstore() -> Chroma | None:
    if not CHROMA_DIR.exists():
        return None
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
    return Chroma(
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR),
        collection_name="linee_guida_cliniche",
    )


def retrieve(query: str, k: int = 3) -> list[str]:
    """Restituisce fino a k pezzi di linee guida piu' pertinenti alla query.

    "query: " obbligatorio per multilingual-e5-small sulle query di ricerca
    (simmetrico al "passage: " gia' applicato ai documenti in build_index.py) -
    senza questo prefisso la qualita' del recupero peggiora sensibilmente,
    documentato esplicitamente dagli autori del modello.
    """
    vectorstore = _get_vectorstore()
    if vectorstore is None:
        return []

    results = vectorstore.similarity_search(f"query: {query}", k=k)
    # Rimuoviamo il prefisso "passage: " prima di restituire il testo: era
    # necessario solo per l'embedding, non deve comparire nel prompt dello
    # specialista.
    return [doc.page_content.removeprefix("passage: ") for doc in results]
