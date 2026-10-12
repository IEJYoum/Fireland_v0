"""World/session ownership and the fixed ordered simulation pipeline."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .components import (
    Collider,
    ControlledBy,
    Equipment,
    Gravity,
    Grounded,
    Health,
    Inventory,
    Renderable,
    Pickup,
    Think,
    Transform,
    Velocity,
    Weapon,
)
from .entities import EntityDefinition, EntityStore
from .physics import JUMP_SPEED, PLAYER_MOVE_SPEED, step_physics
from .registry import BehaviorRegistry
from .vectors import Aabb, Vec3, ZERO_VEC3
from .world3d import ENEMY_SPAWN, PICKUP_SPAWN, PLAYER_SPAWN, World, create_test_arena


FIXED_STEP_SECONDS = 1 / 60
MAX_FRAME_SECONDS = 0.25
MAX_PITCH = math.pi / 2 - 0.01
ACTIVE_RADIUS = 64.0
THINK_ROUTINES = BehaviorRegistry("think")


PLAYER_DEFINITION = EntityDefinition(
    "player",
    (
        Transform(PLAYER_SPAWN),
        Velocity(),
        Collider(Aabb(half_x=0.3, height=1.8, half_z=0.3)),
        Gravity(),
        Grounded(),
        Health(100, 100),
        Inventory(),
        Equipment(),
        ControlledBy("unassigned"),
        Renderable("player"),
    ),
)

PISTOL_DEFINITION = EntityDefinition(
    "pistol",
    (
        Collider(Aabb(half_x=0.18, height=0.28, half_z=0.18)),
        Renderable("pistol"),
        Weapon(damage=25, max_distance=28.0, cooldown_seconds=0.3),
    ),
)

ENEMY_DEFINITION = EntityDefinition(
    "test_enemy",
    (
        Transform(ENEMY_SPAWN),
        Collider(Aabb(half_x=0.35, height=1.7, half_z=0.35)),
        Health(75, 75),
        Think("idle"),
        Renderable("enemy"),
    ),
)


@dataclass
class InputCommand:
    sequence: int = -1
    forward: float = 0.0
    strafe: float = 0.0
    yaw: float = 0.0
    pitch: float = 0.0
    jump_requested: bool = False


@dataclass
class Session:
    id: str
    player_entity_id: int
    command: InputCommand = field(default_factory=InputCommand)

    def apply_input(
        self,
        *,
        sequence: int,
        forward: float,
        strafe: float,
        yaw: float,
        pitch: float,
        jump: bool,
    ) -> bool:
        if sequence <= self.command.sequence:
            return False
        values = (forward, strafe, yaw, pitch)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Input values must be finite.")
        self.command.sequence = sequence
        self.command.forward = max(-1.0, min(1.0, forward))
        self.command.strafe = max(-1.0, min(1.0, strafe))
        self.command.yaw = yaw
        self.command.pitch = max(-MAX_PITCH, min(MAX_PITCH, pitch))
        # Preserve a jump edge if another newer movement packet arrives before the
        # simulation consumes it.
        self.command.jump_requested = self.command.jump_requested or jump
        return True


@dataclass
class GameRuntime:
    world_id: str
    world: World
    entities: EntityStore
    sessions: dict[str, Session]
    server_tick: int = 0

    def require_session(self, session_id: str) -> Session:
        try:
            return self.sessions[session_id]
        except KeyError as error:
            raise KeyError(f"Unknown session {session_id!r}.") from error


@dataclass
class FixedStepClock:
    step_seconds: float = FIXED_STEP_SECONDS
    max_frame_seconds: float = MAX_FRAME_SECONDS
    accumulator: float = 0.0

    def advance(self, elapsed_seconds: float, update) -> int:
        self.accumulator += max(0.0, min(elapsed_seconds, self.max_frame_seconds))
        step_count = 0
        while self.accumulator + 1e-12 >= self.step_seconds:
            update(self.step_seconds)
            self.accumulator -= self.step_seconds
            step_count += 1
        return step_count


def _idle_think(runtime: GameRuntime, entity, dt: float) -> None:
    """Intentional no-op used by the graybox target."""


THINK_ROUTINES.register("idle", _idle_think)


def create_runtime(session_id: str = "local") -> GameRuntime:
    entities = EntityStore()
    player = create_player_entity(entities, session_id)
    runtime = GameRuntime(
        world_id="development-world",
        world=create_test_arena(),
        entities=entities,
        sessions={session_id: Session(session_id, player.id)},
    )
    runtime.entities.create(ENEMY_DEFINITION, (Transform(ENEMY_SPAWN),))
    runtime.entities.create(
        PISTOL_DEFINITION,
        (
            Transform(PICKUP_SPAWN),
            Pickup("interact"),
        ),
    )
    return runtime


def create_player_entity(entities: EntityStore, session_id: str):
    player = entities.create(
        PLAYER_DEFINITION,
        (
            Transform(PLAYER_SPAWN),
            ControlledBy(session_id),
        ),
    )
    starting_pistol = entities.create(PISTOL_DEFINITION)
    player.require(Inventory).item_ids.append(starting_pistol.id)
    player.require(Equipment).equipped_item_id = starting_pistol.id
    return player


def respawn_player(runtime: GameRuntime, session_id: str) -> int:
    session = runtime.require_session(session_id)
    old_player = runtime.entities.require(session.player_entity_id)
    inventory = old_player.get(Inventory)
    if inventory is not None:
        runtime.entities.remove_many(inventory.item_ids)
    runtime.entities.remove(old_player.id)
    new_player = create_player_entity(runtime.entities, session_id)
    session.player_entity_id = new_player.id
    session.command = InputCommand()
    return new_player.id


def active_entity_ids(runtime: GameRuntime) -> set[int]:
    player_positions = []
    active_ids = set()
    for session in runtime.sessions.values():
        player = runtime.entities.require(session.player_entity_id)
        active_ids.add(player.id)
        player_positions.append(player.require(Transform).position)
        inventory = player.get(Inventory)
        if inventory is not None:
            active_ids.update(inventory.item_ids)

    radius_squared = ACTIVE_RADIUS * ACTIVE_RADIUS
    for entity in runtime.entities.query(Transform):
        position = entity.require(Transform).position
        if any(
            (position.x - player_position.x) ** 2 + (position.z - player_position.z) ** 2
            <= radius_squared
            for player_position in player_positions
        ):
            active_ids.add(entity.id)
    return active_ids


def apply_session_commands(runtime: GameRuntime) -> None:
    for session in runtime.sessions.values():
        player = runtime.entities.require(session.player_entity_id)
        transform = player.require(Transform)
        velocity = player.require(Velocity)
        grounded = player.require(Grounded)
        command = session.command

        transform.yaw = command.yaw
        transform.pitch = command.pitch
        # Match Three.js's YXZ camera convention: yaw 0 looks toward -Z and
        # positive yaw turns the view toward -X.
        forward_vector = Vec3(-math.sin(command.yaw), 0.0, -math.cos(command.yaw))
        right_vector = Vec3(math.cos(command.yaw), 0.0, -math.sin(command.yaw))
        movement = forward_vector * command.forward + right_vector * command.strafe
        horizontal_length = math.hypot(movement.x, movement.z)
        if horizontal_length > 1:
            movement = Vec3(movement.x / horizontal_length, 0.0, movement.z / horizontal_length)
        velocity.value = Vec3(
            movement.x * PLAYER_MOVE_SPEED,
            velocity.value.y,
            movement.z * PLAYER_MOVE_SPEED,
        )
        if command.jump_requested and grounded.value:
            velocity.value = Vec3(velocity.value.x, JUMP_SPEED, velocity.value.z)
            grounded.value = False
        command.jump_requested = False


def step_runtime(runtime: GameRuntime, dt: float = FIXED_STEP_SECONDS) -> None:
    apply_session_commands(runtime)
    active_ids = active_entity_ids(runtime)
    step_physics(runtime.entities, runtime.world, dt, active_ids)
    step_weapon_cooldowns(runtime, dt)
    step_think(runtime, dt, active_ids)
    runtime.server_tick += 1


def step_weapon_cooldowns(runtime: GameRuntime, dt: float) -> None:
    for entity in runtime.entities.query(Weapon):
        weapon = entity.require(Weapon)
        weapon.seconds_until_ready = max(0.0, weapon.seconds_until_ready - dt)


def step_think(runtime: GameRuntime, dt: float, active_ids: set[int]) -> None:
    for entity in runtime.entities.query(Think):
        if entity.id not in active_ids:
            continue
        think = entity.require(Think)
        if think.cadence_hz <= 0:
            raise ValueError(f"Entity {entity.id} has a non-positive think cadence.")
        think.seconds_until_tick -= dt
        interval = 1 / think.cadence_hz
        while think.seconds_until_tick <= 0:
            THINK_ROUTINES.lookup(think.routine)(runtime, entity, interval)
            think.seconds_until_tick += interval


def stop_session_movement(runtime: GameRuntime, session_id: str) -> None:
    session = runtime.require_session(session_id)
    session.command.forward = 0.0
    session.command.strafe = 0.0
    player = runtime.entities.require(session.player_entity_id)
    velocity = player.require(Velocity)
    velocity.value = Vec3(0.0, velocity.value.y, 0.0)
