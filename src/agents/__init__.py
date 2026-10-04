# Pacchetto degli agenti/nodi del grafo, un file per agente. Non tutto qui
# dentro e' un "agente" in senso stretto (es. persistence.py e router.py sono
# logica deterministica, nessun LLM coinvolto) - il nome riprende comunque il
# "Multi-Agent" con cui il progetto si presenta, usando la definizione ampia di
# agente (percepisce, decide, agisce) e non quella ristretta "solo se usa un LLM".
#   common.py       - client LLM, connessione DB, utility condivise
#   prompts.py      - tutti i prompt
#   authors.py      - nomi mostrati in chat
#   persistence.py  - read_db, save_db (lettura/scrittura sul DB pazienti)
#   intake.py       - anagrafica
#   reviewer.py     - sintomi
#   photography.py  - foto
#   supervisor.py   - scelta degli specialisti
#   roundtable.py   - cio' che il tavolo ha in comune (nomi, limiti, trascrizione)
#   specialist.py   - turno di uno specialista e i 10 nodi specialistici
#   router.py       - chi parla al prossimo turno del tavolo
#   primary.py      - report di sintesi
#
# Questo file ri-esporta tutto cosi' il resto del progetto (in particolare
# graph.py) continua a fare `from src.agents import nome_nodo` con un unico import.
from .common import (
    stream_response,
    settings,
    llm,
    llm_vision,
    mdb,
    as_list,
    as_text,
    is_no,
    is_yes,
)
from .authors import Authors
from .persistence import (
    is_valid_fiscal_code,
    read_db_node,
    save_db_node,
)
from .intake import intake_node
from .reviewer import reviewer_node
from .photography import photography_node
from .supervisor import supervisor_node
from .roundtable import (
    MAX_TOTAL_TURNS,
    MAX_RECRUITED_SPECIALISTS,
    MAX_SPEAKS_PER_SPECIALIST,
    MAX_FAILED_TURNS,
)
from .specialist import (
    specialist_node,
    cardiologist_node,
    neurologist_node,
    orthopedic_node,
    gastroenterologist_node,
    dermatologist_node,
    pneumologist_node,
    ent_node,
    ophthalmologist_node,
    urologist_node,
    general_practitioner_node,
)
from .router import router
from .primary import primary_node
