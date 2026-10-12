import asyncio

import pytest
from fastapi import HTTPException

from app import app, get_chunk, get_state, index, lifespan, post_action


def test_3d_http_shell_exposes_state_chunks_and_sequenced_actions():
    async def scenario():
        async with lifespan(app):
            root = await index()
            state = await get_state()
            descriptor = state["chunks"][0]
            chunk = await get_chunk(descriptor["x"], descriptor["z"])
            action = await post_action(
                {
                    "type": "input",
                    "sequence": 1,
                    "forward": 1,
                    "strafe": 0,
                    "yaw": 0,
                    "pitch": 0,
                    "jump": False,
                }
            )
            return root, state, descriptor, chunk, action

    root, state, descriptor, chunk, action = asyncio.run(scenario())
    assert root.path.name == "index.html"
    assert state["schema_version"] == 1
    assert chunk["revision"] == descriptor["revision"]
    assert action == {"changed": True}


def test_3d_http_shell_rejects_invalid_input_and_missing_chunks():
    async def scenario():
        async with lifespan(app):
            with pytest.raises(HTTPException) as invalid_error:
                await post_action(
                    {
                        "type": "input",
                        "sequence": "old",
                        "forward": 0,
                        "strafe": 0,
                        "yaw": 0,
                        "pitch": 0,
                        "jump": False,
                    }
                )
            with pytest.raises(HTTPException) as chunk_error:
                await get_chunk(999, 999)
            return invalid_error.value, chunk_error.value

    invalid_error, chunk_error = asyncio.run(scenario())
    assert invalid_error.status_code == 422
    assert chunk_error.status_code == 425
