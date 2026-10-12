"""Authoritative block/entity raycasts, hitscan attacks, and pickup interaction."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Literal

from .components import Collider, Equipment, Health, Inventory, Pickup, Transform, Weapon
from .entities import Entity, EntityStore
from .runtime import GameRuntime
from .vectors import Aabb, Vec3
from .world3d import World


EYE_HEIGHT = 1.65
INTERACTION_DISTANCE = 3.0
_RAY_EPSILON = 1e-9


@dataclass(frozen=True)
class RayHit:
    kind: Literal["block", "entity"]
    distance: float
    point: Vec3
    block: tuple[int, int, int] | None = None
    entity_id: int | None = None


def normalized_direction(direction: Vec3) -> Vec3:
    if not direction.is_finite():
        raise ValueError("Ray direction must be finite.")
    length = direction.length()
    if length <= _RAY_EPSILON:
        raise ValueError("Ray direction cannot be zero.")
    return direction / length


def ray_aabb_distance(origin: Vec3, direction: Vec3, position: Vec3, box: Aabb, max_distance: float) -> float | None:
    bounds = box.bounds_at(position)
    minimums = bounds[:3]
    maximums = bounds[3:]
    near = 0.0
    far = max_distance
    for ray_origin, ray_direction, minimum, maximum in zip(
        (origin.x, origin.y, origin.z),
        (direction.x, direction.y, direction.z),
        minimums,
        maximums,
    ):
        if abs(ray_direction) <= _RAY_EPSILON:
            if ray_origin < minimum or ray_origin > maximum:
                return None
            continue
        first = (minimum - ray_origin) / ray_direction
        second = (maximum - ray_origin) / ray_direction
        axis_near, axis_far = min(first, second), max(first, second)
        near = max(near, axis_near)
        far = min(far, axis_far)
        if near > far:
            return None
    return near if 0 <= near <= max_distance else None


def raycast_blocks(world: World, origin: Vec3, direction: Vec3, max_distance: float) -> RayHit | None:
    cell = [math.floor(origin.x), math.floor(origin.y), math.floor(origin.z)]
    if world.is_solid(*cell):
        return RayHit("block", 0.0, origin, block=tuple(cell))

    step = [1 if component > 0 else -1 if component < 0 else 0 for component in (direction.x, direction.y, direction.z)]
    delta = [abs(1 / component) if abs(component) > _RAY_EPSILON else math.inf for component in (direction.x, direction.y, direction.z)]
    origins = (origin.x, origin.y, origin.z)
    directions = (direction.x, direction.y, direction.z)
    next_distances = []
    for axis in range(3):
        if step[axis] > 0:
            boundary = cell[axis] + 1
        else:
            boundary = cell[axis]
        next_distances.append(
            (boundary - origins[axis]) / directions[axis]
            if step[axis] != 0
            else math.inf
        )

    while True:
        axis = min(range(3), key=next_distances.__getitem__)
        distance = next_distances[axis]
        if distance > max_distance:
            return None
        cell[axis] += step[axis]
        next_distances[axis] += delta[axis]
        if world.is_solid(*cell):
            return RayHit(
                "block",
                distance,
                origin + direction * distance,
                block=tuple(cell),
            )


def raycast_entities(
    entities: EntityStore,
    origin: Vec3,
    direction: Vec3,
    max_distance: float,
    predicate: Callable[[Entity], bool],
    excluded_entity_ids: set[int] | None = None,
) -> RayHit | None:
    excluded = excluded_entity_ids or set()
    nearest: RayHit | None = None
    for entity in entities.query(Transform, Collider):
        if entity.id in excluded or not predicate(entity):
            continue
        distance = ray_aabb_distance(
            origin,
            direction,
            entity.require(Transform).position,
            entity.require(Collider).box,
            max_distance,
        )
        if distance is not None and (nearest is None or distance < nearest.distance):
            nearest = RayHit(
                "entity",
                distance,
                origin + direction * distance,
                entity_id=entity.id,
            )
    return nearest


def raycast(
    world: World,
    entities: EntityStore,
    origin: Vec3,
    direction: Vec3,
    max_distance: float,
    predicate: Callable[[Entity], bool],
    excluded_entity_ids: set[int] | None = None,
) -> RayHit | None:
    if max_distance <= 0:
        return None
    direction = normalized_direction(direction)
    block_hit = raycast_blocks(world, origin, direction, max_distance)
    entity_limit = block_hit.distance if block_hit is not None else max_distance
    entity_hit = raycast_entities(
        entities,
        origin,
        direction,
        entity_limit,
        predicate,
        excluded_entity_ids,
    )
    return entity_hit or block_hit


def player_eye_origin(runtime: GameRuntime, player_id: int) -> Vec3:
    player = runtime.entities.require(player_id)
    position = player.require(Transform).position
    collider = player.require(Collider).box
    return Vec3(position.x, position.y + min(EYE_HEIGHT, collider.height - 0.05), position.z)


def fire_hitscan(runtime: GameRuntime, session_id: str, direction: Vec3) -> bool:
    session = runtime.require_session(session_id)
    player = runtime.entities.require(session.player_entity_id)
    equipped_id = player.require(Equipment).equipped_item_id
    if equipped_id is None:
        return False
    weapon_entity = runtime.entities.require(equipped_id)
    weapon = weapon_entity.get(Weapon)
    if weapon is None or weapon.seconds_until_ready > 0:
        return False
    direction = normalized_direction(direction)
    weapon.seconds_until_ready = weapon.cooldown_seconds
    hit = raycast(
        runtime.world,
        runtime.entities,
        player_eye_origin(runtime, player.id),
        direction,
        weapon.max_distance,
        predicate=lambda entity: entity.has(Health),
        excluded_entity_ids={player.id},
    )
    if hit is None or hit.entity_id is None:
        return True
    target = runtime.entities.require(hit.entity_id)
    health = target.require(Health)
    health.current = max(0, health.current - weapon.damage)
    if health.current == 0:
        runtime.entities.remove(target.id)
    return True


def interact_pickup(runtime: GameRuntime, session_id: str, direction: Vec3) -> bool:
    session = runtime.require_session(session_id)
    player = runtime.entities.require(session.player_entity_id)
    direction = normalized_direction(direction)
    hit = raycast(
        runtime.world,
        runtime.entities,
        player_eye_origin(runtime, player.id),
        direction,
        INTERACTION_DISTANCE,
        predicate=lambda entity: entity.has(Pickup),
        excluded_entity_ids={player.id},
    )
    if hit is None or hit.entity_id is None:
        return False
    item = runtime.entities.require(hit.entity_id)
    item.remove(Transform)
    item.remove(Pickup)
    inventory = player.require(Inventory)
    inventory.item_ids.append(item.id)
    if item.has(Weapon):
        player.require(Equipment).equipped_item_id = item.id
    return True
