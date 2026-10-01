# Script diagnostico (NON un test automatico con assert - serve a MISURARE la
# qualita' del recupero RAG, non a dare un verdetto passa/non passa): per una
# serie di casi clinici, uno o piu' per ciascuno dei 10 specialisti, costruisce
# la query di ricerca nello stesso formato di specialist_node (clinical.py) e
# controlla se tra i pezzi recuperati c'e' una linea guida della specialita'
# giusta. Stampa hit@1 (il primo pezzo e' della specialita' giusta) e hit@3
# (almeno uno dei 3 lo e'), per singolo caso, per specialista e in totale -
# cosi' ogni modifica al corpus/indicizzazione/recupero si confronta sempre
# sugli stessi casi, invece che "a occhio" su una conversazione in chat.
#
# Riporta anche:
# - casi con sintomi MISTI (di specialita' diverse nella stessa cartella), vedi
#   MIXED_CASES sotto;
# - 2 query volutamente fuori tema, per vedere che punteggi prendono pezzi
#   non pertinenti (utile per decidere se una soglia di pertinenza ha senso);
# - un conteggio del rumore nell'indice, per file: pezzi quasi vuoti, con
#   parole incollate (estrazione del testo dal PDF non riuscita) e di
#   bibliografia.
#
# La specialita' di un documento si ricava dal prefisso del nome del file
# (es. "cardio_simeu_dolore_toracico.pdf" -> "cardio"), vedi ROLE_PREFIX sotto.
#
# L'indice NON viene aperto direttamente in data/chroma_db: Chroma puo'
# riscrivere i propri file anche solo aprendoli, quindi lo copiamo prima in una
# cartella temporanea (fuori dal progetto) e lavoriamo sulla copia.
#
# Uso: python -m tests.test_rag_retrieval
import logging
import os
import re
import shutil
import tempfile
import warnings
from collections import Counter, defaultdict
from pathlib import Path

# Il modello di embedding e' gia' in cache locale dopo la prima build
# dell'indice - niente chiamate di rete a HuggingFace durante la misura.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

from src.rag import retriever  # noqa: E402
from src.rag.build_index import CHROMA_DIR  # noqa: E402

K = 3

# Stessi nomi di SPECIALIST_DISPLAY_NAMES in src/agents/clinical.py - copiati
# qui invece di importarli perche' importare src.agents crea i client LLM e la
# connessione al database dei pazienti, inutili (e con effetti collaterali) per
# una misura del solo recupero.
DISPLAY_NAMES = {
    "cardiologist": "Cardiologia",
    "neurologist": "Neurologia",
    "dermatologist": "Dermatologia",
    "orthopedist": "Ortopedia",
    "gastroenterologist": "Gastroenterologia",
    "pulmonologist": "Pneumologia",
    "ent": "Otorinolaringoiatria",
    "ophthalmologist": "Oftalmologia",
    "urologist": "Urologia",
    "general_practitioner": "Medicina",
}

# Prefisso del nome file dei documenti di ciascuna specialita' in data/guidelines/.
ROLE_PREFIX = {
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

# Casi clinici: (ruolo dello specialista che parla, descrizioni dei sintomi
# come le salverebbe il revisore in PatientCard).
CASES = [
    ("cardiologist", ["dolore toracico oppressivo", "sudorazione fredda"]),
    ("cardiologist", ["palpitazioni", "senso di svenimento"]),
    ("cardiologist", ["dolore al petto che si irradia al braccio sinistro"]),
    ("neurologist", ["debolezza al braccio destro", "difficoltà a parlare"]),
    ("neurologist", ["bocca storta", "formicolio alla mano"]),
    ("neurologist", ["mal di testa improvviso e violento"]),
    ("dermatologist", ["macchie rosse pruriginose sulla pelle"]),
    ("dermatologist", ["chiazza desquamante tra le dita dei piedi"]),
    ("dermatologist", ["ustione alla mano"]),
    ("dermatologist", ["pomfi pruriginosi", "gonfiore delle labbra"]),
    ("dermatologist", ["gamba arrossata, calda e dolente", "febbre"]),
    ("orthopedist", ["dolore all'anca dopo una caduta"]),
    ("orthopedist", ["dolore alla gamba dopo incidente stradale"]),
    ("orthopedist", ["distorsione alla caviglia", "gonfiore alla caviglia"]),
    ("gastroenterologist", ["dolore addominale", "vomito"]),
    ("gastroenterologist", ["sangue nelle feci"]),
    ("gastroenterologist", ["dolore addominale dopo pasti grassi"]),
    ("pulmonologist", ["difficoltà respiratoria", "tosse persistente"]),
    ("pulmonologist", ["dolore toracico quando respiro", "fiato corto"]),
    ("pulmonologist", ["attacco d'asma"]),
    ("ent", ["mal d'orecchio", "febbre"]),
    ("ent", ["sangue dal naso"]),
    ("ent", ["mal di gola", "difficoltà a deglutire"]),
    ("ophthalmologist", ["occhio rosso", "dolore oculare"]),
    ("ophthalmologist", ["corpo estraneo nell'occhio"]),
    ("ophthalmologist", ["perdita improvvisa della vista"]),
    ("urologist", ["dolore al fianco", "bruciore quando urino"]),
    ("urologist", ["colica renale"]),
    ("urologist", ["impossibilità a urinare"]),
    ("general_practitioner", ["febbre alta", "stanchezza"]),
    ("general_practitioner", ["svenimento"]),
    ("general_practitioner", ["malessere generale", "febbre"]),
]

# Casi con sintomi di specialita' diverse nella stessa cartella: (ruolo,
# tutti i sintomi in cartella, il sintomo che riguarda quello specialista).
# Nei CASES sopra ogni query parla di una sola specialita', quindi non potevano
# mostrare un problema visto nella prova reale del tavolo rotondo
# (tests/test_round_table.py): con "dolore addominale" + "eruzione cutanea" in
# cartella, la query del gastroenterologo conteneva anche l'eruzione, e invece
# del documento sul dolore addominale recuperava pagine di contorno (autori,
# abbreviazioni, indicatori).
#
# Misura: "sovrapposizione" = quanti dei pezzi recuperati con TUTTI i sintomi
# coincidono con quelli recuperati con il SOLO sintomo pertinente (il
# risultato "ideale"). 3/3 = gli altri sintomi in cartella non hanno disturbato
# la ricerca; 0/3 = l'hanno stravolta. Il sintomo pertinente e' indicato qui
# SOLO per calcolare questo riferimento - il recupero dell'app non lo conosce.
MIXED_CASES = [
    ("gastroenterologist", ["dolore addominale tipo crampi", "eruzione cutanea con macchie rosse pruriginose"], "dolore addominale tipo crampi"),
    ("dermatologist", ["dolore addominale tipo crampi", "eruzione cutanea con macchie rosse pruriginose"], "eruzione cutanea con macchie rosse pruriginose"),
    ("cardiologist", ["dolore toracico oppressivo", "formicolio alla mano", "vista sfocata"], "dolore toracico oppressivo"),
    ("neurologist", ["mal di testa improvviso e violento", "bruciore quando urino"], "mal di testa improvviso e violento"),
    ("urologist", ["mal di testa improvviso e violento", "bruciore quando urino"], "bruciore quando urino"),
    ("orthopedist", ["dolore all'anca dopo una caduta", "tosse persistente", "febbre"], "dolore all'anca dopo una caduta"),
    ("pulmonologist", ["dolore all'anca dopo una caduta", "tosse persistente", "febbre"], "tosse persistente"),
    ("ophthalmologist", ["occhio rosso", "mal di gola", "febbre"], "occhio rosso"),
    ("ent", ["occhio rosso", "mal di gola", "febbre"], "mal di gola"),
]

OFF_TOPIC = [
    "ricetta della carbonara con guanciale",
    "risultati del campionato di calcio",
]

BIBLIOGRAPHY = re.compile(r"(et al\.|doi|N Engl J Med|Lancet|;\s*\d{4})", re.IGNORECASE)


def build_query(role: str, descriptions: list[str]) -> list[str]:
    """Le stesse query di specialist_node (retriever.build_queries: una per
    sintomo), senza il contenuto di un eventuale mini-consulto."""
    return retriever.build_queries(DISPLAY_NAMES[role], descriptions)


def case_label(role: str, descriptions: list[str]) -> str:
    return f"{DISPLAY_NAMES[role]} - {', '.join(descriptions)}"


def short_name(source_file: str) -> str:
    return source_file.removesuffix(".pdf")


def evaluate_cases() -> None:
    """Usa retriever.retrieve() cosi' come la chiama specialist_node (query +
    ruolo, quindi con il filtro per specialita'), non una ricerca rifatta a
    parte - la misura riguarda esattamente il recupero dell'app."""
    per_role = defaultdict(lambda: [0, 0, 0, 0])  # casi, hit@1, hit@3, pezzi della specialita'
    print("=" * 100)
    print(f"CASI CLINICI (OK = primo pezzo della specialita' giusta, ~ = tra i primi {K}, NO = nessuno)")
    print("=" * 100)
    for role, descriptions in CASES:
        query = build_query(role, descriptions)
        results = retriever.retrieve(query, role, k=K)
        hits = [chunk.source_file.startswith(ROLE_PREFIX[role] + "_") for chunk in results]

        stats = per_role[role]
        stats[0] += 1
        stats[1] += bool(hits and hits[0])
        stats[2] += any(hits)
        stats[3] += sum(hits)

        mark = "OK" if hits and hits[0] else ("~ " if any(hits) else "NO")
        found = ", ".join(f"{short_name(c.source_file)} p.{c.page_number}({c.score:.3f})" for c in results)
        print(f"{mark} {case_label(role, descriptions)[:62]:62s} -> {found}")

    print()
    print(f"{'specialista':22s} {'casi':>4s} {'hit@1':>6s} {'hit@3':>6s} {'pezzi spec.':>12s}  documenti nel corpus")
    total = [0, 0, 0, 0]
    corpus_files = sorted(p.name for p in (CHROMA_DIR.parent / "guidelines").glob("*.pdf"))
    for role in DISPLAY_NAMES:
        n, h1, h3, own = per_role[role]
        total = [a + b for a, b in zip(total, (n, h1, h3, own))]
        n_docs = sum(1 for f in corpus_files if f.startswith(ROLE_PREFIX[role] + "_"))
        print(f"{role:22s} {n:4d} {h1:6d} {h3:6d} {own:5d}/{n * K:<6d}  {n_docs}")
    print(f"{'TOTALE':22s} {total[0]:4d} {total[1]:6d} {total[2]:6d} {total[3]:5d}/{total[0] * K:<6d}")


def _chunk_key(chunk) -> tuple:
    return (chunk.source_file, chunk.page_number, chunk.text[:80])


def evaluate_mixed_cases() -> None:
    print()
    print("=" * 100)
    print("CASI CON SINTOMI MISTI (sovrapposizione con il recupero sul solo sintomo pertinente)")
    print("=" * 100)
    total_overlap = 0
    for role, descriptions, pertinent in MIXED_CASES:
        mixed = retriever.retrieve(build_query(role, descriptions), role, k=K)
        ideal = retriever.retrieve(build_query(role, [pertinent]), role, k=K)
        ideal_keys = {_chunk_key(c) for c in ideal}
        overlap = sum(1 for c in mixed if _chunk_key(c) in ideal_keys)
        total_overlap += overlap
        print(f"{overlap}/{K} {DISPLAY_NAMES[role]} - sintomo pertinente: {pertinent}")
        print("      con tutti i sintomi: " + ", ".join(f"{short_name(c.source_file)} p.{c.page_number}" for c in mixed))
        print("      solo il pertinente:  " + ", ".join(f"{short_name(c.source_file)} p.{c.page_number}" for c in ideal))
    print(f"--> sovrapposizione totale {total_overlap}/{len(MIXED_CASES) * K}")


def evaluate_off_topic() -> None:
    print()
    print("=" * 100)
    print("QUERY FUORI TEMA (nessun pezzo dovrebbe essere davvero pertinente)")
    print("=" * 100)
    for query in OFF_TOPIC:
        results = retriever.retrieve(query, "cardiologist", k=K)
        found = ", ".join(f"{short_name(c.source_file)}({c.score:.3f})" for c in results)
        print(f"   {query:62s} -> {found}")


def noise_report(vectorstore) -> None:
    data = vectorstore._collection.get(include=["documents", "metadatas"])
    counts = defaultdict(Counter)
    for text, meta in zip(data["documents"], data["metadatas"]):
        source = meta.get("source_file", "?")
        text = text.removeprefix("passage: ")
        words = text.split()
        avg_word_len = sum(len(w) for w in words) / max(len(words), 1)
        c = counts[source]
        c["totale"] += 1
        if len(text) < 200:
            c["quasi_vuoti"] += 1
        if avg_word_len > 12:
            c["incollati"] += 1
        if len(BIBLIOGRAPHY.findall(text)) >= 3:
            c["bibliografia"] += 1

    print()
    print("=" * 100)
    print("RUMORE NELL'INDICE (pezzi quasi vuoti <200 caratteri, parole incollate, bibliografia)")
    print("=" * 100)
    print(f"{'file':42s} {'totale':>7s} {'vuoti':>7s} {'incoll.':>8s} {'biblio':>7s}")
    total = Counter()
    for source in sorted(counts):
        c = counts[source]
        total.update(c)
        print(f"{source:42s} {c['totale']:7d} {c['quasi_vuoti']:7d} {c['incollati']:8d} {c['bibliografia']:7d}")
    print(f"{'TOTALE':42s} {total['totale']:7d} {total['quasi_vuoti']:7d} {total['incollati']:8d} {total['bibliografia']:7d}")


def main() -> None:
    if not CHROMA_DIR.exists():
        raise SystemExit(f"Indice non trovato in {CHROMA_DIR} - eseguire prima: python -m src.rag.build_index")

    with tempfile.TemporaryDirectory(prefix="vita_rag_eval_", ignore_cleanup_errors=True) as tmp:
        copy_dir = Path(tmp) / "chroma_db"
        shutil.copytree(CHROMA_DIR, copy_dir)

        # Il retriever di produzione legge CHROMA_DIR al momento della prima
        # chiamata: lo puntiamo sulla copia, cosi' la misura usa lo stesso
        # identico codice di apertura dell'indice dell'app.
        retriever.CHROMA_DIR = copy_dir
        vectorstore = retriever._get_vectorstore()

        evaluate_cases()
        evaluate_mixed_cases()
        evaluate_off_topic()
        noise_report(vectorstore)
        del vectorstore


if __name__ == "__main__":
    main()
