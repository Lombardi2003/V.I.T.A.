"""Catalogo dei modelli conosciuti, organizzati per provenienza.

Fonte unica di verita' per i nomi dei modelli usati altrove nel progetto
(factory.py, script di test) - evita stringhe scritte a mano e
ripetute in piu' punti, con il rischio di un refuso in una sola di esse.
"""


class Models:
    class Groq:
        TEXT_8B = "llama-3.1-8b-instant"
        TEXT_70B = "llama-3.3-70b-versatile"
        VISION_MAVERICK = "meta-llama/llama-4-maverick-17b-128e-instruct"

    class Ollama:
        TEXT_LLAMA3 = "llama3"
        VISION_MOONDREAM = "moondream"
