"""Authoritative 3D targeting, weapon attacks, damage, death, and drops."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Literal

from .components import Armor, Collider, Drops, Equipment, Faction, Health, Inventory, Transform, Weapon, Xp
from .entities import Entity, EntityStore
from .items import place_item_as_pickup, spawn_item
from .registry import BehaviorRegistry
from .runtime import GameRuntime
from .vectors import Aabb, Vec3
from .world3d import World


EYE_HEIGHT = 1.65
_RAY_EPSILON = 1e-9
DROP_POOLS = BehaviorRegistry("drop pool")


@dataclass(frozen=True)
class RayHit:
    kind: Literal["block", "entity"]
    distance: float
    point: Vec3
    block: tuple[int, int, int] | None = None
    entity_id: int | None = None


@dataclass(frozen=True)
class ShotResult:
    fired: bool
    origin: Vec3 | None = None
    end: Vec3 | None = None
    hit_kind: Literal["miss", "block", "entity"] | None = None
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


def entity_eye_origin(entity: Entity) -> Vec3:
    position = entity.require(Transform).position
    collider = entity.require(Collider).box
    return Vec3(position.x, position.y + min(EYE_HEIGHT, collider.height - 0.05), position.z)


def player_eye_origin(runtime: GameRuntime, player_id: int) -> Vec3:
    return entity_eye_origin(runtime.entities.require(player_id))


def _is_opposing_target(shooter: Entity, target: Entity) -> bool:
    if target.id == shooter.id or not target.has(Health):
        return False
    shooter_faction = shooter.get(Faction)
    target_faction = target.get(Faction)
    return (
        shooter_faction is None
        or target_faction is None
        or shooter_faction.key != target_faction.key
    )


def _standard_enemy_drop(runtime: GameRuntime, enemy: Entity, position: Vec3) -> None:
    inventory = enemy.require(Inventory)
    equipment = enemy.require(Equipment)
    roll = runtime.randomizer.randrange(3)
    if roll == 0 and equipment.equipped_item_id is not None:
        weapon_id = equipment.equipped_item_id
        weapon = runtime.entities.require(weapon_id)
        if weapon_id in inventory.item_ids:
            inventory.item_ids.remove(weapon_id)
        equipment.equipped_item_id = None
        place_item_as_pickup(weapon, position)
        runtime.add_message(f"Enemy defeated. Dropped {weapon.def_key.replace('_', ' ').title()}.")
        return
    drop_key = "health_up" if roll == 1 else "food"
    spawn_item(runtime.entities, drop_key, position)
    label = "Health Up" if drop_key == "health_up" else "Food"
    runtime.add_message(f"Enemy defeated. Dropped {label}.")


DROP_POOLS.register("standard_enemy", _standard_enemy_drop)


def _remove_owned_items(runtime: GameRuntime, entity: Entity) -> None:
    inventory = entity.get(Inventory)
    if inventory is not None:
        runtime.entities.remove_many(inventory.item_ids)


def apply_damage(
    runtime: GameRuntime,
    target: Entity,
    raw_damage: int,
    source: Entity | None,
) -> int:
    armor = target.get(Armor)
    damage = max(1, raw_damage - (armor.value if armor is not None else 0))
    health = target.require(Health)
    health.current = max(0, health.current - damage)
    target_faction = target.get(Faction)
    if target_faction is not None and target_faction.key == "player":
        runtime.add_message(f"You were hit for {damage}.")
    if health.current > 0:
        return damage

    if target_faction is not None and target_faction.key == "player":
        runtime.add_message("You died. Press R to respawn; the world will persist.")
        return damage

    if source is not None:
        xp = source.get(Xp)
        if xp is not None:
            xp.points += 25
    drops = target.get(Drops)
    position = target.require(Transform).position
    if drops is not None:
        DROP_POOLS.lookup(drops.pool)(runtime, target, position)
    _remove_owned_items(runtime, target)
    runtime.entities.remove(target.id)
    return damage


def _fire_melee(
    runtime: GameRuntime,
    shooter: Entity,
    weapon: Weapon,
    origin: Vec3,
    direction: Vec3,
) -> ShotResult:
    candidates = []
    for target in runtime.entities.query(Transform, Collider, Health):
        if not _is_opposing_target(shooter, target):
            continue
        target_origin = entity_eye_origin(target)
        delta = target_origin - origin
        distance = delta.length()
        if distance <= 0 or distance > weapon.max_distance:
            continue
        target_direction = delta / distance
        dot = (
            direction.x * target_direction.x
            + direction.y * target_direction.y
            + direction.z * target_direction.z
        )
        if dot < 0.25:
            continue
        obstruction = raycast(
            runtime.world,
            runtime.entities,
            origin,
            target_direction,
            distance,
            predicate=lambda entity, target_id=target.id: entity.id == target_id,
            excluded_entity_ids={shooter.id},
        )
        if obstruction is not None and obstruction.entity_id == target.id:
            candidates.append((distance, target, obstruction.point))
    if not candidates:
        return ShotResult(True, origin, origin + direction * weapon.max_distance, "miss")
    _distance, target, hit_point = min(candidates, key=lambda candidate: candidate[0])
    apply_damage(runtime, target, weapon.damage, shooter)
    return ShotResult(True, origin, hit_point, "entity", target.id)


def fire_entity_weapon(
    runtime: GameRuntime,
    shooter: Entity,
    weapon_entity: Entity,
    direction: Vec3,
) -> ShotResult:
    weapon = weapon_entity.get(Weapon)
    if weapon is None or weapon.seconds_until_ready > 0 or shooter.require(Health).current <= 0:
        return ShotResult(False)
    direction = normalized_direction(direction)
    weapon.seconds_until_ready = weapon.cooldown_seconds
    origin = entity_eye_origin(shooter)
    if weapon.attack_style == "melee":
        return _fire_melee(runtime, shooter, weapon, origin, direction)
    hit = raycast(
        runtime.world,
        runtime.entities,
        origin,
        direction,
        weapon.max_distance,
        predicate=lambda entity: _is_opposing_target(shooter, entity),
        excluded_entity_ids={shooter.id},
    )
    if hit is None:
        return ShotResult(True, origin, origin + direction * weapon.max_distance, "miss")
    if hit.entity_id is None:
        return ShotResult(True, origin, hit.point, "block")
    target = runtime.entities.require(hit.entity_id)
    apply_damage(runtime, target, weapon.damage, shooter)
    return ShotResult(True, origin, hit.point, "entity", hit.entity_id)


def fire_hitscan(runtime: GameRuntime, session_id: str, direction: Vec3) -> ShotResult:
    session = runtime.require_session(session_id)
    player = runtime.entities.require(session.player_entity_id)
    equipped_id = player.require(Equipment).equipped_item_id
    if equipped_id is None:
        return ShotResult(False)
    return fire_entity_weapon(
        runtime,
        player,
        runtime.entities.require(equipped_id),
        direction,
    )


def _has_line_of_sight(runtime: GameRuntime, shooter: Entity, target: Entity, max_distance: float) -> bool:
    origin = entity_eye_origin(shooter)
    destination = entity_eye_origin(target)
    delta = destination - origin
    distance = delta.length()
    if distance <= 0 or distance > max_distance:
        return False
    hit = raycast(
        runtime.world,
        runtime.entities,
        origin,
        delta / distance,
        distance,
        predicate=lambda entity: entity.id == target.id,
        excluded_entity_ids={shooter.id},
    )
    return hit is not None and hit.entity_id == target.id


def fire_hostile_weapon(runtime: GameRuntime, shooter: Entity, target: Entity) -> ShotResult:
    equipped_id = shooter.require(Equipment).equipped_item_id
    if equipped_id is None:
        return ShotResult(False)
    weapon_entity = runtime.entities.require(equipped_id)
    weapon = weapon_entity.require(Weapon)
    if not _has_line_of_sight(runtime, shooter, target, weapon.max_distance):
        return ShotResult(False)
    origin = entity_eye_origin(shooter)
    destination = entity_eye_origin(target)
    base = normalized_direction(destination - origin)
    if weapon.attack_style == "melee":
        direction = base
    else:
        yaw = math.atan2(-base.x, -base.z) + runtime.randomizer.uniform(-0.18, 0.18)
        pitch = math.asin(max(-1.0, min(1.0, base.y))) + runtime.randomizer.uniform(-0.18, 0.18)
        cos_pitch = math.cos(pitch)
        direction = Vec3(-math.sin(yaw) * cos_pitch, math.sin(pitch), -math.cos(yaw) * cos_pitch)
    result = fire_entity_weapon(runtime, shooter, weapon_entity, direction)
    if result.fired:
        weapon.seconds_until_ready = runtime.randomizer.uniform(0.85, 1.3)
    return result
