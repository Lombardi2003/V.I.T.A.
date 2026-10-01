"""Catalogo dei modelli disponibili, organizzati per provenienza (provider).

Fonte unica di verita' per i nomi dei modelli usati nel progetto - evita
stringhe scritte a mano e ripetute in piu' punti, con il rischio di un refuso
in una sola di esse. La classe in cui sta un nome indica il suo provider
(Models.Groq.* -> Groq, Models.Ollama.* -> Ollama, ...): factory.py lo ricava
da qui, senza bisogno di scriverlo altrove. Per usare un modello nuovo basta
aggiungerne il nome sotto il suo provider e sceglierlo in cima a factory.py.
"""


class Models:
    class Groq:
        # TEXT_8B/TEXT_70B: non piu' nel catalogo modelli dell'account
        # (verificato dalla pagina dei rate limit Groq), lasciati come storico.
        TEXT_8B = "llama-3.1-8b-instant"
        TEXT_70B = "llama-3.3-70b-versatile"
        # 120B, OpenAI open-weight, modello di ragionamento - verificato
        # disponibile su questo account con una chiamata reale ai modelli Groq.
        TEXT_120B = "openai/gpt-oss-120b"
        # Stessa famiglia di TEXT_120B, piu' piccolo, stesso limite (8K token/min).
        TEXT_20B = "openai/gpt-oss-20b"
        # Lo stesso modello di VISION_QWEN, usato per il testo: e' un modello
        # "thinking", antepone un blocco <think>...</think> al JSON (gestito da
        # extract_json in calls.py).
        TEXT_QWEN_27B = "qwen/qwen3.6-27b"
        # Sistema "agentic" di Groq (non un modello di testo "nudo"): puo'
        # decidere da solo di usare strumenti esterni (es. ricerca web).
        # PROVATO E SCARTATO come soluzione al limite di token/minuto: i 70K
        # TPM dichiarati (contro 8K dei modelli sopra) sono un limite del
        # sistema "compound" stesso, non del modello che genera davvero la
        # risposta sotto - un errore reale ha mostrato che compound-mini si
        # appoggia a TEXT_120B per la generazione, quindi consuma lo stesso
        # budget da 8K TPM. Nessun vantaggio, solo il rischio in piu' del
        # comportamento agentic - lasciato qui solo come nota per non
        # riprovarlo in futuro pensando che risolva il problema.
        TEXT_COMPOUND_MINI = "groq/compound-mini"
        # meta-llama/llama-4-maverick-17b-128e-instruct: non piu' accessibile su
        # questo account (404 model_not_found, verificato con chiamata reale) -
        # qwen/qwen3.6-27b e' l'unico modello vision confermato raggiungibile.
        VISION_QWEN = "qwen/qwen3.6-27b"

    class Ollama:
        # In locale, nessun limite al minuto. NB: Ollama usa di default un
        # contesto piccolo (4096 token nelle versioni recenti, 2048 nelle
        # precedenti) e taglia in silenzio il resto del prompt - il prompt
        # degli specialisti supera i 4000 token: avviare Ollama con la
        # variabile d'ambiente OLLAMA_CONTEXT_LENGTH (es. 8192).
        TEXT_LLAMA3 = "llama3:latest"
        VISION_MOONDREAM = "moondream"

    class Gemini:
        # Google AI Studio (piano gratuito, limite di 20 richieste/GIORNO).
        # gemini-2.5-flash (la prima scelta) e' risultato NON PIU' DISPONIBILE
        # per nuovi utenti (404 model_not_found, verificato con una chiamata
        # reale) - Google indica esplicitamente gemini-3.6-flash come sostituto
        # nello stesso messaggio di errore. E' un modello "thinking" e
        # nativamente multimodale: va bene anche per la foto.
        TEXT_FLASH = "gemini-3.8-flash"
