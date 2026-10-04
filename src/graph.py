"""The graph: which nodes exist, how they follow each other and where the conversation pauses."""

from langgraph.graph import StateGraph, START,END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from langchain_core.messages import HumanMessage

from src.state import MedicalState
from src.agents import reviewer_node, read_db_node, intake_node, save_db_node, supervisor_node, cardiologist_node, neurologist_node, primary_node, photography_node, orthopedic_node, gastroenterologist_node, dermatologist_node, pneumologist_node, ent_node, ophthalmologist_node, urologist_node, general_practitioner_node, router, MAX_TOTAL_TURNS
from src.log import get_logger

log = get_logger("graph")


async def user_node(state: MedicalState):
    """Pause point: the message is already in the state, so nothing is added here."""
    if state.triage_history and isinstance(state.triage_history[-1], HumanMessage):
        log.debug("operator message: %s", state.triage_history[-1].content.strip())

    return {}


def generate_graph():
    """Builds and compiles the graph, pausing before every `user` node."""
    workflow = StateGraph(MedicalState)

    workflow.add_node("read_db", read_db_node)
    workflow.add_node("user", user_node)
    workflow.add_node("intake", intake_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("photography", photography_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("router", router)
    workflow.add_node("cardiologist", cardiologist_node)
    workflow.add_node("neurologist", neurologist_node)
    workflow.add_node("orthopedist", orthopedic_node)
    workflow.add_node("gastroenterologist", gastroenterologist_node)
    workflow.add_node("dermatologist", dermatologist_node)
    workflow.add_node("pulmonologist", pneumologist_node)
    workflow.add_node("ent", ent_node)
    workflow.add_node("ophthalmologist", ophthalmologist_node)
    workflow.add_node("urologist", urologist_node)
    workflow.add_node("general_practitioner", general_practitioner_node)
    workflow.add_node("chief_physician", primary_node)
    workflow.add_node("save_db", save_db_node)

    # A completed step goes straight to the next node; an incomplete one goes to `user`, where the graph pauses.
    workflow.add_edge(START, "read_db")
    workflow.add_conditional_edges(
        "read_db",
        lambda state: "intake" if state.next_step == "intake" else "user",
        {"intake": "intake", "user": "user"},
    )
    workflow.add_conditional_edges(
        "intake",
        lambda state: "reviewer" if state.next_step == "reviewer" else "user",
        {"reviewer": "reviewer", "user": "user"},
    )
    workflow.add_conditional_edges(
        "reviewer",
        lambda state: "photography" if state.next_step == "photography" else "user",
        {"photography": "photography", "user": "user"},
    )
    workflow.add_conditional_edges(
        "photography",
        lambda state: "supervisor" if state.next_step == "supervisor" else "user",
        {"supervisor": "supervisor", "user": "user"},
    )

    workflow.add_conditional_edges(
        "user",
        # After the pause, resume at the node that asked for the message.
        lambda state: state.next_step if state.next_step else "reviewer",
        {
            "read_db":     "read_db",
            "intake":      "intake",
            "reviewer":    "reviewer",
            "photography": "photography",
            "supervisor":  "supervisor",
        }
        )

    # The table: the router picks a specialist, who hands back to the router.
    workflow.add_edge("supervisor", "router")

    workflow.add_conditional_edges(
        "router",
        lambda state: state.next_step,
        {
            "cardiologist": "cardiologist",
            "neurologist": "neurologist",
            "orthopedist": "orthopedist",
            "gastroenterologist": "gastroenterologist",
            "dermatologist": "dermatologist",
            "pulmonologist": "pulmonologist",
            "ent": "ent",
            "ophthalmologist": "ophthalmologist",
            "urologist": "urologist",
            "general_practitioner": "general_practitioner",
            "chief_physician": "chief_physician",
        }
    )

    workflow.add_edge("cardiologist", "router")
    workflow.add_edge("neurologist", "router")
    workflow.add_edge("orthopedist", "router")
    workflow.add_edge("gastroenterologist", "router")
    workflow.add_edge("dermatologist", "router")
    workflow.add_edge("pulmonologist", "router")
    workflow.add_edge("ent", "router")
    workflow.add_edge("ophthalmologist", "router")
    workflow.add_edge("urologist", "router")
    workflow.add_edge("general_practitioner", "router")

    workflow.add_edge("chief_physician", "save_db")
    workflow.add_edge("save_db", END)

    # Register the nested state types, or the checkpointer warns at every save.
    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("src.state", "GroupHypothesis"),
            ("src.state", "RoundTableEntry"),
        ]
    )
    memory = MemorySaver(serde=serde)
    return workflow.compile(
        checkpointer=memory,
        interrupt_before=["user"]
    )


# Steps allowed in one run; LangGraph's default (25) is less than a 12-turn discussion needs.
RECURSION_LIMIT = 2 * MAX_TOTAL_TURNS + 20


def thread_config(thread_id: str) -> dict:
    """Configuration every caller must use: the thread and the step limit."""
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}


def photo_next(state: MedicalState):
    """Unused routing helper of an earlier version."""
    return state.next_step


def triage_complete(state: MedicalState):
    """Unused routing helper of an earlier version."""
    return state.triage_complete


def user_next(state: MedicalState):
    """Unused routing helper of an earlier version."""
    return state.next_step
