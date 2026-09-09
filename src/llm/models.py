"""Catalogo dei modelli conosciuti, organizzati per provenienza.

Fonte unica di verita' per i nomi dei modelli usati altrove nel progetto
(factory.py, script di test) - evita stringhe scritte a mano e
ripetute in piu' punti, con il rischio di un refuso in una sola di esse.
"""


class Models:
    class Groq:
        TEXT_8B = "llama-3.1-8b-instant"
        TEXT_70B = "llama-3.3-70b-versatile"
        # Piu' grande dei due sopra (120B, OpenAI open-weight) - verificato
        # disponibile su questo account con una chiamata reale ai modelli Groq.
        TEXT_120B = "openai/gpt-oss-120b"
        # Stessa famiglia di TEXT_120B, piu' piccolo - stesso limite TPM (8K)
        # del 120B ma risposte piu' corte, usato per contenere il consumo di
        # token nella discussione al tavolo (vedi llm_specialist in common.py).
        TEXT_20B = "openai/gpt-oss-20b"
        # Stesso modello di VISION_QWEN sotto (stesso valore, alias diverso):
        # qui usato per il testo (es. specialist_node), non per la visione -
        # e' un modello "thinking", antepone un blocco <think>...</think> al
        # JSON vero e proprio: chi lo usa deve ripulire la risposta prima di
        # fare json.loads (vedi photography_node/specialist_node).
        TEXT_QWEN_27B = "qwen/qwen3.8-27b"
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
        TEXT_LLAMA3 = "llama3:latest"
        VISION_MOONDREAM = "moondream"

    class Gemini:
        # Google AI Studio (piano gratuito). gemini-2.5-flash (la prima scelta,
        # sembrava la piu' stabile dall'elenco restituito da GET
        # /v1beta/openai/models) e' risultato NON PIU' DISPONIBILE per nuovi
        # utenti (404 model_not_found, verificato con una chiamata reale) -
        # Google indica esplicitamente gemini-3.6-flash come sostituto nello
        # stesso messaggio di errore. E' un modello "thinking" (ragionamento
        # interno via "thought_signature", non testo <think> visibile nel
        # contenuto come qwen - non serve pulizia lato Python, verificato con
        # una chiamata reale).
        TEXT_FLASH = "gemini-3.6-flash"
