# RAG benchmark (NOT a unit test with asserts: it MEASURES retrieval quality,
# it gives no pass/fail). For a fixed set of clinical cases, one or more for
# each of the 10 specialists, it builds the search queries exactly as
# specialist_node does (clinical.py) and checks whether the retrieved chunks
# include a guideline of the right specialty. It prints hit@1 (the first chunk
# is from the right specialty) and hit@3 (at least one of the 3 is), per case,
# per specialist and in total - so every change to corpus, indexing or
# retrieval is compared on the same cases instead of "by eye" on a chat.
#
# It also reports:
# - cases with MIXED symptoms (different specialties in the same card), see
#   MIXED_CASES: "overlap" = how many chunks retrieved with ALL the symptoms
#   match those retrieved with the pertinent symptom alone (3/3 = the other
#   symptoms did not disturb the search);
# - 2 off-topic queries, to see what scores unrelated chunks get;
# - a count of the noise in the index, per file: almost empty chunks, glued
#   words (failed PDF text extraction) and bibliography.
#
# A document's specialty is the prefix of its file name
# ("cardio_simeu_dolore_toracico.pdf" -> "cardio"), see ROLE_PREFIX.
#
# The index is NOT opened directly in data/chroma_db: Chroma may rewrite its
# files just by opening them, so it is copied to a temporary folder (outside
# the project) first. No model, no API quota.
#
# Usage: python -m tests.benchmarks.rag_retrieval
import logging
import os
import re
import shutil
import tempfile
import warnings
from collections import Counter, defaultdict
from pathlib import Path

# The embedding model is already in the local cache after the first index
# build - no network calls to HuggingFace during the measurement.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

from src.rag import retriever  # noqa: E402
from src.rag.build_index import CHROMA_DIR  # noqa: E402

K = 3

# Same names as SPECIALIST_DISPLAY_NAMES in src/agents/clinical.py - copied
# instead of imported because importing src.agents creates the LLM clients and
# the patient database connection, useless (and with side effects) here.
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

# File name prefix of each specialty's documents in data/guidelines/.
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

# Clinical cases: (role of the specialist speaking, symptom descriptions as the
# reviewer would store them in PatientCard).
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

# Cases with symptoms of different specialties in the same card: (role, all
# the symptoms in the card, the symptom that concerns that specialist). The
# pertinent symptom is given ONLY to compute the reference result - the app's
# retrieval does not know it.
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
# Credits pages (authors, signatures, affiliations): from the right specialty
# but useless to a specialist, so they must not count as a hit.
CREDITS = re.compile(r"\b(AUTORI|COORDINATOR[EI]|hanno collaborato|gruppo di lavoro|revisori|a cura d[ie]l|"
                     r"Universit[àa] degli Studi|Ospedale|IRCCS|U\.?O\.?C?\b|Dott\.?(ssa)?\s|Dr\.?(ssa)?\s|Prof\.?\s)",
                     re.IGNORECASE)


def looks_like_credits(text: str) -> bool:
    """HELPER looks_like_credits: many names/institutions on mostly short lines = a credits page, not guidance."""
    lines = [line for line in text.splitlines() if line.strip()]
    short = sum(1 for line in lines if len(line) < 60) / max(len(lines), 1)
    return len(CREDITS.findall(text)) >= 3 and short >= 0.6


def build_query(role: str, descriptions: list[str]) -> list[str]:
    """HELPER build_query: the same queries as specialist_node (one per symptom), without any consult text."""
    return retriever.build_queries(DISPLAY_NAMES[role], descriptions)


def case_label(role: str, descriptions: list[str]) -> str:
    """HELPER case_label: "Specialty - symptom, symptom" for the printed table."""
    return f"{DISPLAY_NAMES[role]} - {', '.join(descriptions)}"


def short_name(source_file: str) -> str:
    """HELPER short_name: file name without .pdf."""
    return source_file.removesuffix(".pdf")


def evaluate_cases() -> None:
    """BENCHMARK cases: hit@1 and hit@3 per case and per specialist, using retrieve() exactly as the app does."""
    per_role = defaultdict(lambda: [0, 0, 0, 0])  # cases, hit@1, hit@3, chunks of the specialty
    credits_found = 0
    print("=" * 100)
    print(f"CLINICAL CASES (OK = first chunk from the right specialty, ~ = within the first {K}, NO = none; "
          "credits pages never count)")
    print("=" * 100)
    for role, descriptions in CASES:
        results = retriever.retrieve(build_query(role, descriptions), role, k=K)
        hits = [chunk.source_file.startswith(ROLE_PREFIX[role] + "_") and not looks_like_credits(chunk.text)
                for chunk in results]
        credits_found += sum(looks_like_credits(chunk.text) for chunk in results)

        stats = per_role[role]
        stats[0] += 1
        stats[1] += bool(hits and hits[0])
        stats[2] += any(hits)
        stats[3] += sum(hits)

        mark = "OK" if hits and hits[0] else ("~ " if any(hits) else "NO")
        found = ", ".join(f"{short_name(c.source_file)} p.{c.page_number}({c.score:.3f})" for c in results)
        print(f"{mark} {case_label(role, descriptions)[:62]:62s} -> {found}")

    print()
    print(f"{'specialist':22s} {'cases':>5s} {'hit@1':>6s} {'hit@3':>6s} {'own chunks':>12s}  documents in corpus")
    total = [0, 0, 0, 0]
    corpus_files = sorted(p.name for p in (CHROMA_DIR.parent / "guidelines").glob("*.pdf"))
    for role in DISPLAY_NAMES:
        n, h1, h3, own = per_role[role]
        total = [a + b for a, b in zip(total, (n, h1, h3, own))]
        n_docs = sum(1 for f in corpus_files if f.startswith(ROLE_PREFIX[role] + "_"))
        print(f"{role:22s} {n:5d} {h1:6d} {h3:6d} {own:5d}/{n * K:<6d}  {n_docs}")
    print(f"{'TOTAL':22s} {total[0]:5d} {total[1]:6d} {total[2]:6d} {total[3]:5d}/{total[0] * K:<6d}")
    print(f"credits chunks (authors, signatures) retrieved: {credits_found}")


def _chunk_key(chunk) -> tuple:
    """HELPER _chunk_key: identity of a chunk (file, page, start of the text)."""
    return (chunk.source_file, chunk.page_number, chunk.text[:80])


def evaluate_mixed_cases() -> None:
    """BENCHMARK mixed cases: overlap between retrieval with all the symptoms and with the pertinent one only."""
    print()
    print("=" * 100)
    print("MIXED-SYMPTOM CASES (overlap with the retrieval on the pertinent symptom only)")
    print("=" * 100)
    total_overlap = 0
    for role, descriptions, pertinent in MIXED_CASES:
        mixed = retriever.retrieve(build_query(role, descriptions), role, k=K)
        ideal = retriever.retrieve(build_query(role, [pertinent]), role, k=K)
        ideal_keys = {_chunk_key(c) for c in ideal}
        overlap = sum(1 for c in mixed if _chunk_key(c) in ideal_keys)
        total_overlap += overlap
        print(f"{overlap}/{K} {DISPLAY_NAMES[role]} - pertinent symptom: {pertinent}")
        print("      with all symptoms:  " + ", ".join(f"{short_name(c.source_file)} p.{c.page_number}" for c in mixed))
        print("      pertinent only:     " + ", ".join(f"{short_name(c.source_file)} p.{c.page_number}" for c in ideal))
    print(f"--> total overlap {total_overlap}/{len(MIXED_CASES) * K}")


def evaluate_off_topic() -> None:
    """BENCHMARK off-topic: scores of chunks retrieved for queries with nothing to do with medicine."""
    print()
    print("=" * 100)
    print("OFF-TOPIC QUERIES (no chunk should really be pertinent)")
    print("=" * 100)
    for query in OFF_TOPIC:
        results = retriever.retrieve(query, "cardiologist", k=K)
        found = ", ".join(f"{short_name(c.source_file)}({c.score:.3f})" for c in results)
        print(f"   {query:62s} -> {found}")


def noise_report(vectorstore) -> None:
    """BENCHMARK noise: per file, chunks that are almost empty, have glued words or are bibliography."""
    data = vectorstore._collection.get(include=["documents", "metadatas"])
    counts = defaultdict(Counter)
    for text, meta in zip(data["documents"], data["metadatas"]):
        source = meta.get("source_file", "?")
        text = text.removeprefix("passage: ")
        words = text.split()
        avg_word_len = sum(len(w) for w in words) / max(len(words), 1)
        c = counts[source]
        c["total"] += 1
        if len(text) < 200:
            c["almost_empty"] += 1
        if avg_word_len > 12:
            c["glued"] += 1
        if len(BIBLIOGRAPHY.findall(text)) >= 3:
            c["bibliography"] += 1

    print()
    print("=" * 100)
    print("NOISE IN THE INDEX (almost empty chunks <200 characters, glued words, bibliography)")
    print("=" * 100)
    print(f"{'file':42s} {'total':>7s} {'empty':>7s} {'glued':>8s} {'biblio':>7s}")
    total = Counter()
    for source in sorted(counts):
        c = counts[source]
        total.update(c)
        print(f"{source:42s} {c['total']:7d} {c['almost_empty']:7d} {c['glued']:8d} {c['bibliography']:7d}")
    print(f"{'TOTAL':42s} {total['total']:7d} {total['almost_empty']:7d} {total['glued']:8d} {total['bibliography']:7d}")


def main() -> None:
    """BENCHMARK main: runs every measurement on a temporary copy of the index."""
    if not CHROMA_DIR.exists():
        raise SystemExit(f"Index not found in {CHROMA_DIR} - first run: python -m src.rag.build_index")

    with tempfile.TemporaryDirectory(prefix="vita_rag_eval_", ignore_cleanup_errors=True) as tmp:
        copy_dir = Path(tmp) / "chroma_db"
        shutil.copytree(CHROMA_DIR, copy_dir)

        # The production retriever reads CHROMA_DIR on its first call: point it
        # at the copy, so the measurement uses the app's own index-opening code.
        retriever.CHROMA_DIR = copy_dir
        vectorstore = retriever._get_vectorstore()

        evaluate_cases()
        evaluate_mixed_cases()
        evaluate_off_topic()
        noise_report(vectorstore)
        del vectorstore


if __name__ == "__main__":
    main()
