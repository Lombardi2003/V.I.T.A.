from pathlib import Path
from typing import List
from sqlmodel import Field, Session, SQLModel, create_engine
from sqlalchemy import Column, JSON
from sqlalchemy.exc import SQLAlchemyError

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Table class for the database, represents patient data
class PatientRecord(SQLModel, table=True):
    """Represents the patients table in the database. The tax ID (fiscal_code) is the primary key."""
    fiscal_code: str = Field(primary_key=True)  # Primary key, unique for each patient
    first_name: str = ""
    last_name: str = ""
    age: str = ""
    sex: str = ""
    allergies: List[str] = Field(default_factory=list, sa_column=Column(JSON))  # JSON to store lists in SQLite
    previous_conditions: List[str] = Field(default_factory=list, sa_column=Column(JSON))  # JSON to store lists in SQLite

# Class that handles all communication with the database
class MedicalDatabase:
    """Class that handles all communication with the database."""

    def __init__(self, db_name: str = "data/medical_database.db"):
        """On startup, creates the engine and generates the tables if they don't exist."""
        db_path = Path(db_name)
        if not db_path.is_absolute():
            db_path = _PROJECT_ROOT / db_path
        self.sqlite_url = f"sqlite:///{db_path}"

        try:
            self.engine = create_engine(self.sqlite_url, echo=False)
            # Table creation
            SQLModel.metadata.create_all(self.engine)
        except SQLAlchemyError as e:
            raise RuntimeError(
                f"Impossibile inizializzare il database in '{db_path}'. "
                "Controlla che il percorso sia valido, che tu abbia i permessi di scrittura "
                f"sulla cartella e che ci sia spazio su disco. Dettaglio tecnico: {e}"
            ) from e

        print(f"✅ Database connection ready, tables verified! ({db_path})")

    def upsert_patient(self, patient_card: dict) -> bool:
        """Saves the whole patient card: creates the patient if the fiscal code is
        new, otherwise updates every field (so corrections made during intake are
        kept). Returns True if the patient was created, False if updated."""
        fields = {
            "first_name": patient_card.get("first_name", ""),
            "last_name": patient_card.get("last_name", ""),
            "age": patient_card.get("age", ""),
            "sex": patient_card.get("sex", ""),
            # New lists (not the caller's): SQLAlchemy only stores a JSON column
            # again when the attribute is reassigned.
            "allergies": list(patient_card.get("allergies") or []),
            "previous_conditions": list(patient_card.get("previous_conditions") or []),
        }
        with Session(self.engine) as session:
            record = session.get(PatientRecord, patient_card["fiscal_code"])
            created = record is None
            if created:
                record = PatientRecord(fiscal_code=patient_card["fiscal_code"], **fields)
            else:
                for name, value in fields.items():
                    setattr(record, name, value)
            session.add(record)
            session.commit()
            print(f"💾 Patient {'created' if created else 'updated'}: {record.first_name} {record.last_name}")
        return created

    def read_patient(self, cf: str) -> PatientRecord | None:
        """Retrieves the patient from the database."""
        with Session(self.engine) as session:
            patient_record = session.get(PatientRecord, cf)
            return patient_record

    def verify_patient_exists(self, cf: str) -> bool:
        """Checks whether a patient exists in the database."""
        with Session(self.engine) as session:
            patient_record = session.get(PatientRecord, cf)
            return patient_record is not None
