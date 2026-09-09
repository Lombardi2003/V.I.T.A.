# Pacchetto degli agenti/nodi del grafo, diviso per responsabilita'. Non tutto
# qui dentro e' un "agente" in senso stretto (es. persistence.py e' logica
# deterministica, nessun LLM coinvolto) - il nome riprende comunque il "Multi-Agent"
# con cui il progetto si presenta, usando la definizione ampia di agente
# (percepisce, decide, agisce) e non quella ristretta "solo se usa un LLM".
#   common.py       - client LLM, connessione DB, utility condivise
#   persistence.py  - read_db, save_db, modify_db (lettura/scrittura sul DB pazienti)
#   intake.py       - user, intake, reviewer, photography (raccolta dati dal paziente)
#   clinical.py     - supervisor, specialisti, primario (valutazione clinica)
#
# Questo file ri-esporta tutto cosi' il resto del progetto (in particolare
# graph.py) continua a fare `from src.agents import nome_nodo` con un unico import.
from .common import (
    stream_response,
    settings,
    USE_CLOUD_ACCELERATION,
    llm_agents,
    llm_photography,
    mdb,
)
from .authors import Authors
from .persistence import (
    is_valid_fiscal_code,
    read_db_node,
    save_db_node,
    modify_db_node,
)
from .intake import (
    user_node,
    intake_node,
    reviewer_node,
    photography_node,
)
from .clinical import (
    MAX_TOTAL_TURNS,
    MAX_RECRUITED_SPECIALISTS,
    MAX_SPEAKS_PER_SPECIALIST,
    supervisor_node,
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
    primary_node,
)
