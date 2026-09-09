# Script diagnostico (NON un test automatico con assert): verifica se il
# meccanismo di CORREZIONE funziona - uno specialista che si trova davanti
# un'ipotesi di gruppo chiaramente SBAGLIATA nel proprio ambito la corregge
# davvero con "rivedi", invece di limitarsi a confermarla o ad aggiungere
# dettagli in coda (vedi la nuova regola "PRIORITA' (ipotesi scartata nel TUO
# ambito)" in SPECIALIST_PROMPT).
#
# A differenza di test_round_table.py/test_mini_consulto.py (che lasciano
# aprire la discussione a un vero specialista), qui INIETTIAMO NOI un primo
# intervento deliberatamente sbagliato - non aspettiamo che l'LLM sbagli da
# solo (osservato in test reale: con questo modello non succede quasi mai,
# ragiona troppo bene fin dal primo turno). Iniettiamo un'ipotesi di "colica
# renale" con urgenza VERDE per un quadro che e' in realta' da manuale di
# colecistite acuta (dolore che peggiora con cibi grassi) - la spiegazione
# scartata ricade proprio nell'ambito del secondo specialista
# (gastroenterologist), il caso pensato apposta per far scattare la nuova
# regola di difesa del proprio ambito. router/specialist_node/primary_node
# restano codice di produzione reale, con vere chiamate all'LLM per il turno
# di correzione.
#
# Uso: python -m tests.test_correction
import asyncio
import uuid

from chainlit.context import init_http_context

from src.graph import generate_graph
from src.state import (
    MedicalState, PatientCard, SymptomProfile, Symptom,
    GroupHypothesis, RoundTableEntry,
)

ALL_SPECIALIST_NODES = (
    "cardiologist", "neurologist", "orthopedist", "gastroenterologist",
    "dermatologist", "pulmonologist", "ent", "ophthalmologist",
    "urologist", "general_practitioner",
)


async def main():
    init_http_context()

    app = generate_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Stesso caso "colica biliare vs renale" gia' provato dal vivo in chat -
    # li' sia gastroenterologist che urologist avevano ragionato bene da soli.
    # Qui forziamo la mano: iniettiamo un'ipotesi INIZIALE deliberatamente
    # sbagliata (colica renale, urgenza verde, colecistite scartata) come se
    # fosse gia' stato urologist a proporla per primo.
    card = PatientCard(
        first_name="Elena",
        last_name="Ferrari",
        age="45",
        sex="femminile",
        symptom=SymptomProfile(symptoms=[
            Symptom(description="dolore al fianco destro tipo colica", intensity="forte", duration="6 ore",
                    trigger="peggiora dopo aver mangiato cibi grassi"),
            Symptom(description="nausea", intensity="moderata", duration="6 ore"),
        ]),
    )

    initial_state = MedicalState(patient_card=card)
    app.update_state(config, initial_state.model_dump())

    fake_hypothesis = GroupHypothesis(
        diagnosis="Colica renale (verosimile calcolo ureterale destro)",
        urgency_level="VERDE",
        recommended_exams=["Antidolorifico al bisogno", "Idratazione abbondante", "Controllo ambulatoriale tra una settimana se il dolore persiste"],
        details="Dolore al fianco destro di tipo colico: quadro compatibile con colica renale da calcolo ureterale. Non richiede accertamenti urgenti.",
        discarded_alternative="Colecistite acuta",
        discard_reason="Il dolore e' colico e localizzato al fianco, non tipico di colecistite.",
        last_updated_by="urologist",
        confirmed_by=["urologist"],
    )
    fake_entry = RoundTableEntry(
        author="urologist",
        to=None,
        azione="proponi",
        content="Propongo colica renale da calcolo ureterale destro, gestione ambulatoriale con antidolorifico, urgenza verde.",
    )

    # Iniettiamo lo stato COME SE urologist avesse gia' parlato per primo -
    # needed_specialists = entrambi seduti, urologist gia' confermato (la
    # propria ipotesi), gastroenterologist ancora in attesa: il router lo
    # chiamera' per primo.
    app.update_state(
        config,
        {
            "needed_specialists": {"urologist": True, "gastroenterologist": True},
            "round_table": [fake_entry],
            "group_hypothesis": fake_hypothesis.model_dump(),
            "total_turns": 1,
        },
        as_node="supervisor",
    )

    print("=" * 70)
    print("Ipotesi INIETTATA (deliberatamente sbagliata): colica renale, urgenza VERDE")
    print("Verifica se gastroenterologist la corregge davvero con 'rivedi'")
    print("=" * 70)

    async for event in app.astream_events(None, config=config, version="v2"):
        kind = event["event"]
        node_name = event.get("metadata", {}).get("langgraph_node", "")

        if kind == "on_chain_error":
            print(f"\nERRORE in {node_name}: {event.get('data', {}).get('error')}")

        if kind == "on_chain_end" and node_name in (*ALL_SPECIALIST_NODES, "router", "chief_physician"):
            output = event.get("data", {}).get("output")
            if isinstance(output, dict) and output:
                print(f"\n--- {node_name} ha aggiornato: {list(output.keys())} ---")

    final_state = app.get_state(config).values
    print("\n" + "=" * 70)
    print("STATO FINALE")
    print("=" * 70)

    print(f"\nround_table ({len(final_state.get('round_table', []))} interventi):")
    for entry in final_state.get("round_table", []):
        autore = entry.author if hasattr(entry, "author") else entry.get("author")
        destinatario = entry.to if hasattr(entry, "to") else entry.get("to")
        azione = entry.azione if hasattr(entry, "azione") else entry.get("azione")
        contenuto = entry.content if hasattr(entry, "content") else entry.get("content")
        tag = f" [{azione}]" if azione else ""
        print(f"  [{autore} -> {destinatario or 'tutti'}]{tag} {contenuto}")

    gh = final_state.get("group_hypothesis")
    print(f"\ngroup_hypothesis finale: {gh}")
    print(f"\nfinal_diagnosis: {final_state.get('final_diagnosis')}")

    diagnosi_finale = (gh.get("diagnosis") if isinstance(gh, dict) else getattr(gh, "diagnosis", "")) or ""
    corretto = "renale" not in diagnosi_finale.lower() and "ureterale" not in diagnosi_finale.lower()
    print("\n" + "=" * 70)
    if corretto:
        print("✅ CORREZIONE avvenuta: l'ipotesi di gruppo finale non e' piu' 'colica renale'.")
    else:
        print("⚠️ CORREZIONE NON avvenuta: l'ipotesi di gruppo finale e' rimasta 'colica renale'.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
