"""Names shown in the chat; each must match an avatar file in public/avatars/."""


class Authors:
    """Chat author of each node."""
    SYSTEM = "System"
    INTAKE = "Anagrafica"
    REVIEWER = "Revisore"
    PHOTOGRAPHY = "Fotografia"
    SUPERVISOR = "Supervisore"
    PRIMARY_PHYSICIAN = "Primario"

    # Specialists: same names as SPECIALIST_DISPLAY_NAMES in roundtable.py.
    CARDIOLOGIST = "Cardiologia"
    NEUROLOGIST = "Neurologia"
    DERMATOLOGIST = "Dermatologia"
    ORTHOPEDIST = "Ortopedia"
    GASTROENTEROLOGIST = "Gastroenterologia"
    PULMONOLOGIST = "Pneumologia"
    ENT = "Otorinolaringoiatria"
    OPHTHALMOLOGIST = "Oftalmologia"
    UROLOGIST = "Urologia"
    GENERAL_PRACTITIONER = "Medicina"
