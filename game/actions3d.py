"""Validate browser payloads and turn them into per-session input state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .combat3d import ShotResult, fire_hitscan
from .inventory import consume_food, equip_next, interact_nearby
from .runtime import GameRuntime, respawn_player
from .vectors import Vec3


@dataclass(frozen=True)
class ActionResult:
    changed: bool
    shot: ShotResult | None = None


def _number(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Input field {key!r} must be a number.")
    return float(value)


def apply_action(runtime: GameRuntime, session_id: str, payload: dict[str, Any]) -> ActionResult:
    action_type = payload.get("type")
    if action_type == "restart":
        respawn_player(runtime, session_id)
        return ActionResult(True)
    if action_type == "interact":
        return ActionResult(interact_nearby(runtime, session_id))
    if action_type == "equip_next":
        return ActionResult(equip_next(runtime, session_id))
    if action_type == "eat":
        return ActionResult(consume_food(runtime, session_id))
    if action_type == "shoot":
        raw_direction = payload.get("direction")
        if not isinstance(raw_direction, dict):
            raise ValueError("A 3D direction is required.")
        direction = Vec3(
            _number(raw_direction, "x"),
            _number(raw_direction, "y"),
            _number(raw_direction, "z"),
        )
        shot = fire_hitscan(runtime, session_id, direction)
        return ActionResult(shot.fired, shot)
    if action_type != "input":
        return ActionResult(False)
    sequence = payload.get("sequence")
    jump = payload.get("jump", False)
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        raise ValueError("Input sequence must be an integer.")
    if not isinstance(jump, bool):
        raise ValueError("Input jump must be a boolean.")
    return ActionResult(
        runtime.require_session(session_id).apply_input(
            sequence=sequence,
            forward=_number(payload, "forward"),
            strafe=_number(payload, "strafe"),
            yaw=_number(payload, "yaw"),
            pitch=_number(payload, "pitch"),
            jump=jump,
        )
    )
