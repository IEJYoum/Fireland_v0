"""Validate browser payloads and turn them into per-session input state."""

from __future__ import annotations

from typing import Any

from .combat3d import fire_hitscan, interact_pickup
from .runtime import GameRuntime, respawn_player
from .vectors import Vec3


def _number(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Input field {key!r} must be a number.")
    return float(value)


def apply_action(runtime: GameRuntime, session_id: str, payload: dict[str, Any]) -> bool:
    action_type = payload.get("type")
    if action_type == "restart":
        respawn_player(runtime, session_id)
        return True
    if action_type in {"shoot", "interact"}:
        raw_direction = payload.get("direction")
        if not isinstance(raw_direction, dict):
            raise ValueError("A 3D direction is required.")
        direction = Vec3(
            _number(raw_direction, "x"),
            _number(raw_direction, "y"),
            _number(raw_direction, "z"),
        )
        if action_type == "shoot":
            return fire_hitscan(runtime, session_id, direction)
        return interact_pickup(runtime, session_id, direction)
    if action_type != "input":
        return False
    sequence = payload.get("sequence")
    jump = payload.get("jump", False)
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        raise ValueError("Input sequence must be an integer.")
    if not isinstance(jump, bool):
        raise ValueError("Input jump must be a boolean.")
    return runtime.require_session(session_id).apply_input(
        sequence=sequence,
        forward=_number(payload, "forward"),
        strafe=_number(payload, "strafe"),
        yaw=_number(payload, "yaw"),
        pitch=_number(payload, "pitch"),
        jump=jump,
    )
