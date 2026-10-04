"""Shared code for the live scripts: start the round table on the real graph and print what happened."""
import uuid

# Import the function by name: the package attribute chainlit.context is not the submodule.
from chainlit.context import init_http_context

from src.graph import generate_graph, thread_config
from src.state import MedicalState

ALL_SPECIALIST_NODES = (
    "cardiologist", "neurologist", "orthopedist", "gastroenterologist",
    "dermatologist", "pulmonologist", "ent", "ophthalmologist",
    "urologist", "general_practitioner",
)


async def run_table(card, seated, extra_state=None):
    """HELPER run_table: seats the given specialists (skipping the supervisor) and runs table and primary with the real model."""
    # The nodes need an active Chainlit context: this one has a no-op emitter.
    init_http_context()
    app = generate_graph()
    config = thread_config(str(uuid.uuid4()))
    app.update_state(config, MedicalState(patient_card=card).model_dump())
    # Only the supervisor's choice is skipped.
    app.update_state(config, {"needed_specialists": {r: True for r in seated}, **(extra_state or {})}, as_node="supervisor")

    async for event in app.astream_events(None, config=config, version="v2"):
        kind = event["event"]
        node = event.get("metadata", {}).get("langgraph_node", "")
        if kind == "on_chain_error":
            print(f"\nERROR in {node}: {event.get('data', {}).get('error')}")
        if kind == "on_chain_end" and node in (*ALL_SPECIALIST_NODES, "router", "chief_physician"):
            output = event.get("data", {}).get("output")
            if isinstance(output, dict) and output:
                print(f"\n--- {node} updated: {list(output.keys())} ---")
    return app.get_state(config).values


def _field(obj, name):
    """HELPER _field: a field of a state value, whether it is a Pydantic model or a dict."""
    return getattr(obj, name) if hasattr(obj, name) else (obj or {}).get(name)


def print_final_state(state):
    """HELPER print_final_state: prints the discussion, the group hypothesis and the final diagnosis."""
    print("\n" + "=" * 70)
    print("FINAL STATE")
    print("=" * 70)
    entries = state.get("round_table", [])
    print(f"\nround_table ({len(entries)} entries):")
    for e in entries:
        action = _field(e, "azione")
        tag = f" [{action}]" if action else ""
        print(f"  [{_field(e, 'author')} -> {_field(e, 'to') or 'everyone'}]{tag} {_field(e, 'content')}")
    print(f"\nfinal group_hypothesis: {state.get('group_hypothesis')}")
    print(f"\nneeded_specialists: {state.get('needed_specialists')}")
    print(f"recruited during the discussion: {state.get('recruited_specialists_count')}")
    print(f"total_turns: {state.get('total_turns')}")
    print(f"\nfinal_diagnosis: {state.get('final_diagnosis')}")


def print_verdict(ok, ok_text, ko_text):
    """HELPER print_verdict: prints the outcome line of a live script."""
    print("\n" + "=" * 70)
    print(("✅ " + ok_text) if ok else ("⚠️ " + ko_text))
    print("=" * 70)
