# Pacchetto per tutto cio' che riguarda la scelta/costruzione dei client LLM:
#   factory.py  - get_llm(), costruisce il client ChatOpenAI per il provider attivo
#   models.py   - Models, il catalogo dei nomi di modello conosciuti per provider
# settings.py resta fuori di proposito: legge la configurazione generale del
# progetto (non solo quella LLM), quindi vive a livello src/.
from .factory import get_llm
from .models import Models
