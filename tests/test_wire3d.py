import pytest

from game.actions3d import apply_action
from game.components import ControlledBy, Transform
from game.runtime import create_runtime, step_runtime
from game.wire import SCHEMA_VERSION, chunk_to_wire, snapshot_for_session


def test_snapshot_is_explicit_versioned_and_scoped_to_a_session():
    runtime = create_runtime("browser-a")
    step_runtime(runtime)
    snapshot = snapshot_for_session(runtime, "browser-a")

    assert snapshot["schema_version"] == SCHEMA_VERSION
    assert snapshot["server_tick"] == 1
    assert snapshot["world_id"] == "development-world"
    assert snapshot["you"]["session_id"] == "browser-a"
    assert snapshot["you"]["player_entity_id"] == 1
    assert snapshot["you"]["survival_seconds"] == pytest.approx(1 / 60)
    assert "blocks" not in snapshot
    assert snapshot["chunks"]

    player = snapshot["entities"][0]
    assert player["id"] == snapshot["you"]["player_entity_id"]
    assert player["components"]["transform"]["y"] == pytest.approx(0, abs=1e-5)
    assert "collider" in player["components"]
    assert "grounded" in player["components"]
    assert "controlled_by" not in player["components"]


def test_chunk_payload_is_fetched_separately_and_revision_tracks_edits():
    runtime = create_runtime()
    descriptor = next(chunk for chunk in snapshot_for_session(runtime, "local")["chunks"] if chunk["x"] == 0 and chunk["z"] == 0)
    first = chunk_to_wire(runtime, 0, 0)
    assert first["revision"] == descriptor["revision"]
    assert first["blocks"]

    runtime.world.set_block(3, 0, 3, "stone")
    second = chunk_to_wire(runtime, 0, 0)
    assert second["revision"] == first["revision"] + 1
    assert [3, 0, 3, "stone"] in second["blocks"]


def test_snapshot_requires_the_requested_session():
    runtime = create_runtime()
    with pytest.raises(KeyError, match="Unknown session"):
        snapshot_for_session(runtime, "missing")


def test_action_validation_updates_only_newer_sequenced_input():
    runtime = create_runtime()
    assert apply_action(
        runtime,
        "local",
        {"type": "input", "sequence": 2, "forward": 1, "strafe": 0, "yaw": 0, "pitch": 0, "jump": True},
    ).changed is True
    assert apply_action(
        runtime,
        "local",
        {"type": "input", "sequence": 1, "forward": -1, "strafe": 0, "yaw": 0, "pitch": 0, "jump": False},
    ).changed is False
    with pytest.raises(ValueError, match="sequence"):
        apply_action(
            runtime,
            "local",
            {"type": "input", "sequence": 1.5, "forward": 0, "strafe": 0, "yaw": 0, "pitch": 0},
        )
