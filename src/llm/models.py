"""Catalogo dei modelli conosciuti, organizzati per provenienza.

Fonte unica di verita' per i nomi dei modelli usati altrove nel progetto
(factory.py, script di test) - evita stringhe scritte a mano e
ripetute in piu' punti, con il rischio di un refuso in una sola di esse.
"""


class Models:
    class Groq:
        TEXT_8B = "llama-3.1-8b-instant"
        TEXT_70B = "llama-3.3-70b-versatile"
        # meta-llama/llama-4-maverick-17b-128e-instruct: non piu' accessibile su
        # questo account (404 model_not_found, verificato con chiamata reale) -
        # qwen/qwen3.6-27b e' l'unico modello vision confermato raggiungibile.
        VISION_QWEN = "qwen/qwen3.6-27b"

    class Ollama:
        TEXT_LLAMA3 = "llama3"
        VISION_MOONDREAM = "moondream"
