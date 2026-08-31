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
        # Stesso modello di VISION_QWEN sotto (stesso valore, alias diverso):
        # qui usato per il testo (es. specialist_node), non per la visione -
        # e' un modello "thinking", antepone un blocco <think>...</think> al
        # JSON vero e proprio: chi lo usa deve ripulire la risposta prima di
        # fare json.loads (vedi photography_node/specialist_node).
        TEXT_QWEN_27B = "qwen/qwen3.6-27b"
        # meta-llama/llama-4-maverick-17b-128e-instruct: non piu' accessibile su
        # questo account (404 model_not_found, verificato con chiamata reale) -
        # qwen/qwen3.6-27b e' l'unico modello vision confermato raggiungibile.
        VISION_QWEN = "qwen/qwen3.6-27b"

    class Ollama:
        TEXT_LLAMA3 = "llama3"
        VISION_MOONDREAM = "moondream"
