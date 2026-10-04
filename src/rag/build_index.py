"""Builds the guideline index. Run by hand when data/guidelines/ changes: python -m src.rag.build_index"""

import re
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path

from huggingface_hub import snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Project folder.
GUIDELINES_DIR = PROJECT_ROOT / "data" / "guidelines"  # The source PDF files.

CHROMA_DIR = PROJECT_ROOT / "data" / "chroma_db"  # The index, kept in the repository with the PDFs.

EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"  # Local embedding model, also used by retriever.py.

COLLECTION_NAME = "linee_guida_cliniche"  # Name of the collection inside the index.


def load_embeddings() -> HuggingFaceEmbeddings:
    """The embedding model, loaded from the local cache when present (no network calls)."""
    try:
        model_path = snapshot_download(EMBEDDING_MODEL_NAME, local_files_only=True)
    except LocalEntryNotFoundError:
        print(f"Embedding model not in the local cache yet: downloading it ({EMBEDDING_MODEL_NAME})...")
        model_path = EMBEDDING_MODEL_NAME
    return HuggingFaceEmbeddings(model_name=model_path)


MIN_CHUNK_CHARS = 80  # Shorter chunks are stray titles or page leftovers.

MAX_AVG_WORD_LEN = 12  # Above this the text was extracted with the words glued together.

# Marks of a reference list.
_BIBLIOGRAPHY = re.compile(r"(et al\.|doi[:\s]|N Engl J Med|Lancet|;\s*\d{4}\s*[;:(])", re.IGNORECASE)
# Conflict-of-interest statements.
_CONFLICT_OF_INTEREST = re.compile(r"conflitt\w*\s+d\w*\s+interess", re.IGNORECASE)
_DOT_LEADER = re.compile(r"(\.\s?){5,}")  # Dotted lines of a table of contents.
_PAGE_NUMBER_LINE = re.compile(r"\s*\d{1,4}\s*")  # A line holding only a page number.

_INDICATOR = re.compile(r"\b(numeratore|denominatore)\b", re.IGNORECASE)  # Statistical indicator sheets.
# Lists of authors and reviewers.
_AUTHORS = re.compile(
    r"\b(a cura d[ie]l|gruppo di lavoro|redazione del documento|revisori|project manager|"
    r"coordinamento del gruppo|hanno collaborato)\b",
    re.IGNORECASE,
)
_SEARCH_STRATEGY = re.compile(r"\.ti,ab|\bexp [a-z]|search terms", re.IGNORECASE)  # Literature search strings.
# Heading of a glossary of abbreviations.
_GLOSSARY_HEADER = re.compile(r"^\W*(\d+\.?\s*)?(acronimi|abbreviazioni|sigle|glossario)\b", re.IGNORECASE)
_ACRONYM_LINE = re.compile(r"^[A-Z][A-Z/\-]{1,9}\s+[A-Za-zÀ-ù]")  # A glossary line: abbreviation, then its meaning.
_TOC_LINE = re.compile(r"\s\d{1,3}\s*$")  # A line ending with a page number.
_SENTENCE_END = re.compile(r"[a-zà-ù][.;:]\s")  # End of a sentence: tells prose from lists.

# Pages left out by hand, each with its reason; check a page has no useful text before adding it.
EXCLUDED_PAGES = {
    "generale_fvg_manuale_triage_adulto_2018.pdf": {
        11: "triage levels chart: only the names of the sheets",
    },
    "generale_triage_piemonte.pdf": {
        27: "list of indications for short observation: only names of conditions",
        28: "list of indications for short observation, continued",
    },
    "generale_umbria_sepsi.pdf": {
        1: "working group and acknowledgements",
    },
    "cardio_cardarelli_pdta_dolore_toracico.pdf": {
        2: "working group and approval signatures",
    },
    "dermatologia_aniarti_ustioni_ps.pdf": {
        1: "title and authors' names",
        9: "authors' names and acknowledgements",
    },
    "dermatologia_aopisa_orticaria_angioedema.pdf": {
        1: "front page of the procedure: drafting and approval signatures",
    },
    "neuro_fvg_pdta_ictus_fase_acuta.pdf": {
        5: "coordination, reviewers and drafting method",
    },
    "oftalmologia_soi_pronto_soccorso.pdf": {
        5: "secretariat, publisher and board",
        6: "coordinator and list of authors",
        7: "list of authors, continued",
        8: "list of authors, continued",
        9: "acknowledgements",
    },
    "ortopedia_siot_trauma_maggiore.pdf": {
        7: "guideline development group",
        8: "reviewers and working groups",
        9: "ethics reviewer and secretariat",
        22: "list of the societies invited to the scoping workshop",
        23: "list of the participating societies",
    },
    "pneumo_campania_pdta_asma.pdf": {
        4: "priorities of the care pathway and working group",
    },
}


def _line_key(line: str) -> str:
    """A line with its numbers masked, to recognise the same header on different pages."""
    return re.sub(r"\d+", "#", " ".join(line.split())).lower()


def clean_pages(pages: list[str]) -> list[str]:
    """The pages of one document without repeated headers, page numbers and split words."""
    repeated = set()
    if len(pages) >= 4:
        counts = Counter()
        for page in pages:
            counts.update({_line_key(line) for line in page.splitlines() if line.strip()})
        threshold = max(3, 0.3 * len(pages))
        repeated = {key for key, n in counts.items() if n >= threshold and len(key) > 3}

    cleaned = []
    for page in pages:
        lines = [
            line for line in page.splitlines()
            if _line_key(line) not in repeated and not _PAGE_NUMBER_LINE.fullmatch(line)
        ]
        text = "\n".join(lines)
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        text = text.replace("\t", " ")
        text = re.sub(r"[  ]{2,}", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        cleaned.append(text.strip())
    return cleaned


def discard_reason(text: str) -> str | None:
    """Why a chunk must not be indexed, or None if it is kept."""
    if len(text) < MIN_CHUNK_CHARS:
        return "too short"
    words = [w for w in text.split() if not _DOT_LEADER.fullmatch(w)]
    if words and sum(len(w) for w in words) / len(words) > MAX_AVG_WORD_LEN:
        return "glued words"
    if len(_DOT_LEADER.findall(text)) >= 3:
        return "table of contents"
    if len(_BIBLIOGRAPHY.findall(text)) >= 3:
        return "bibliography"
    if _CONFLICT_OF_INTEREST.search(text):
        return "conflict of interest"

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    n_lines = len(lines)
    if len(_INDICATOR.findall(text)) >= 2:
        return "indicators"
    if len(_SEARCH_STRATEGY.findall(text)) >= 3:
        return "search strategy"
    short_lines = sum(1 for line in lines if len(line) < 50)
    if (_AUTHORS.search(text) and n_lines >= 5 and short_lines / n_lines >= 0.7
            and len(_SENTENCE_END.findall(text + " ")) <= 2):
        return "authors"
    if n_lines <= 2 and re.match(r"\W*a cura d[ie]l\b", text, re.IGNORECASE):
        return "authors"
    acronym_lines = sum(1 for line in lines if _ACRONYM_LINE.match(line))
    if n_lines >= 3 and (
        (any(_GLOSSARY_HEADER.match(line) for line in lines[:3]) and acronym_lines / n_lines >= 0.4)
        or (n_lines >= 8 and acronym_lines / n_lines >= 0.6)
    ):
        return "glossary"
    if n_lines >= 5 and sum(1 for line in lines if _TOC_LINE.search(line)) / n_lines >= 0.6:
        return "table of contents"
    return None


def specialty_from_filename(filename: str) -> str:
    """The specialty of a document: the part of its file name before the first underscore."""
    return filename.split("_", 1)[0]


def _retry_fs_op(op, label: str) -> None:
    """Repeats a file operation until it succeeds: just-written files may be briefly locked."""
    MAX_ATTEMPTS = 40
    WAIT_BETWEEN = 5
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            op()
            return
        except (PermissionError, OSError) as e:
            print(f"  [{label}] attempt {attempt}/{MAX_ATTEMPTS}: file busy ({type(e).__name__}), retrying in {WAIT_BETWEEN}s...")
            time.sleep(WAIT_BETWEEN)
    raise SystemExit(
        f"[{label}] operation failed after {MAX_ATTEMPTS} attempts: "
        "the files are still locked by the synchronisation. Run the script again."
    )


def _wait_until_readable(persist_directory: str, embeddings: HuggingFaceEmbeddings, label: str) -> None:
    """Opens and queries the index until it really works, instead of waiting a fixed time."""
    MAX_ATTEMPTS = 60
    WAIT_BETWEEN = 5
    for attempt in range(1, MAX_ATTEMPTS + 1):
        time.sleep(WAIT_BETWEEN)
        try:
            test_client = Chroma(
                embedding_function=embeddings,
                persist_directory=persist_directory,
                collection_name=COLLECTION_NAME,
            )
            test_client.similarity_search("query: prova di lettura", k=1)
            del test_client
            print(f"  [{label}] readable after {attempt * WAIT_BETWEEN}s")
            return
        except Exception as e:
            print(f"  [{label}] attempt {attempt}/{MAX_ATTEMPTS}: not ready yet ({type(e).__name__})")
    raise SystemExit(
        f"[{label}] the index did not become readable within the maximum "
        f"wait ({MAX_ATTEMPTS * WAIT_BETWEEN}s). Run the script again."
    )


def main() -> None:
    """Reads, cleans, splits, filters and embeds the PDFs, then replaces the index."""
    pdf_paths = sorted(GUIDELINES_DIR.glob("*.pdf"))
    if not pdf_paths:
        raise SystemExit(f"No PDF found in {GUIDELINES_DIR}")

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)

    chunks = []
    discarded_total = Counter()
    for pdf_path in pdf_paths:
        pages = PyPDFLoader(str(pdf_path)).load()
        for page, text in zip(pages, clean_pages([p.page_content for p in pages])):
            page.page_content = text

        discarded = Counter()
        excluded = EXCLUDED_PAGES.get(pdf_path.name, {})
        if excluded:
            # PyPDFLoader counts pages from 0, EXCLUDED_PAGES from 1.
            pages = [p for p in pages if p.metadata.get("page", 0) + 1 not in excluded]
            discarded["excluded page"] = len(excluded)

        kept = []
        for chunk in splitter.split_documents(pages):
            reason = discard_reason(chunk.page_content)
            if reason:
                discarded[reason] += 1
                continue
            # The embedding model requires the "passage: " prefix on indexed text.
            chunk.page_content = "passage: " + chunk.page_content
            chunk.metadata["source_file"] = pdf_path.name
            chunk.metadata["specialty"] = specialty_from_filename(pdf_path.name)
            chunk.metadata["page_number"] = chunk.metadata.get("page", 0) + 1
            kept.append(chunk)
        chunks.extend(kept)
        discarded_total.update(discarded)

        discarded_text = ", ".join(f"{n} {why}" for why, n in discarded.most_common()) or "none"
        print(f"  {pdf_path.name}: {len(pages)} pages -> {len(kept)} chunks (discarded: {discarded_text})")

    discarded_text = ", ".join(f"{n} {why}" for why, n in discarded_total.most_common()) or "none"
    print(f"\nTotal: {len(chunks)} chunks from {len(pdf_paths)} documents (discarded: {discarded_text})")
    print(f"Loading the embedding model ({EMBEDDING_MODEL_NAME})...")
    embeddings = load_embeddings()

    # Build outside the project folder, then copy: an index written in a synchronised folder was corrupted.
    with tempfile.TemporaryDirectory(
        prefix="vita_chroma_build_", ignore_cleanup_errors=True
    ) as staging_dir:
        print(f"Building the index in a temporary folder ({staging_dir})...")
        vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=staging_dir,
            collection_name=COLLECTION_NAME,
        )
        del vectorstore

        print("Checking that the index is readable before copying it...")
        _wait_until_readable(staging_dir, embeddings, "write")

        print(f"Copying the finished index to {CHROMA_DIR}...")
        if CHROMA_DIR.exists():
            _retry_fs_op(lambda: shutil.rmtree(CHROMA_DIR), "removing the old index")
        _retry_fs_op(lambda: shutil.copytree(staging_dir, CHROMA_DIR), "copying the new index")

    print("Checking that the index copied to data/ is readable...")
    _wait_until_readable(str(CHROMA_DIR), embeddings, "copy in data/")

    print("Index built.")


if __name__ == "__main__":
    main()
