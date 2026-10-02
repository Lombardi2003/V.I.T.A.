# Funzione di recupero usata da specialist_node (src/agents/clinical.py) ad
# ogni turno del tavolo rotondo - legge l'indice gia' costruito da
# build_index.py, non lo ricostruisce. Se l'indice non esiste ancora (build_index
# mai eseguito), retrieve() restituisce una lista vuota invece di sollevare un
# errore: RAG e' un contesto facoltativo in piu' (vedi SPECIALIST_PROMPT, "se
# pertinenti, tienine conto"), il tavolo rotondo deve continuare a funzionare
# anche senza.
from dataclasses import dataclass
from functools import lru_cache

from langchain_chroma import Chroma

from .build_index import CHROMA_DIR, COLLECTION_NAME, load_embeddings

# Specialita' dei documenti in data/guidelines/ (prefisso del nome del file,
# vedi specialty_from_filename in build_index.py) per ciascun ruolo del tavolo
# (i ruoli sono quelli di ALL_SPECIALISTS in src/agents/prompts.py).
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

# Documenti trasversali (triage, sepsi, ...) - validi per tutti gli specialisti.
GENERAL_SPECIALTY = "generale"


@dataclass
class RetrievedChunk:
    text: str
    source_file: str
    page_number: int
    score: float  # distanza dalla query: piu' basso = piu' simile

    @property
    def citation(self) -> str:
        """Riferimento da mostrare allo specialista e da citare in fonti_consultate."""
        return f"{self.source_file.removesuffix('.pdf')}, p. {self.page_number}"


@lru_cache
def _get_vectorstore() -> Chroma | None:
    if not CHROMA_DIR.exists():
        return None
    return Chroma(
        embedding_function=load_embeddings(),
        persist_directory=str(CHROMA_DIR),
        collection_name=COLLECTION_NAME,
    )


def warm_up() -> None:
    """Carica subito modello di embedding e indice, invece che al primo turno
    del primo specialista (che altrimenti risultava sensibilmente piu' lento
    degli altri). Da chiamare una volta all'avvio dell'app."""
    _get_vectorstore()


def build_queries(display_name: str, symptoms: list[str], extra: str = "") -> list[str]:
    """Una query per ciascun sintomo ("Neurologia - mal di testa improvviso"),
    piu' una per il testo di un eventuale mini-consulto rivolto allo specialista.

    Prima c'era un'unica query con TUTTI i sintomi della cartella: con sintomi
    di ambiti diversi (es. dolore addominale + eruzione cutanea), quelli fuori
    dall'ambito dello specialista "sporcavano" la ricerca - nella prova reale il
    gastroenterologo riceveva pagine di contorno invece del documento sul
    dolore addominale (misurato con tests/benchmarks/rag_retrieval.py, casi misti).
    Con una query per sintomo nessuno decide a priori quale sintomo riguardi
    quale specialista: vince il sintomo le cui ricerche trovano i passaggi piu'
    simili (vedi retrieve() sotto) - lo specialista continua comunque a vedere
    e discutere l'intera cartella clinica, questo riguarda solo cosa si cerca
    nelle linee guida."""
    queries = [f"{display_name} - {s}" for s in symptoms if s.strip()] or [display_name]
    if extra.strip():
        queries.append(f"{display_name} - {extra}")
    return queries


def _search(vectorstore: Chroma, query: str, specialty: str, k: int) -> list[RetrievedChunk]:
    if k <= 0:
        return []
    # "query: " obbligatorio per multilingual-e5-small sulle query di ricerca
    # (simmetrico al "passage: " applicato ai documenti in build_index.py) -
    # senza questo prefisso la qualita' del recupero peggiora sensibilmente,
    # documentato esplicitamente dagli autori del modello.
    results = vectorstore.similarity_search_with_score(
        f"query: {query}", k=k, filter={"specialty": specialty}
    )
    # Il prefisso "passage: " serviva solo per l'embedding, non deve comparire
    # nel prompt dello specialista.
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
    """Esegue ogni query e tiene i k pezzi migliori in assoluto (senza
    duplicati: lo stesso pezzo puo' uscire per piu' sintomi)."""
    best: dict[tuple, RetrievedChunk] = {}
    for query in queries:
        for chunk in _search(vectorstore, query, specialty, k):
            key = (chunk.source_file, chunk.page_number, chunk.text)
            if key not in best or chunk.score < best[key].score:
                best[key] = chunk
    return sorted(best.values(), key=lambda chunk: chunk.score)[:k]


def retrieve(queries: str | list[str], role: str | None = None, k: int = 3) -> list[RetrievedChunk]:
    """Restituisce fino a k pezzi di linee guida pertinenti alle query (una o
    piu', vedi build_queries), ordinati dal piu' simile.

    Con un ruolo: k-1 pezzi dai documenti della specialita' di quel ruolo + 1
    dai documenti generali (triage, sepsi). Senza questa ripartizione i
    documenti generali - in particolare il manuale di triage FVG, che ha una
    scheda per quasi ogni sintomo - occupavano da soli le prime posizioni per
    neurologia/ortopedia/pneumologia, lasciando lo specialista senza le linee
    guida del proprio ambito (misurato con tests/benchmarks/rag_retrieval.py: con il
    solo filtro "specialita' + generali", 57 pezzi su 90 della specialita'
    giusta; con questa ripartizione, 63 su 90 e almeno uno in tutti i 30 casi).
    Il pezzo generale resta utile: di solito e' la scheda di triage del sintomo,
    cioe' il riferimento per il codice di urgenza. Se la specialita' ha meno
    documenti pertinenti del previsto, il resto viene dai documenti generali.

    Senza ruolo (o con un ruolo senza specialita' propria, come il medico
    generico): tutti i k pezzi dai documenti generali.
    """
    vectorstore = _get_vectorstore()
    if vectorstore is None:
        return []
    if isinstance(queries, str):
        queries = [queries]

    specialty = ROLE_SPECIALTY.get(role or "", GENERAL_SPECIALTY)
    if specialty == GENERAL_SPECIALTY:
        return _search_all(vectorstore, queries, GENERAL_SPECIALTY, k)

    own = _search_all(vectorstore, queries, specialty, k - 1)
    general = _search_all(vectorstore, queries, GENERAL_SPECIALTY, k - len(own))
    return sorted(own + general, key=lambda chunk: chunk.score)
