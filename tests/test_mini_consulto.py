# Script diagnostico (NON un test automatico con assert - il contenuto della
# discussione lo scrive l'LLM in linguaggio libero, non e' verificabile con
# un confronto esatto): verifica dal vivo se il meccanismo di MINI-CONSULTO
# funziona - uno specialista al tavolo chiama in causa un collega che il
# supervisore NON aveva selezionato (azione "consulta", vedi specialist_node
# in clinical.py e router in graph.py).
#
# Aggira solo la selezione del supervisore (come test_round_table.py), qui
# pre-selezionando di proposito UN SOLO specialista (cardiologist) su un caso
# che coinvolge anche un sintomo (formicolio al braccio) esplicitamente di
# competenza di un altro specialista (neurologist) rimasto FUORI dal tavolo -
# la stessa identica situazione gia' osservata in chat (vedi ARCHITECTURE.md/
# conversazione: qui il supervisore avrebbe normalmente incluso anche
# neurologist, lo escludiamo apposta per vedere se cardiologist lo chiama in
# causa da solo con un mini-consulto invece di lasciar perdere il dubbio.
# router/specialist_node/primary_node restano codice di produzione reale, con
# vere chiamate all'LLM.
#
# Uso: python -m tests.test_mini_consulto
import asyncio
import uuid

# NB: "import chainlit.context" seguito da chainlit.context.init_http_context()
# NON funziona - chainlit/__init__.py fa "from chainlit.context import context",
# che sovrascrive l'attributo chainlit.context (sul pacchetto) con il proxy
# invece del sottomodulo (verificato: causa ChainlitContextException gia' qui).
# Importare la funzione per nome bypassa il problema.
from chainlit.context import init_http_context

from src.graph import generate_graph
from src.state import MedicalState, PatientCard, SymptomProfile, Symptom

ALL_SPECIALIST_NODES = (
    "cardiologist", "neurologist", "orthopedist", "gastroenterologist",
    "dermatologist", "pulmonologist", "ent", "ophthalmologist",
    "urologist", "general_practitioner",
)


async def main():
    # specialist_node/primary_node/ecc. chiamano cl.Step/cl.Message, che richiedono
    # un contesto Chainlit attivo (altrimenti ChainlitContextException). Fuori da un
    # vero server Chainlit usiamo init_http_context(), pensato apposta per questo -
    # l'emitter che genera (BaseChainlitEmitter) e' documentato nel sorgente di
    # chainlit come "stub per scopi di test": i metodi send_* non fanno nulla,
    # quindi i nodi girano con la logica vera ma senza tentare di scrivere su un
    # websocket inesistente.
    init_http_context()

    app = generate_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Terzo tentativo di caso, dopo due precedenti (dolore toracico+formicolio,
    # poi vertigini posizionali) in cui il mini-consulto non e' mai scattato:
    # il modello si sentiva sempre abbastanza sicuro da cavarsela da solo,
    # anche quando "arricchirebbe la valutazione" (osservato in test reale, 7
    # tentativi su 7). Qui cambiamo la NATURA del bisogno: non piu' "sarebbe
    # utile un parere", ma "la mia raccomandazione terapeutica potrebbe essere
    # PERICOLOSA senza saperlo" - vedi la nuova regola non-facoltativa in
    # SPECIALIST_PROMPT. Fibrillazione atriale (cardiologist: raccomanda
    # anticoagulante) + lividi comparsi da soli senza trauma (possibile
    # disturbo della coagulazione, ambito dermatologist/ematologico) - un
    # cardiologo prudente non dovrebbe avviare un anticoagulante senza sapere
    # se c'e' un disturbo della coagulazione sottostante. Dermatologist resta
    # FUORI dal tavolo apposta (qui bypassiamo il supervisore, quindi lo
    # decidiamo noi, a differenza della chat dal vivo dove deciderebbe il
    # supervisore stesso).
    card = PatientCard(
        first_name="Giorgio",
        last_name="Bianchi",
        age="65",
        sex="maschile",
        previous_conditions=["fibrillazione atriale nota"],
        symptom=SymptomProfile(symptoms=[
            Symptom(description="palpitazioni irregolari", intensity="forte", duration="2 ore"),
            Symptom(description="lividi estesi comparsi da soli sulle braccia e sulle gambe", intensity="moderata", duration="una settimana",
                    trigger="compaiono senza traumi o urti"),
        ]),
    )

    initial_state = MedicalState(patient_card=card)
    app.update_state(config, initial_state.model_dump())

    # Fingiamo che il supervisore abbia scelto UN SOLO specialista - e' l'UNICA
    # cosa che bypassiamo. router/specialist_node/primary_node restano reali.
    app.update_state(
        config,
        {"needed_specialists": {"cardiologist": True}},
        as_node="supervisor",
    )

    print("=" * 70)
    print("Avvio tavola rotonda con UN SOLO specialista pre-selezionato (cardiologist)")
    print("Verifica se chiama in causa dermatologist con un mini-consulto")
    print("(caso a sicurezza critica: anticoagulante + lividi inspiegati)")
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

    print(f"\nneeded_specialists finale: {final_state.get('needed_specialists')}")
    print(f"specialisti reclutati durante la discussione: {final_state.get('recruited_specialists_count')}")

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

    print(f"\ntotal_turns finale: {final_state.get('total_turns')}")
    print(f"\nfinal_diagnosis: {final_state.get('final_diagnosis')}")

    reclutato = final_state.get("recruited_specialists_count", 0) > 0
    print("\n" + "=" * 70)
    if reclutato:
        print("✅ MINI-CONSULTO scattato: un secondo specialista e' stato coinvolto durante la discussione.")
    else:
        print("⚠️ MINI-CONSULTO NON scattato in questa esecuzione: cardiologist non ha chiamato in causa nessuno.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
