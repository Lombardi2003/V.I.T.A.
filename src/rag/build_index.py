# Script da eseguire UNA TANTUM (non fa parte del flusso dell'app): legge i PDF
# di linee guida cliniche in data/guidelines/, li spezzetta, li trasforma in
# vettori con un modello di embedding LOCALE (nessuna quota/costo esterno - vedi
# src/agents/common.py per lo storico dei problemi di quota con Gemini/Groq) e
# li salva in un indice Chroma persistente su disco (data/chroma_db/), usato poi
# da src/rag/retriever.py durante il tavolo rotondo.
#
# Uso: python -m src.rag.build_index
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
GUIDELINES_DIR = PROJECT_ROOT / "data" / "guidelines"

# Destinazione FINALE (dentro il progetto, committabile - vedi CHROMA_DIR sotto):
# deve stare in data/ insieme ai PDF sorgente, non fuori dal repository.
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma_db"

# Stesso modello usato da retriever.py - vedi commento li' per il dettaglio dei
# prefissi "query: "/"passage: " richiesti da questo modello specifico.
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"

COLLECTION_NAME = "linee_guida_cliniche"


def load_embeddings() -> HuggingFaceEmbeddings:
    """Modello di embedding, caricato dalla cache locale se c'e' gia'.

    Passando solo il nome del modello, la libreria interroga HuggingFace a ogni
    avvio per controllare i file (decine di richieste HEAD, visibili nei log
    dell'app) anche se il modello e' gia' scaricato: avvio piu' lento e
    dipendenza dalla rete. Se il modello e' in cache lo carichiamo invece dalla
    sua cartella locale, senza nessuna chiamata; se non c'e' (primo avvio su un
    PC nuovo, es. dopo aver clonato il progetto) lo scarichiamo come prima, una
    volta sola.
    """
    try:
        model_path = snapshot_download(EMBEDDING_MODEL_NAME, local_files_only=True)
    except LocalEntryNotFoundError:
        print(f"Modello di embedding non ancora in cache: lo scarico ({EMBEDDING_MODEL_NAME})...")
        model_path = EMBEDDING_MODEL_NAME
    return HuggingFaceEmbeddings(model_name=model_path)

# --- Pulizia del testo e filtro dei pezzi ---
# Il testo estratto dai PDF contiene molto materiale che non e' contenuto
# clinico: intestazioni/pie' di pagina ripetuti su ogni pagina, numeri di
# pagina, sommari con i puntini, bibliografie, dichiarazioni di conflitto di
# interessi. Indicizzati cosi' com'erano, questi pezzi finivano tra i risultati
# anche per query che non c'entravano (misurato con tests/test_rag_retrieval.py:
# pezzi di solo numero di pagina, pezzi con parole incollate recuperati per
# epistassi/febbre/colica). Qui il testo viene prima ripulito pagina per pagina,
# poi i pezzi che restano comunque inutili vengono scartati prima di finire
# nell'indice.

# Sotto questa lunghezza un pezzo e' un titolo isolato o un residuo di pagina.
# Non piu' alta di cosi': anche la coda di una pagina puo' essere breve ma utile
# (es. "SHOCK, CON IPOPERFUSIONE SEVERA" nel manuale di triage FVG, ~100
# caratteri - verificato a campione con una soglia di 200, che la scartava).
MIN_CHUNK_CHARS = 80

# Lunghezza media delle parole oltre la quale il testo e' "incollato"
# (estrazione dal PDF non riuscita: "inItaliapiùutilizzabile") o non e' prosa
# (es. elenchi di codici separati da virgole senza spazi).
MAX_AVG_WORD_LEN = 12

_BIBLIOGRAPHY = re.compile(r"(et al\.|doi[:\s]|N Engl J Med|Lancet|;\s*\d{4}\s*[;:(])", re.IGNORECASE)
_CONFLICT_OF_INTEREST = re.compile(r"conflitt\w*\s+d\w*\s+interess", re.IGNORECASE)
_DOT_LEADER = re.compile(r"(\.\s?){5,}")          # "Metodologia ........ 4" dei sommari
_PAGE_NUMBER_LINE = re.compile(r"\s*\d{1,4}\s*")

# Materiale di contorno dei PDTA/linee guida, individuato guardando i pezzi
# recuperati nella prova reale del tavolo rotondo (tests/test_round_table.py) -
# per il gastroenterologo arrivavano elenco degli autori, glossario delle sigle
# e schede di indicatori statistici invece del contenuto clinico. Ogni regola e'
# stata verificata controllando a mano TUTTI i pezzi che scarta: provata e
# abbandonata una regola generica sugli "elenchi" (righe corte, poche frasi),
# perche' scartava anche tabelle cliniche vere (schede di triage FVG, gestione
# della riacutizzazione asmatica in PS, dosaggi dei farmaci).
_INDICATOR = re.compile(r"\b(numeratore|denominatore)\b", re.IGNORECASE)
_AUTHORS = re.compile(
    r"\b(a cura d[ie]l|gruppo di lavoro|redazione del documento|revisori|project manager|"
    r"coordinamento del gruppo|hanno collaborato)\b",
    re.IGNORECASE,
)
_SEARCH_STRATEGY = re.compile(r"\.ti,ab|\bexp [a-z]|search terms", re.IGNORECASE)  # stringhe Medline/Embase
_GLOSSARY_HEADER = re.compile(r"^\W*(\d+\.?\s*)?(acronimi|abbreviazioni|sigle|glossario)\b", re.IGNORECASE)
_ACRONYM_LINE = re.compile(r"^[A-Z][A-Z/\-]{1,9}\s+[A-Za-zÀ-ù]")        # "ECG Elettrocardiogramma"
_TOC_LINE = re.compile(r"\s\d{1,3}\s*$")                                  # "2.1 Definizione di Triage 6"
_SENTENCE_END = re.compile(r"[a-zà-ù][.;:]\s")


# Pagine escluse a mano dall'indice, con il motivo. Sono elenchi di soli titoli
# o nomi di patologie, senza contenuto clinico: proprio perche' nominano un po'
# di tutto, risultavano "simili" a quasi ogni query e uscivano in quasi tutti i
# turni del tavolo (misurato con tests/test_rag_retrieval.py e osservato nella
# prova reale, dove uno specialista li ha citati come se contenessero criteri
# clinici). Esclusi per pagina invece che con una regola automatica perche' le
# regole generiche sugli elenchi provate scartavano anche tabelle cliniche vere
# (vedi commento su _INDICATOR). Prima di aggiungere una pagina qui, verificare
# che NON contenga anche testo utile: es. p. 18 e 47 del manuale FVG iniziano
# con un elenco di schede ma poi contengono le note d'uso, e vanno tenute.
EXCLUDED_PAGES = {
    "generale_fvg_manuale_triage_adulto_2018.pdf": {
        11: "schema dei livelli di triage: solo i nomi delle schede",
    },
    "generale_triage_piemonte.pdf": {
        27: "elenco non esaustivo delle indicazioni all'OBI: solo nomi di patologie",
        28: "continuazione dell'elenco delle indicazioni all'OBI",
    },
}


def _line_key(line: str) -> str:
    """Chiave per riconoscere la stessa riga su pagine diverse: numeri
    normalizzati, cosi' "Pag. 5 a 72" e "Pag. 6 a 72" contano come uguali."""
    return re.sub(r"\d+", "#", " ".join(line.split())).lower()


def clean_pages(pages: list[str]) -> list[str]:
    """Ripulisce il testo delle pagine di UN documento.

    Toglie le righe ripetute su almeno il 30% delle pagine (intestazioni e pie'
    di pagina, es. "PDTA ... Versione n. 00 del 20/12/2024 Pag. 5 a 72") e le
    righe con il solo numero di pagina, riunisce le parole spezzate a fine riga
    ("diagno-\\nsi" -> "diagnosi") e normalizza spazi/tabulazioni/righe vuote.
    Le intestazioni si riconoscono solo confrontando le pagine tra loro, per
    questo la funzione lavora sull'intero documento e non pagina per pagina.
    """
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
    """Motivo per cui un pezzo non va indicizzato, oppure None se va tenuto."""
    if len(text) < MIN_CHUNK_CHARS:
        return "corto"
    words = [w for w in text.split() if not _DOT_LEADER.fullmatch(w)]
    if words and sum(len(w) for w in words) / len(words) > MAX_AVG_WORD_LEN:
        return "incollato"
    if len(_DOT_LEADER.findall(text)) >= 3:
        return "sommario"
    if len(_BIBLIOGRAPHY.findall(text)) >= 3:
        return "bibliografia"
    if _CONFLICT_OF_INTEREST.search(text):
        return "conflitto di interessi"

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    n_lines = len(lines)
    if len(_INDICATOR.findall(text)) >= 2:
        return "indicatori"
    if len(_SEARCH_STRATEGY.findall(text)) >= 3:
        return "strategia di ricerca"
    # Autori/revisioni: elenco di nomi e enti, righe corte e quasi nessuna frase
    # (senza questi vincoli la regola scartava anche paragrafi in prosa che
    # citano "il gruppo di lavoro").
    short_lines = sum(1 for line in lines if len(line) < 50)
    if (_AUTHORS.search(text) and n_lines >= 5 and short_lines / n_lines >= 0.7
            and len(_SENTENCE_END.findall(text + " ")) <= 2):
        return "autori"
    # ... oppure solo la riga "A cura del Gruppo di ..." rimasta isolata in un pezzo.
    if n_lines <= 2 and re.match(r"\W*a cura d[ie]l\b", text, re.IGNORECASE):
        return "autori"
    # Glossario di sigle: l'intestazione deve stare all'inizio del pezzo (se sta
    # in mezzo, prima c'e' contenuto vero da non buttare), oppure il pezzo e' la
    # continuazione del glossario (quasi tutte le righe "SIGLA Significato").
    acronym_lines = sum(1 for line in lines if _ACRONYM_LINE.match(line))
    if n_lines >= 3 and (
        (any(_GLOSSARY_HEADER.match(line) for line in lines[:3]) and acronym_lines / n_lines >= 0.4)
        or (n_lines >= 8 and acronym_lines / n_lines >= 0.6)
    ):
        return "glossario"
    # Sommario senza puntini: la maggior parte delle righe finisce con un numero di pagina.
    if n_lines >= 5 and sum(1 for line in lines if _TOC_LINE.search(line)) / n_lines >= 0.6:
        return "sommario"
    return None


def specialty_from_filename(filename: str) -> str:
    """Specialita' di un documento, dal prefisso del nome del file
    (convenzione di data/guidelines/: "cardio_fvg_pdta_stemi_2022.pdf" -> "cardio")."""
    return filename.split("_", 1)[0]


def _retry_fs_op(op, label: str) -> None:
    """Riprova un'operazione sul filesystem (cancellare/copiare una cartella)
    finche' non riesce, invece di fallire al primo tentativo.

    Stesso motivo di _wait_until_readable: OneDrive tiene per un po' un
    handle aperto sui file appena scritti/sincronizzati nella cartella del
    progetto. Verificato con un crash reale: shutil.rmtree(CHROMA_DIR) ha
    dato PermissionError [WinError 5] su un file dentro data/chroma_db
    rimasto dal tentativo precedente, ancora "occupato" da OneDrive - e un
    primo tentativo con soli 10x3s=30s di attesa non e' bastato (OneDrive
    stava probabilmente ancora caricando in cloud i ~37MB del tentativo
    precedente), quindi il budget qui e' molto piu' ampio che per la sola
    lettura.
    """
    MAX_ATTEMPTS = 40
    WAIT_BETWEEN = 5
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            op()
            return
        except (PermissionError, OSError) as e:
            print(f"  [{label}] tentativo {attempt}/{MAX_ATTEMPTS}: file occupato ({type(e).__name__}), riprovo tra {WAIT_BETWEEN}s...")
            time.sleep(WAIT_BETWEEN)
    raise SystemExit(
        f"[{label}] operazione fallita dopo {MAX_ATTEMPTS} tentativi: "
        "OneDrive continua a tenere occupati i file. Riprova a eseguire lo script."
    )


def _wait_until_readable(persist_directory: str, embeddings: HuggingFaceEmbeddings, label: str) -> None:
    """Riprova ad aprire un indice Chroma e a interrogarlo finche' non riesce
    davvero, invece di indovinare un tempo fisso di attesa.

    Necessario in DUE punti diversi, non solo uno: (1) subito dopo che Chroma
    ha scritto l'indice (il suo compattatore interno lavora in background,
    from_documents() puo' restituire il controllo prima che la scrittura sia
    davvero finita su disco) e (2) subito dopo aver COPIATO l'indice dentro
    data/ - perche' la cartella del progetto e' sincronizzata con OneDrive
    ("OneDrive - Unimore" nel percorso), e OneDrive tocca/sincronizza i file
    appena compaiono nella cartella anche se sono stati solo copiati (non
    scritti in incrementale) - verificato con un tentativo reale: la verifica
    subito dopo la scrittura passava, ma la lettura del file GIA' COPIATO
    dentro data/chroma_db falliva comunque subito dopo, riuscendo solo dopo
    aver aspettato. Un'attesa fissa (provati 3s, 10s) non e' affidabile - il
    tempo necessario varia da un tentativo all'altro sulla stessa macchina.
    """
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
            print(f"  [{label}] leggibile dopo {attempt * WAIT_BETWEEN}s")
            return
        except Exception as e:
            print(f"  [{label}] tentativo {attempt}/{MAX_ATTEMPTS}: non ancora pronto ({type(e).__name__})")
    raise SystemExit(
        f"[{label}] l'indice non e' diventato leggibile entro il tempo massimo "
        f"di attesa ({MAX_ATTEMPTS * WAIT_BETWEEN}s). Riprova a eseguire lo script."
    )


def main() -> None:
    pdf_paths = sorted(GUIDELINES_DIR.glob("*.pdf"))
    if not pdf_paths:
        raise SystemExit(f"Nessun PDF trovato in {GUIDELINES_DIR}")

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
            # "page" di PyPDFLoader parte da 0, EXCLUDED_PAGES usa la numerazione da 1.
            pages = [p for p in pages if p.metadata.get("page", 0) + 1 not in excluded]
            discarded["pagina esclusa"] = len(excluded)

        kept = []
        for chunk in splitter.split_documents(pages):
            reason = discard_reason(chunk.page_content)
            if reason:
                discarded[reason] += 1
                continue
            # "passage: " obbligatorio per multilingual-e5-small su ogni testo che
            # finisce nell'indice (a differenza delle query, che lo ricevono in
            # retriever.py al momento della ricerca, non qui in fase di indicizzazione).
            chunk.page_content = "passage: " + chunk.page_content
            chunk.metadata["source_file"] = pdf_path.name
            chunk.metadata["specialty"] = specialty_from_filename(pdf_path.name)
            # "page" di PyPDFLoader parte da 0: "page_number" e' quella da
            # citare come fonte (prima pagina = 1).
            chunk.metadata["page_number"] = chunk.metadata.get("page", 0) + 1
            kept.append(chunk)
        chunks.extend(kept)
        discarded_total.update(discarded)

        scartati = ", ".join(f"{n} {motivo}" for motivo, n in discarded.most_common()) or "nessuno"
        print(f"  {pdf_path.name}: {len(pages)} pagine -> {len(kept)} pezzi (scartati: {scartati})")

    scartati = ", ".join(f"{n} {motivo}" for motivo, n in discarded_total.most_common()) or "nessuno"
    print(f"\nTotale: {len(chunks)} pezzi da {len(pdf_paths)} documenti (scartati: {scartati})")
    print(f"Carico il modello di embedding ({EMBEDDING_MODEL_NAME})...")
    embeddings = load_embeddings()

    # Si scrive PRIMA in una cartella temporanea FUORI dal progetto (fuori da
    # OneDrive), poi si copia il risultato completo in data/chroma_db/ - MAI
    # scrivere l'indice direttamente dentro la cartella di progetto: la
    # sincronizzazione OneDrive in background corrompe l'indice HNSW binario
    # di Chroma MENTRE viene scritto (verificato con un test reale).
    with tempfile.TemporaryDirectory(
        prefix="vita_chroma_build_", ignore_cleanup_errors=True
    ) as staging_dir:
        print(f"Costruisco l'indice in una cartella temporanea ({staging_dir})...")
        vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=staging_dir,
            collection_name=COLLECTION_NAME,
        )
        del vectorstore

        print("Verifico che l'indice sia leggibile prima di copiarlo...")
        _wait_until_readable(staging_dir, embeddings, "scrittura")

        print(f"Copio l'indice completato in {CHROMA_DIR}...")
        if CHROMA_DIR.exists():
            _retry_fs_op(lambda: shutil.rmtree(CHROMA_DIR), "cancellazione vecchio indice")
        _retry_fs_op(lambda: shutil.copytree(staging_dir, CHROMA_DIR), "copia nuovo indice")

    # Seconda verifica, DOPO la copia: OneDrive tocca i file appena arrivano
    # in data/ (vedi docstring di _wait_until_readable) - senza questa seconda
    # verifica, lo script poteva terminare "con successo" lasciando pero' un
    # indice in data/chroma_db non ancora leggibile per qualche secondo.
    print("Verifico che l'indice copiato in data/ sia leggibile...")
    _wait_until_readable(str(CHROMA_DIR), embeddings, "copia in data/")

    print("Indice costruito con successo.")


if __name__ == "__main__":
    main()
