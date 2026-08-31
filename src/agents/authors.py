# Registro dei nomi mostrati in chat per ciascun nodo. Chainlit associa in
# automatico l'avatar corrispondente in public/avatars/{nome}.* (case-insensitive),
# in base al nome esatto passato come author= a cl.Message - basta aggiungere
# la voce qui e il file .svg per dare un profilo a un nuovo nodo.
#
# cl.Step NON legge public/avatars/: /avatars/{nome step} e' generato in
# automatico lato server da Chainlit e ignora i file qui, anche se il nome
# combacia (verificato scaricando il contenuto reale, non fidandosi dell'URL).
# L'icona per gli Step e' quindi iniettata via CSS in public/style.css
# (nascosta l'icona nativa sbagliata, mostrato al suo posto il file vero da
# /public/avatars/{nome}.svg, agganciato sull'alt="Avatar for {nome step}").


class Authors:
    SYSTEM = "System"
    INTAKE = "Anagrafica"
    REVIEWER = "Revisore"
    PHOTOGRAPHY = "Fotografia"
    SUPERVISOR = "Supervisore"
    PRIMARY_PHYSICIAN = "Primario"

    # Specialisti (le chiavi in inglese sono i ruoli usati nel grafo/ALL_SPECIALISTS,
    # questi sono i nomi mostrati in chat - vedi SPECIALIST_DISPLAY_NAMES in clinical.py
    # per la mappa ruolo->nome, tenuta in sync a mano con questi valori).
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
