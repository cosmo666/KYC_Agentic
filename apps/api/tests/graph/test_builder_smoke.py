import uuid

import pytest
from langchain_core.messages import AIMessage

from app.graph.builder import build_graph
from app.graph.checkpointer import open_checkpointer


@pytest.mark.asyncio
async def test_graph_runs_once():
    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        # Fresh thread each run so we don't accumulate state across reruns.
        thread = {"configurable": {"thread_id": f"test-{uuid.uuid4()}"}}
        out = await graph.ainvoke(
            {"session_id": "s1", "messages": [], "language": "en"},
            config=thread,
        )
        assert out["next_required"] == "done"
        # add_messages reducer normalises dict messages to LangChain BaseMessage.
        assert any(isinstance(m, AIMessage) for m in out["messages"])
        assert len(out["messages"]) == 1
