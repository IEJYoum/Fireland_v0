"""Explicit transport-neutral snapshots for the 3D client."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .components import (
    Armor,
    Collider,
    Equipment,
    Faction,
    Grounded,
    Health,
    HostileAI,
    Hunger,
    Inventory,
    Item,
    Lifetime,
    Pickup,
    Renderable,
    Transform,
    Velocity,
    Weapon,
    Xp,
)
from .entities import Entity
from .runtime import GameRuntime, streamed_chunk_keys_for_session, visible_entity_ids_for_session
from .world3d import CHUNK_SIZE_X, CHUNK_SIZE_Z


SCHEMA_VERSION = 2
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
    return {"item_ids": list(inventory.item_ids), "capacity": inventory.capacity}


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


def _hunger_to_wire(component: object) -> dict[str, Any]:
    hunger = component
    assert isinstance(hunger, Hunger)
    return {"current": hunger.current, "maximum": hunger.maximum}


def _armor_to_wire(component: object) -> dict[str, Any]:
    armor = component
    assert isinstance(armor, Armor)
    return {"value": armor.value}


def _xp_to_wire(component: object) -> dict[str, Any]:
    xp = component
    assert isinstance(xp, Xp)
    return {"points": xp.points}


def _faction_to_wire(component: object) -> dict[str, Any]:
    faction = component
    assert isinstance(faction, Faction)
    return {"key": faction.key}


def _item_to_wire(component: object) -> dict[str, Any]:
    item = component
    assert isinstance(item, Item)
    return {
        "display_name": item.display_name,
        "kind": item.kind,
        "projectile_speed": item.projectile_speed,
        "projectile_lifetime": item.projectile_lifetime,
    }


def _weapon_to_wire(component: object) -> dict[str, Any]:
    weapon = component
    assert isinstance(weapon, Weapon)
    return {
        "damage": weapon.damage,
        "max_distance": weapon.max_distance,
        "cooldown_seconds": weapon.cooldown_seconds,
        "seconds_until_ready": weapon.seconds_until_ready,
        "attack_style": weapon.attack_style,
    }


def _hostile_ai_to_wire(component: object) -> dict[str, Any]:
    hostile = component
    assert isinstance(hostile, HostileAI)
    return {"mode": hostile.mode}


# This mapping is the deliberate public opt-in. Components absent here remain
# server-private even though their entities are included in a snapshot.
WIRE_COMPONENTS: dict[type[object], ComponentSerializer] = {
    Transform: ("transform", _transform_to_wire),
    Velocity: ("velocity", _velocity_to_wire),
    Collider: ("collider", _collider_to_wire),
    Grounded: ("grounded", _grounded_to_wire),
    Health: ("health", _health_to_wire),
    Hunger: ("hunger", _hunger_to_wire),
    Armor: ("armor", _armor_to_wire),
    Xp: ("xp", _xp_to_wire),
    Faction: ("faction", _faction_to_wire),
    Inventory: ("inventory", _inventory_to_wire),
    Equipment: ("equipment", _equipment_to_wire),
    Pickup: ("pickup", _pickup_to_wire),
    Renderable: ("renderable", _renderable_to_wire),
    Lifetime: ("lifetime", _lifetime_to_wire),
    Item: ("item", _item_to_wire),
    Weapon: ("weapon", _weapon_to_wire),
    HostileAI: ("hostile_ai", _hostile_ai_to_wire),
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
    visible_entity_ids = visible_entity_ids_for_session(runtime, session_id)
    streamed_chunk_keys = streamed_chunk_keys_for_session(runtime, session_id)
    chunks = [
        {
            "x": chunk_x,
            "z": chunk_z,
            "revision": chunk.revision,
            "biome": chunk.biome_key,
        }
        for (chunk_x, chunk_z), chunk in sorted(runtime.world.chunks.items())
        if (chunk_x, chunk_z) in streamed_chunk_keys
    ]
    player_transform = player.require(Transform)
    player_chunk_key = (
        player_transform.position.x // CHUNK_SIZE_X,
        player_transform.position.z // CHUNK_SIZE_Z,
    )
    current_chunk = runtime.world.get_chunk(
        (int(player_chunk_key[0]), int(player_chunk_key[1]))
    )
    visible_hostiles = sum(
        1
        for entity_id in visible_entity_ids
        if (entity := runtime.entities.get(entity_id)) is not None
        and (faction := entity.get(Faction)) is not None
        and faction.key == "hostile"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "server_tick": runtime.server_tick,
        "world_id": runtime.world_id,
        "you": {
            "session_id": session.id,
            "player_entity_id": session.player_entity_id,
            "survival_seconds": session.survival_seconds,
        },
        "entities": [
            entity_to_wire(entity)
            for entity in sorted(runtime.entities.entities.values(), key=lambda value: value.id)
            if entity.id in visible_entity_ids
        ],
        "chunks": chunks,
        "messages": list(runtime.messages),
        "world": {
            "seed": runtime.world.seed,
            "generator": runtime.world.generator_key,
            "biome": current_chunk.biome_key if current_chunk is not None else "unknown",
            "player_chunk": [int(player_chunk_key[0]), int(player_chunk_key[1])],
        },
        "debug": {
            "active_chunks": len(runtime.active_chunk_keys),
            "resident_chunks": len(runtime.world.chunks),
            "visible_entities": len(visible_entity_ids),
            "visible_hostiles": visible_hostiles,
        },
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
        "biome": chunk.biome_key,
        "blocks": blocks,
    }
