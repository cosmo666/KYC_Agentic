from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.graph.state import KYCState


# Nodes return *deltas*. LangGraph merges them via the reducers declared on
# KYCState (in particular `add_messages` for the messages field). Mutating
# state in place and returning it would cause `add_messages` to double-count
# the new messages.


def _greet(state: KYCState) -> dict:
    return {
        "messages": [
            {
                "role": "assistant",
                "content": "Hi! I'll help you complete your KYC. What's your full name?",
            }
        ],
        "next_required": "wait_for_name",
    }


def _ask_name(state: KYCState) -> dict:
    # No-op stub — real orchestrator replaces this in Phase 6.
    return {}


def _done(state: KYCState) -> dict:
    return {"next_required": "done"}


def build_graph():
    g = StateGraph(KYCState)
    g.add_node("greet", _greet)
    g.add_node("ask_name", _ask_name)
    g.add_node("done", _done)

    g.set_entry_point("greet")
    g.add_edge("greet", "ask_name")
    g.add_edge("ask_name", "done")
    g.add_edge("done", END)
    return g
