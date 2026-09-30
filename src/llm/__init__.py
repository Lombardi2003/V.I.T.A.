# Pacchetto per tutto cio' che riguarda i modelli LLM - l'unico posto del
# progetto che sa quale provider/modello c'e' sotto ("ecco il tuo LLM"):
#   models.py   - Models, l'elenco dei modelli disponibili per provider
#   factory.py  - quali modelli usa l'app (MODELLI ATTIVI) e get_llm(), che ne
#                 costruisce il client ChatOpenAI
#   calls.py    - come si usa un client: chiamata con nuovi tentativi e limiti
#                 di token, lettura del JSON dalla risposta
# settings.py resta fuori di proposito: legge la configurazione generale del
# progetto (chiavi, temperatura), quindi vive a livello src/.
from .models import Models
from .factory import build_llm, describe_llm, get_llm
from .calls import call_with_retry, extract_json, stream_text
