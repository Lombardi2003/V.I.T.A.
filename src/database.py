from typing import List
from sqlmodel import Field, Session, SQLModel, create_engine
from sqlalchemy import Column, JSON
from src.state import PatientCard

# Classe Tabella per il database, rappresenta i dati del paziente
class PatientRecord(SQLModel, table=True):
    """Rappresenta la tabella dei pazienti nel database. Il codice fiscale è la chiave primaria."""
    codice_fiscale: str = Field(primary_key=True)  # Chiave primaria, unica per ogni paziente
    nome: str = ""
    cognome: str = ""
    eta: str = ""
    patologie_precedenti: List[str] = Field(default_factory=list, sa_column=Column(JSON)) # JSON per memorizzare liste in SQLite

# Classe che gestisce tutte le comunicazioni con il database
class MedicalDatabase:
    """Classe che gestisce tutte le comunicazioni con il database."""
    
    def __init__(self, db_name: str = "medical_database.db"):
        """All'avvio, crea l'engine e genera le tabelle se non esistono."""
        self.sqlite_url = f"sqlite:///{db_name}"
        self.engine = create_engine(self.sqlite_url, echo=False)
        
        # Creazione delle tabelle
        SQLModel.metadata.create_all(self.engine)
        print("✅ Connessione al Database pronta e tabelle verificate!")

    def save_patient(self, patient_card):
        """Salva i dati estratti nel database."""
        
        # Usiamo .get() ovunque. Se un campo manca, mettiamo una stringa vuota "" o una lista vuota []
        nuovo_record = PatientRecord(
            codice_fiscale=patient_card.get("codice_fiscale", "DA_RICHIEDERE"),
            nome=patient_card.get("nome", ""),
            cognome=patient_card.get("cognome", ""),
            eta=patient_card.get("eta", ""),
            # Ecco la riga magica che risolve l'errore: se non c'è, mette una lista vuota []
            patologie_precedenti=patient_card.get("patologie_precedenti", []) 
        )
        
        with Session(self.engine) as session:
            session.add(nuovo_record)
            session.commit()
            print(f"💾 Salvataggio completato per: {nuovo_record.nome} {nuovo_record.cognome}")

    def modify_patology_patient(self, patient: PatientCard, nuova_patologia: str):
        """Aggiorna la lista delle patologie di un paziente esistente."""
        with Session(self.engine) as session:
            paziente = session.get(PatientRecord, patient["codice_fiscale"])
            
            if not paziente:
                print(f"❌ Nessun paziente trovato con CF: {patient['codice_fiscale']}")
                return
                
            # Creiamo una copia della lista, aggiungiamo il dato e riassegniamo
            lista_aggiornata = paziente.patologie_precedenti.copy()
            lista_aggiornata.append(nuova_patologia)
            paziente.patologie_precedenti = lista_aggiornata
            
            session.add(paziente)
            session.commit()
            print(f"✅ Patologia '{nuova_patologia}' aggiunta con successo a {paziente.nome}")

    def read_patient(self, cf: str) -> PatientRecord | None:
        """Estrae il paziente dal database."""
        with Session(self.engine) as session:
            paziente = session.get(PatientRecord, cf)
            return paziente
    
    def verify_patient_exists(self, cf: str) -> bool:
        """Verifica se un paziente esiste nel database."""
        with Session(self.engine) as session:
            paziente = session.get(PatientRecord, cf)
            return paziente is not None