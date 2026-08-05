# Script diagnostico (NON un test automatico con assert - la scelta la fa
# l'LLM in linguaggio libero, non e' verificabile con un confronto esatto):
# verifica se supervisor_node seleziona TUTTI gli specialisti pertinenti
# quando il paziente ha piu' sintomi di ambiti diversi nella stessa cartella,
# invece di "dimenticarne" uno come osservato in test reale prima del fix
# (analisi per-sintomo forzata in SUPERVISOR_PROMPT, vedi prompts.py).
#
# Copre anche il caso opposto: un sintomo composito (mal di testa + vista
# offuscata) dove UN solo specialista puo' legittimamente coprire entrambi
# (aura emicranica, ambito neurologico) - la nuova struttura non deve forzare
# artificialmente due specialisti quando uno solo e' clinicamente valido.
#
# Uso: python -m tests.test_supervisor_selection
import asyncio

from chainlit.context import init_http_context

from src.agents.clinical import supervisor_node
from src.state import MedicalState, PatientCard, SymptomProfile, Symptom


async def run_case(titolo: str, card: PatientCard):
    state = MedicalState(patient_card=card)
    print("=" * 70)
    print(titolo)
    print("=" * 70)
    result = await supervisor_node(state)
    print(f"\n>>> needed_specialists: {result.get('needed_specialists')}\n")


async def main():
    init_http_context()

    caso_scollegato = PatientCard(
        first_name="Laura", last_name="Bianchi", age="34", sex="femminile",
        symptom=SymptomProfile(symptoms=[
            Symptom(description="dolore addominale tipo crampi", intensity="forte", duration="6 ore"),
            Symptom(description="eruzione cutanea con macchie rosse pruriginose", intensity="moderata", duration="3 ore"),
        ]),
    )
    await run_case("CASO 1: sintomi di ambiti scollegati (attesi 2 specialisti diversi)", caso_scollegato)

    caso_correlato = PatientCard(
        first_name="Luigi", last_name="Ferrari", age="50", sex="maschile",
        symptom=SymptomProfile(symptoms=[
            Symptom(description="mal di testa", intensity="forte", duration="2 giorni"),
            Symptom(description="vista sfocata", intensity="moderata", duration="da 3 ore"),
        ]),
    )
    await run_case("CASO 2: sintomi potenzialmente correlati (neurologia puo' coprire entrambi)", caso_correlato)

    caso_tre_sintomi = PatientCard(
        first_name="Marco", last_name="Rossi", age="45", sex="maschile",
        symptom=SymptomProfile(symptoms=[
            Symptom(description="dolore al petto", intensity="forte", duration="2 ore"),
            Symptom(description="eruzione cutanea con macchie rosse", intensity="lieve", duration="1 giorno"),
            Symptom(description="forte mal di schiena", intensity="forte", duration="3 giorni"),
        ]),
    )
    await run_case("CASO 3: tre sintomi di ambiti diversi (attesi 3 specialisti)", caso_tre_sintomi)


if __name__ == "__main__":
    asyncio.run(main())
