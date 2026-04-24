import uuid

import pytest

from app.graph.builder import build_graph
from app.graph.checkpointer import open_checkpointer


@pytest.mark.asyncio
async def test_greet_entry_reaches_wait_for_name():
    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        thread = {"configurable": {"thread_id": f"test-{uuid.uuid4()}"}}
        out = await graph.ainvoke(
            {"session_id": "s1", "messages": [], "language": "en"},
            config=thread,
        )
        # Greet emits no message itself — the /chat route is responsible for
        # the assistant reply. Graph halts at the first wait state.
        assert out["next_required"] == "wait_for_name"
        assert out["language"] == "en"


@pytest.mark.asyncio
async def test_capture_name_to_wait_for_aadhaar():
    async with open_checkpointer() as saver:
        graph = build_graph().compile(checkpointer=saver)
        thread = {"configurable": {"thread_id": f"test-{uuid.uuid4()}"}}
        out = await graph.ainvoke(
            {
                "session_id": "s2",
                "language": "en",
                "next_required": "wait_for_name",
                "messages": [{"role": "user", "content": "my name is Asha Sharma"}],
            },
            config=thread,
        )
        assert out["next_required"] == "wait_for_aadhaar_image"
        assert out["user_name"] == "Asha Sharma"
