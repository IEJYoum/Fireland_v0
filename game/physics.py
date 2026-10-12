"""Fixed-step AABB physics against the block world."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .components import Collider, ControlVelocity, Gravity, Grounded, Transform, Velocity
from .entities import Entity, EntityStore
from .vectors import Aabb, Vec3
from .world3d import World


GRAVITY = -24.0
JUMP_SPEED = 8.5
PLAYER_MOVE_SPEED = 5.5
MAX_FALL_SPEED = -40.0
MAX_MOVEMENT_SUBSTEP = 0.25
RESIDUAL_HORIZONTAL_DRAG = 6.0
RESIDUAL_STOP_SPEED = 0.001
_COLLISION_EPSILON = 1e-7


@dataclass(frozen=True)
class CollisionResult:
    position: Vec3
    collided_x: bool = False
    collided_y: bool = False
    collided_z: bool = False
    grounded: bool = False


def aabb_collides_with_world(world: World, position: Vec3, box: Aabb) -> bool:
    min_x, min_y, min_z, max_x, max_y, max_z = box.bounds_at(position)
    first_x = math.floor(min_x + _COLLISION_EPSILON)
    last_x = math.floor(max_x - _COLLISION_EPSILON)
    first_y = math.floor(min_y + _COLLISION_EPSILON)
    last_y = math.floor(max_y - _COLLISION_EPSILON)
    first_z = math.floor(min_z + _COLLISION_EPSILON)
    last_z = math.floor(max_z - _COLLISION_EPSILON)
    return any(
        world.is_solid(x, y, z)
        for x in range(first_x, last_x + 1)
        for y in range(first_y, last_y + 1)
        for z in range(first_z, last_z + 1)
    )


def _with_axis(position: Vec3, axis: str, value: float) -> Vec3:
    if axis == "x":
        return Vec3(value, position.y, position.z)
    if axis == "y":
        return Vec3(position.x, value, position.z)
    return Vec3(position.x, position.y, value)


def _axis_value(position: Vec3, axis: str) -> float:
    return getattr(position, axis)


def _move_axis(world: World, position: Vec3, box: Aabb, axis: str, amount: float) -> tuple[Vec3, bool]:
    if amount == 0:
        return position, False
    start_value = _axis_value(position, axis)
    candidate = _with_axis(position, axis, start_value + amount)
    if not aabb_collides_with_world(world, candidate, box):
        return candidate, False

    # Find the contact point rather than rejecting the whole substep. This keeps
    # grounded entities flush with block faces and avoids speed-dependent gaps.
    safe_fraction = 0.0
    blocked_fraction = 1.0
    for _ in range(24):
        fraction = (safe_fraction + blocked_fraction) / 2
        probe = _with_axis(position, axis, start_value + amount * fraction)
        if aabb_collides_with_world(world, probe, box):
            blocked_fraction = fraction
        else:
            safe_fraction = fraction
    return _with_axis(position, axis, start_value + amount * safe_fraction), True


def move_aabb(world: World, position: Vec3, box: Aabb, displacement: Vec3) -> CollisionResult:
    largest_axis = max(abs(displacement.x), abs(displacement.y), abs(displacement.z))
    substep_count = max(1, math.ceil(largest_axis / MAX_MOVEMENT_SUBSTEP))
    step = displacement / substep_count
    collided_x = collided_y = collided_z = grounded = False

    for _ in range(substep_count):
        position, hit_x = _move_axis(world, position, box, "x", step.x)
        position, hit_z = _move_axis(world, position, box, "z", step.z)
        position, hit_y = _move_axis(world, position, box, "y", step.y)
        collided_x = collided_x or hit_x
        collided_z = collided_z or hit_z
        collided_y = collided_y or hit_y
        grounded = grounded or (hit_y and step.y < 0)

    return CollisionResult(position, collided_x, collided_y, collided_z, grounded)


def set_control_velocity(entity: Entity, value: Vec3) -> None:
    """Set horizontal desired motion without disturbing external momentum."""

    control = entity.require(ControlVelocity)
    control.value = Vec3(value.x, 0.0, value.z)


def apply_impulse(entity: Entity, impulse: Vec3) -> None:
    """Add persistent ballistic/residual velocity to a movable entity."""

    if not impulse.is_finite():
        raise ValueError("Impulse must be finite.")
    velocity = entity.require(Velocity)
    velocity.value = velocity.value + impulse


def step_physics(
    entities: EntityStore,
    world: World,
    dt: float,
    active_entity_ids: set[int] | None = None,
) -> None:
    if dt <= 0:
        return

    for entity in entities.query(Transform, Velocity, Gravity):
        if active_entity_ids is not None and entity.id not in active_entity_ids:
            continue
        velocity = entity.require(Velocity)
        velocity.value = Vec3(
            velocity.value.x,
            max(MAX_FALL_SPEED, velocity.value.y + GRAVITY * dt),
            velocity.value.z,
        )

    for entity in entities.query(Transform, Velocity, Collider):
        if active_entity_ids is not None and entity.id not in active_entity_ids:
            continue
        transform = entity.require(Transform)
        velocity = entity.require(Velocity)
        collider = entity.require(Collider)
        control = entity.get(ControlVelocity)
        control_value = control.value if control is not None else Vec3(0.0, 0.0, 0.0)
        result = move_aabb(
            world,
            transform.position,
            collider.box,
            (velocity.value + control_value) * dt,
        )
        transform.position = result.position
        residual_x = 0.0 if result.collided_x else velocity.value.x
        residual_z = 0.0 if result.collided_z else velocity.value.z
        decay = math.exp(-RESIDUAL_HORIZONTAL_DRAG * dt)
        residual_x *= decay
        residual_z *= decay
        if abs(residual_x) < RESIDUAL_STOP_SPEED:
            residual_x = 0.0
        if abs(residual_z) < RESIDUAL_STOP_SPEED:
            residual_z = 0.0
        velocity.value = Vec3(
            residual_x,
            0.0 if result.collided_y else velocity.value.y,
            residual_z,
        )
        grounded = entity.get(Grounded)
        if grounded is not None:
            grounded.value = result.grounded
