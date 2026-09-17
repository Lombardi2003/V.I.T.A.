# Script da eseguire UNA TANTUM (non fa parte del flusso dell'app): legge i PDF
# di linee guida cliniche in data/guidelines/, li spezzetta, li trasforma in
# vettori con un modello di embedding LOCALE (nessuna quota/costo esterno - vedi
# src/agents/common.py per lo storico dei problemi di quota con Gemini/Groq) e
# li salva in un indice Chroma persistente su disco (data/chroma_db/), usato poi
# da src/rag/retriever.py durante il tavolo rotondo.
#
# Uso: python -m src.rag.build_index
import shutil
import tempfile
import time
from pathlib import Path

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
    for pdf_path in pdf_paths:
        pages = PyPDFLoader(str(pdf_path)).load()
        doc_chunks = splitter.split_documents(pages)
        # "passage: " obbligatorio per multilingual-e5-small su ogni testo che
        # finisce nell'indice (a differenza delle query, che lo ricevono in
        # retriever.py al momento della ricerca, non qui in fase di indicizzazione).
        for chunk in doc_chunks:
            chunk.page_content = "passage: " + chunk.page_content
            chunk.metadata["source_file"] = pdf_path.name
        chunks.extend(doc_chunks)
        print(f"  {pdf_path.name}: {len(pages)} pagine -> {len(doc_chunks)} pezzi")

    print(f"\nTotale: {len(chunks)} pezzi da {len(pdf_paths)} documenti")
    print(f"Carico il modello di embedding ({EMBEDDING_MODEL_NAME})...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)

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
