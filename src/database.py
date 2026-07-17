from pathlib import Path
from typing import List
from sqlmodel import Field, Session, SQLModel, create_engine
from sqlalchemy import Column, JSON
from src.state import PatientCard

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

    def __init__(self, db_name: str = "medical_database.db"):
        """On startup, creates the engine and generates the tables if they don't exist."""
        db_path = Path(db_name)
        if not db_path.is_absolute():
            db_path = _PROJECT_ROOT / db_path
        self.sqlite_url = f"sqlite:///{db_path}"
        self.engine = create_engine(self.sqlite_url, echo=False)

        # Table creation
        SQLModel.metadata.create_all(self.engine)
        print("✅ Database connection ready, tables verified!")

    def save_patient(self, patient_card):
        """Saves the extracted data to the database."""

        # We use .get() everywhere. If a field is missing, we set an empty string "" or an empty list []
        new_record = PatientRecord(
            fiscal_code=patient_card.get("fiscal_code", "TO_BE_REQUESTED"),
            first_name=patient_card.get("first_name", ""),
            last_name=patient_card.get("last_name", ""),
            age=patient_card.get("age", ""),
            # This is the magic line that fixes the error: if missing, sets an empty list []
            previous_conditions=patient_card.get("previous_conditions", [])
        )

        with Session(self.engine) as session:
            session.add(new_record)
            session.commit()
            print(f"💾 Save completed for: {new_record.first_name} {new_record.last_name}")

    def update_patient_conditions(self, patient: PatientCard, new_condition: str):
        """Updates the condition history of an existing patient."""
        with Session(self.engine) as session:
            patient_record = session.get(PatientRecord, patient["fiscal_code"])

            if not patient_record:
                print(f"❌ No patient found with tax ID: {patient['fiscal_code']}")
                return

            # Copy the list, append the new item, and reassign it
            updated_list = patient_record.previous_conditions.copy()
            updated_list.append(new_condition)
            patient_record.previous_conditions = updated_list

            session.add(patient_record)
            session.commit()
            print(f"✅ Condition '{new_condition}' successfully added to {patient_record.first_name}")

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
