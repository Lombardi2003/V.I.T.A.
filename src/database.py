"""The patient table and the object that reads and writes it."""

from pathlib import Path
from typing import List
from sqlmodel import Field, Session, SQLModel, create_engine
from sqlalchemy import Column, JSON
from sqlalchemy.exc import SQLAlchemyError
from src.log import get_logger

log = get_logger("database")

# Relative database paths are resolved from here, whatever the working directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class PatientRecord(SQLModel, table=True):
    """One patient: the personal data saved at the end of a triage."""
    fiscal_code: str = Field(primary_key=True)  # Primary key.
    first_name: str = ""
    last_name: str = ""
    age: str = ""
    sex: str = ""
    allergies: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    previous_conditions: List[str] = Field(default_factory=list, sa_column=Column(JSON))


class MedicalDatabase:
    """Access to the SQLite patient database."""
    def __init__(self, db_name: str = "data/medical_database.db"):
        """Opens the database and creates the table if it does not exist."""
        db_path = Path(db_name)
        if not db_path.is_absolute():
            db_path = _PROJECT_ROOT / db_path
        self.sqlite_url = f"sqlite:///{db_path}"

        try:
            self.engine = create_engine(self.sqlite_url, echo=False)
            SQLModel.metadata.create_all(self.engine)
        except SQLAlchemyError as e:
            raise RuntimeError(
                f"Cannot initialise the database in '{db_path}'. "
                "Check that the path is valid, that you can write to the folder "
                f"and that there is free disk space. Technical detail: {e}"
            ) from e

        log.info("database ready: %s", db_path)

    def upsert_patient(self, patient_card: dict) -> bool:
        """Saves the whole card, creating or updating the patient; True if created."""
        fields = {
            "first_name": patient_card.get("first_name", ""),
            "last_name": patient_card.get("last_name", ""),
            "age": patient_card.get("age", ""),
            "sex": patient_card.get("sex", ""),
            # New list objects: a JSON column is stored again only when reassigned.
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
            log.debug("patient %s: %s %s", "created" if created else "updated", record.first_name, record.last_name)
        return created

    def read_patient(self, cf: str) -> PatientRecord | None:
        """The patient with this fiscal code, or None."""
        with Session(self.engine) as session:
            patient_record = session.get(PatientRecord, cf)
            return patient_record

    def verify_patient_exists(self, cf: str) -> bool:
        """True if a patient with this fiscal code is stored."""
        with Session(self.engine) as session:
            patient_record = session.get(PatientRecord, cf)
            return patient_record is not None
