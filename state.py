import operator
from typing import Annotated, List, TypedDict
from langchain_core.messages import BaseMessage

# Classe TypedDict per la cartella clinica del paziente
class PatientCard(TypedDict):
    """ Cartella clinica del paziente. """
    nome: str
    eta: str
    sintomo_principale: str
    intensita: str
    durata: str

# Classe TypedDict che rappresenta lo stato minimale del grafo, cioè le informazioni essenziali che devono essere mantenute tra i nodi
class MedicalState(TypedDict):
    """ Stato minimale del grafo. """
    general_history: Annotated[list[BaseMessage], operator.add] # CRONOLOGIA GENERALE: Qui finiscono tutti i messaggi generati durante la consultazione
    triage_history: Annotated[list[BaseMessage], operator.add]  # CRONOLOGIA TRIAGE: Qui finiscono tutti i messaggi relativi al triage iniziale
    patient_card: PatientCard                                   # CARTELLA CLINICA: i dati strutturati del paziente
    triage_complete: bool                                       # FLAG DI COMPLETAMENTO TRIAGE: indica se il triage è completo       
    diagnosis: str                                              # DIAGNOSI FINALE: il testo della diagnosi finale generata dal primario   
    next_step: str                                              # PROSSIMO PASSO: indica quale specialista deve intervenire o se finire il processo

    def __init__(self):
        self.triage_complete = False
        self.diagnosis = ""
        self.next_step = ""
        self.general_history = list()
        self.triage_history = list()
        self.patient_card = {
            "nome": "",
            "eta": "",
            "sintomo_principale": "",
            "intensita": "",
            "durata": ""
        }