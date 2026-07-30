# Nodi che leggono o scrivono sul database dei pazienti: read_db (lettura in
# ingresso), save_db/modify_db (scrittura in uscita, a fine triage).
import re

from langchain_core.messages import AIMessage
import chainlit as cl

from src.state import MedicalState
from .common import mdb
from .authors import Authors


def is_valid_fiscal_code(raw: str) -> bool:
    """Validazione minima del Codice Fiscale: 16 alfanumerici, con bypass di test '1234'."""
    return bool(re.fullmatch(r'[A-Z0-9]{16}', raw)) or raw == "1234"


# Nodo per la lettura del database
async def read_db_node(state: MedicalState):
    """Legge il CF, lo valida minimamente e interroga il DB.

    Se il CF non e' valido, il grafo torna qui (vedi l'arco condizionale da
    "user" in graph.py) finche' non ne arriva uno valido - la validazione del
    CF resta quindi interamente di competenza di questo nodo. Un errore di
    connessione al DB invece non fa ciclare (riprovare lo stesso CF non
    risolverebbe un problema del database) e procede con una nuova scheda.
    """

    # 1. Estrazione input
    try:
        raw = state.general_history[-1].content.strip().upper()
    except (IndexError, AttributeError):
        msg = "Inserire il proprio Codice Fiscale per procedere."
        await cl.Message(content=msg, author=Authors.SYSTEM).send()
        return {"next_step": "read_db", "general_history": [AIMessage(content=msg)]}

    # 2. Validazione minima: 16 caratteri alfanumerici
    if not is_valid_fiscal_code(raw):
        msg = (
            "Il valore inserito non costituisce un Codice Fiscale valido.\n"
            "Deve essere composto da 16 caratteri alfanumerici. Si prega di reinserirlo."
        )
        await cl.Message(content=msg, author=Authors.SYSTEM).send()
        return {
            "next_step": "read_db",  # torna qui finche' non arriva un CF valido
            "general_history": [AIMessage(content=msg)],
        }

    # 3. Query DB (un'unica interrogazione: read_patient restituisce None se non trovato)
    # La ricerca in se' e' un passaggio interno: la mostriamo come Step collassato
    # ("sto pensando..."), non come messaggio di chat - il risultato utile per il
    # paziente arriva subito dopo, come messaggio vero.
    record = None
    db_error = None
    async with cl.Step(name="Ricerca Codice Fiscale", type="tool", default_open=False, show_input="text") as step:
        step.input = raw
        try:
            record = mdb.read_patient(raw)
            step.output = (
                f"Paziente trovato: {record.first_name} {record.last_name}"
                if record else
                "Nessun paziente trovato con questo codice fiscale"
            )
        except Exception as e:
            db_error = e
            step.output = f"Errore di connessione al database: {e}"

    if db_error:
        msg = "Si è verificato un errore di connessione al database. La procedura prosegue con la creazione di una nuova scheda."
        await cl.Message(content=msg, author=Authors.SYSTEM).send()
        print(f"READ_DB | Errore DB: {db_error}")
        return {
            "next_step":       "intake",  # user → intake (raccolta anagrafica)
            "general_history": [AIMessage(content=msg)],
        }

    if record:
        msg = f"Scheda clinica recuperata per **{record.first_name} {record.last_name}**."
        await cl.Message(content=msg, author=Authors.SYSTEM).send()
        print(f"READ_DB | Paziente trovato: {raw}")
        loaded_allergies = getattr(record, "allergies", [])
        loaded_conditions = record.previous_conditions
        return {
            "patient_card": {
                "fiscal_code":         raw,
                "first_name":          record.first_name,
                "last_name":           record.last_name,
                "age":                 record.age,
                "sex":                 getattr(record, "sex", ""),
                "allergies":           loaded_allergies,
                "previous_conditions": loaded_conditions,
            },
            "patient_exists": True,
            # Un paziente di ritorno con allergie/patologie gia' registrate non
            # deve doverle riconfermare da zero - intake_node puo' comunque
            # aggiornarle se ne vengono menzionate di nuove. Se la lista e'
            # vuota restano non affrontate (non possiamo distinguere "nessuna
            # allergia confermata" da "non ancora chiesto"), quindi si richiede.
            "allergies_addressed":            bool(loaded_allergies),
            "previous_conditions_addressed":  bool(loaded_conditions),
            "next_step":      "intake",  # user → intake (raccolta/riconferma anagrafica)
            "general_history": [AIMessage(content=msg)],
        }

    msg = (
        "Codice Fiscale non presente nel sistema: verrà creata una nuova scheda clinica.\n\n"
        "Si prega di fornire i seguenti dati anagrafici: nome, cognome, età, sesso, "
        "allergie e patologie pregresse."
    )
    await cl.Message(content=msg, author=Authors.SYSTEM).send()
    print(f"READ_DB | Nuovo paziente: {raw}")
    return {
        "patient_card":    {"fiscal_code": raw},
        "patient_exists":  False,
        "next_step":       "intake",  # user → intake (raccolta anagrafica)
        "general_history": [AIMessage(content=msg)],
    }


# Nodo per il salvataggio nel database
async def save_db_node(state: MedicalState):
    """ Salva o aggiorna i dati del paziente nel database. """
    print("💾 SAVE_DB: Avvio salvataggio...")

    card = state.get("patient_card", {})

    # 1. Controllo di sicurezza sul codice fiscale (Ottimo che tu lo abbia già messo!)
    if "fiscal_code" not in card or not card["fiscal_code"]:
        print("❌ SAVE_DB: Codice fiscale mancante, impossibile salvare.")
        return {}

    # 2. IL FIX: Assicuriamoci che 'previous_conditions' esista e sia una vera Lista!
    if "previous_conditions" not in card or not isinstance(card["previous_conditions"], list):
        card["previous_conditions"] = []

    # 3. Estrazione sicura della diagnosi
    diagnosi_obj = state.get("report")
    testo_diagnosi = diagnosi_obj["final_diagnosis"] if diagnosi_obj else "Nessuna diagnosi specifica"

    # 4. Ora possiamo fare l'append in totale sicurezza
    card["previous_conditions"].append(testo_diagnosi)

    # 5. Invio al database
    mdb.save_patient(card)
    print("✅ SAVE_DB: Dati salvati con successo.")
    await cl.Message(content=f"✅ I tuoi dati sono stati salvati con la diagnosi: {testo_diagnosi}").send()

    # Restituiamo la card aggiornata allo stato del grafo
    return {"patient_card": card}


# Nodo per modificare un paziente esistente nel database
async def modify_db_node(state: MedicalState):
    """ Modifica i dati di un paziente esistente nel database. """
    print("🔄 MODIFY_DB: Avvio modifica dati...")

    card = state.get("patient_card", {})

    if "fiscal_code" not in card or not card["fiscal_code"]:
        print("❌ MODIFY_DB: Codice fiscale mancante, impossibile modificare.")
        return {}

    nuova_patologia = state.get("report", {}).get("final_diagnosis", "Nessuna diagnosi specifica")

    mdb.update_patient_conditions(card, nuova_patologia)
    print("✅ MODIFY_DB: Dati modificati con successo.")
    await cl.Message(content=f"✅ I tuoi dati sono stati aggiornati con la nuova diagnosi: {nuova_patologia}").send()
    return {"patient_card": card}
