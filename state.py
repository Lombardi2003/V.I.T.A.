import operator
from typing import Annotated, List, TypedDict
from langchain_core.messages import BaseMessage


# Il TypedDict che rappresenta lo stato minimale del grafo, cioè le informazioni essenziali che devono essere mantenute tra i nodi
class MedicalState(TypedDict):
    """ Stato minimale del grafo. """
    
    # CRONOLOGIA: Qui finiscono tutti i messaggi (Utente, Cardiologo, Neurologo, ecc...).
    general_history: Annotated[list[BaseMessage], operator.add]    # operator.add serve ad aggiungere i nuovi messaggi alla lista esistente invece di sovrascriverli ogni volta

    # CARTELA CLINICA: i dati raccolti attraverso i dati dell'utente
    triage_history: Annotated[list[BaseMessage], operator.add]

    # DIAGNOSI FINALE: la diagnosi finale fornita dal sistema
    diagnosis: str

    # PROSSIMO STEP: il prossimo step deciso dal supervisore ("cardiologo", "neurologo", "FINISH")
    next_step: str