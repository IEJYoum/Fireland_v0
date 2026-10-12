"""Explicit transport-neutral snapshots for the 3D client."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from .components import (
    Collider,
    Equipment,
    Grounded,
    Health,
    Inventory,
    Lifetime,
    Pickup,
    Renderable,
    Transform,
    Velocity,
)
from .entities import Entity
from .runtime import ACTIVE_RADIUS, GameRuntime
from .world3d import CHUNK_SIZE_X, CHUNK_SIZE_Z


SCHEMA_VERSION = 1
ComponentSerializer = tuple[str, Callable[[object], dict[str, Any]]]


def _transform_to_wire(component: object) -> dict[str, Any]:
    transform = component
    assert isinstance(transform, Transform)
    return {
        "x": transform.position.x,
        "y": transform.position.y,
        "z": transform.position.z,
        "yaw": transform.yaw,
        "pitch": transform.pitch,
    }


def _velocity_to_wire(component: object) -> dict[str, Any]:
    velocity = component
    assert isinstance(velocity, Velocity)
    return {"x": velocity.value.x, "y": velocity.value.y, "z": velocity.value.z}


def _collider_to_wire(component: object) -> dict[str, Any]:
    collider = component
    assert isinstance(collider, Collider)
    return {
        "half_x": collider.box.half_x,
        "height": collider.box.height,
        "half_z": collider.box.half_z,
    }


def _grounded_to_wire(component: object) -> dict[str, Any]:
    grounded = component
    assert isinstance(grounded, Grounded)
    return {"value": grounded.value}


def _health_to_wire(component: object) -> dict[str, Any]:
    health = component
    assert isinstance(health, Health)
    return {"current": health.current, "maximum": health.maximum}


def _inventory_to_wire(component: object) -> dict[str, Any]:
    inventory = component
    assert isinstance(inventory, Inventory)
    return {"item_ids": list(inventory.item_ids)}


def _equipment_to_wire(component: object) -> dict[str, Any]:
    equipment = component
    assert isinstance(equipment, Equipment)
    return {"equipped_item_id": equipment.equipped_item_id}


def _pickup_to_wire(component: object) -> dict[str, Any]:
    pickup = component
    assert isinstance(pickup, Pickup)
    return {"kind": pickup.kind}


def _renderable_to_wire(component: object) -> dict[str, Any]:
    renderable = component
    assert isinstance(renderable, Renderable)
    return {"appearance_key": renderable.appearance_key}


def _lifetime_to_wire(component: object) -> dict[str, Any]:
    lifetime = component
    assert isinstance(lifetime, Lifetime)
    return {"seconds": lifetime.seconds}


# This mapping is the deliberate public opt-in. Components absent here remain
# server-private even though their entities are included in a snapshot.
WIRE_COMPONENTS: dict[type[object], ComponentSerializer] = {
    Transform: ("transform", _transform_to_wire),
    Velocity: ("velocity", _velocity_to_wire),
    Collider: ("collider", _collider_to_wire),
    Grounded: ("grounded", _grounded_to_wire),
    Health: ("health", _health_to_wire),
    Inventory: ("inventory", _inventory_to_wire),
    Equipment: ("equipment", _equipment_to_wire),
    Pickup: ("pickup", _pickup_to_wire),
    Renderable: ("renderable", _renderable_to_wire),
    Lifetime: ("lifetime", _lifetime_to_wire),
}


def entity_to_wire(entity: Entity) -> dict[str, Any]:
    components: dict[str, dict[str, Any]] = {}
    for component_type, component in entity.components.items():
        serializer_entry = WIRE_COMPONENTS.get(component_type)
        if serializer_entry is None:
            continue
        wire_key, serializer = serializer_entry
        components[wire_key] = serializer(component)
    return {"id": entity.id, "def_key": entity.def_key, "components": components}


def snapshot_for_session(runtime: GameRuntime, session_id: str) -> dict[str, Any]:
    session = runtime.require_session(session_id)
    player = runtime.entities.require(session.player_entity_id)
    player_position = player.require(Transform).position
    active_radius_squared = ACTIVE_RADIUS * ACTIVE_RADIUS
    visible_entity_ids = {player.id}
    inventory = player.get(Inventory)
    if inventory is not None:
        visible_entity_ids.update(inventory.item_ids)
    for entity in runtime.entities.query(Transform):
        position = entity.require(Transform).position
        if (
            (position.x - player_position.x) ** 2 + (position.z - player_position.z) ** 2
            <= active_radius_squared
        ):
            visible_entity_ids.add(entity.id)

    player_chunk_x = int(player_position.x // CHUNK_SIZE_X)
    player_chunk_z = int(player_position.z // CHUNK_SIZE_Z)
    chunk_radius = math.ceil(ACTIVE_RADIUS / max(CHUNK_SIZE_X, CHUNK_SIZE_Z))
    chunks = [
        {"x": chunk_x, "z": chunk_z, "revision": chunk.revision}
        for (chunk_x, chunk_z), chunk in sorted(runtime.world.chunks.items())
        if max(abs(chunk_x - player_chunk_x), abs(chunk_z - player_chunk_z)) <= chunk_radius
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "server_tick": runtime.server_tick,
        "world_id": runtime.world_id,
        "you": {"session_id": session.id, "player_entity_id": session.player_entity_id},
        "entities": [
            entity_to_wire(entity)
            for entity in sorted(runtime.entities.entities.values(), key=lambda value: value.id)
            if entity.id in visible_entity_ids
        ],
        "chunks": chunks,
    }


def chunk_to_wire(runtime: GameRuntime, chunk_x: int, chunk_z: int) -> dict[str, Any]:
    chunk = runtime.world.require_chunk((chunk_x, chunk_z))
    blocks = [
        [
            world_x - chunk_x * CHUNK_SIZE_X,
            y,
            world_z - chunk_z * CHUNK_SIZE_Z,
            block_key,
        ]
        for world_x, y, world_z, block_key in runtime.world.iter_non_air_blocks((chunk_x, chunk_z))
    ]
    blocks.sort(key=lambda block: (block[1], block[2], block[0]))
    return {
        "schema_version": SCHEMA_VERSION,
        "world_id": runtime.world_id,
        "x": chunk_x,
        "z": chunk_z,
        "revision": chunk.revision,
        "blocks": blocks,
    }
