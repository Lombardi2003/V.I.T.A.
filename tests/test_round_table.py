# Script diagnostico (NON un test automatico con assert - il contenuto della
# discussione lo scrive l'LLM in linguaggio libero, non e' verificabile con
# un confronto esatto): verifica dal vivo se il meccanismo di discussione del
# tavolo rotondo funziona quando PIU' di uno specialista e' coinvolto.
#
# Aggira solo la selezione del supervisore (gia' noto come punto debole: con
# temperature=0 seleziona quasi sempre un solo specialista anche con sintomi
# di sistemi diversi, vedi ARCHITECTURE.md) tramite update_state(as_node=...)
# di LangGraph - tutto il resto (router, specialist_node, primary_node) e'
# codice di produzione reale e non modificato, con vere chiamate all'LLM.
#
# Uso: python -m tests.test_round_table
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

    # Due sintomi di sistemi clinici scollegati (addominale vs. cutaneo) -
    # stesso caso gia' usato nel test manuale in chat, dove il supervisore
    # aveva scelto solo "gastroenterologist" ignorando l'eruzione cutanea.
    card = PatientCard(
        first_name="Laura",
        last_name="Bianchi",
        age="34",
        sex="femminile",
        symptom=SymptomProfile(symptoms=[
            Symptom(description="dolore addominale tipo crampi", intensity="forte", duration="6 ore"),
            Symptom(description="eruzione cutanea con macchie rosse pruriginose", intensity="moderata", duration="3 ore"),
        ]),
    )

    initial_state = MedicalState(patient_card=card)
    app.update_state(config, initial_state.model_dump())

    # Fingiamo che il supervisore abbia gia' scelto DUE specialisti - e' l'UNICA
    # cosa che bypassiamo. router/specialist_node/primary_node restano reali.
    app.update_state(
        config,
        {"needed_specialists": {"gastroenterologist": True, "dermatologist": True}},
        as_node="supervisor",
    )

    print("=" * 70)
    print("Avvio tavola rotonda con 2 specialisti pre-selezionati")
    print("(gastroenterologist, dermatologist)")
    print("=" * 70)

    async for event in app.astream_events(None, config=config, version="v2"):
        kind = event["event"]
        node_name = event.get("metadata", {}).get("langgraph_node", "")

        if kind == "on_chain_error":
            print(f"\nERRORE in {node_name}: {event.get('data', {}).get('error')}")

        if kind == "on_chain_end" and node_name in (
            "router", "gastroenterologist", "dermatologist", "chief_physician"
        ):
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

    print(f"\nspecialisti reclutati durante la discussione: {final_state.get('recruited_specialists_count')}")
    print(f"total_turns finale: {final_state.get('total_turns')}")
    print(f"\nfinal_diagnosis: {final_state.get('final_diagnosis')}")


if __name__ == "__main__":
    asyncio.run(main())
