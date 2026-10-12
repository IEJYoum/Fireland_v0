"""World/session ownership and the fixed ordered simulation pipeline."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .components import (
    AlwaysActive,
    Armor,
    Collider,
    ControlVelocity,
    ControlledBy,
    Drops,
    Equipment,
    Faction,
    Gravity,
    Grounded,
    Health,
    HostileAI,
    Hunger,
    Inventory,
    Renderable,
    Think,
    Transform,
    Velocity,
    Weapon,
    Xp,
)
from .entities import EntityDefinition, EntityStore
from .items import create_item, spawn_item
from .physics import JUMP_SPEED, PLAYER_MOVE_SPEED, set_control_velocity, step_physics
from .registry import BehaviorRegistry
from .vectors import Aabb, Vec3, ZERO_VEC3
from .world3d import (
    CHUNK_SIZE_X,
    CHUNK_SIZE_Z,
    PLAYER_SPAWN,
    ChunkKey,
    World,
    create_procedural_world,
    stable_coordinate_seed,
)


FIXED_STEP_SECONDS = 1 / 60
MAX_FRAME_SECONDS = 0.25
MAX_PITCH = math.pi / 2 - 0.01
ACTIVE_RADIUS_CHUNKS = 4
GENERATION_RADIUS_CHUNKS = 5
CLIENT_STREAM_RADIUS_CHUNKS = 4
ENEMY_MOVE_SPEED = 2.2
HUNGER_LOSS_PER_SECOND = 0.5
THINK_ROUTINES = BehaviorRegistry("think")


PLAYER_DEFINITION = EntityDefinition(
    "player",
    (
        Transform(PLAYER_SPAWN),
        Velocity(),
        ControlVelocity(),
        Collider(Aabb(half_x=0.3, height=1.8, half_z=0.3)),
        Gravity(),
        Grounded(),
        Health(100, 100),
        Hunger(),
        Armor(),
        Xp(),
        Faction("player"),
        Inventory(),
        Equipment(),
        ControlledBy("unassigned"),
        Renderable("player"),
    ),
)

ENEMY_DEFINITION = EntityDefinition(
    "test_enemy",
    (
        Transform(Vec3(0.5, 0.0, 0.5)),
        Velocity(),
        ControlVelocity(),
        Collider(Aabb(half_x=0.35, height=1.7, half_z=0.35)),
        Gravity(),
        Grounded(),
        Health(60, 60),
        Armor(),
        Faction("hostile"),
        Inventory(),
        Equipment(),
        Drops("standard_enemy"),
        HostileAI(),
        Think("hostile"),
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
    survival_seconds: float = 0.0

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
    active_chunk_keys: set[ChunkKey] = field(default_factory=set)
    materialized_spawn_keys: set[str] = field(default_factory=set)
    messages: list[str] = field(default_factory=list)
    randomizer: random.Random = field(default_factory=random.Random)

    def require_session(self, session_id: str) -> Session:
        try:
            return self.sessions[session_id]
        except KeyError as error:
            raise KeyError(f"Unknown session {session_id!r}.") from error

    def add_message(self, message: str) -> None:
        self.messages.append(message)
        del self.messages[:-4]


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


def _hostile_think(runtime: GameRuntime, entity, dt: float) -> None:
    transform = entity.require(Transform)
    targets = [
        runtime.entities.require(session.player_entity_id)
        for session in runtime.sessions.values()
        if runtime.entities.require(session.player_entity_id).require(Health).current > 0
    ]
    if not targets:
        set_control_velocity(entity, Vec3(0.0, 0.0, 0.0))
        return
    target_entity = min(
        targets,
        key=lambda target: (target.require(Transform).position.x - transform.position.x) ** 2
        + (target.require(Transform).position.z - transform.position.z) ** 2,
    )
    target = target_entity.require(Transform).position
    hostile = entity.require(HostileAI)
    hostile.seconds_until_mode_roll -= dt
    if hostile.seconds_until_mode_roll <= 0:
        hostile.seconds_until_mode_roll += 1.0
        if runtime.randomizer.random() < 0.33:
            hostile.mode = "evade"
            angle = runtime.randomizer.uniform(0, math.tau)
            distance = runtime.randomizer.uniform(3.0, 6.0)
            hostile.evade_target = Vec3(
                transform.position.x + math.cos(angle) * distance,
                transform.position.y,
                transform.position.z + math.sin(angle) * distance,
            )
        else:
            hostile.mode = "chase"
            hostile.evade_target = None

    delta_x = target.x - transform.position.x
    delta_z = target.z - transform.position.z
    distance = math.hypot(delta_x, delta_z)
    equipment = entity.require(Equipment)
    weapon = (
        runtime.entities.require(equipment.equipped_item_id).get(Weapon)
        if equipment.equipped_item_id is not None
        else None
    )
    preferred_distance = 1.0
    if weapon is not None:
        preferred_distance = (
            weapon.max_distance * 0.75
            if weapon.attack_style == "melee"
            else min(10.0, max(4.0, weapon.max_distance * 0.5))
        )

    movement_target = hostile.evade_target if hostile.mode == "evade" else target
    move_x = movement_target.x - transform.position.x
    move_z = movement_target.z - transform.position.z
    move_distance = math.hypot(move_x, move_z)
    should_move = hostile.mode == "evade" and move_distance > 0.2
    should_move = should_move or (hostile.mode != "evade" and distance > preferred_distance)
    if not should_move or move_distance == 0:
        set_control_velocity(entity, Vec3(0.0, 0.0, 0.0))
    else:
        set_control_velocity(
            entity,
            Vec3(
                move_x / move_distance * ENEMY_MOVE_SPEED,
                0.0,
                move_z / move_distance * ENEMY_MOVE_SPEED,
            ),
        )

    if weapon is not None and distance <= weapon.max_distance and weapon.seconds_until_ready <= 0:
        from .combat3d import fire_hostile_weapon

        fire_hostile_weapon(runtime, entity, target_entity)


THINK_ROUTINES.register("hostile", _hostile_think)


def create_runtime(session_id: str = "local", *, seed: int = 7) -> GameRuntime:
    entities = EntityStore()
    player = create_player_entity(entities, session_id)
    world = create_procedural_world(seed=seed, generator_key="overworld")
    runtime = GameRuntime(
        world_id="development-world",
        world=world,
        entities=entities,
        sessions={session_id: Session(session_id, player.id)},
        randomizer=random.Random(stable_coordinate_seed(world.seed, 0, 0, salt=0x6A4E)),
    )
    refresh_active_chunks(runtime)
    materialize_active_chunk_spawns(runtime)
    runtime.add_message("Find the pistol, open the door, and survive.")
    return runtime


def create_player_entity(
    entities: EntityStore,
    session_id: str,
    *,
    with_starting_kit: bool = False,
):
    player = entities.create(
        PLAYER_DEFINITION,
        (
            Transform(PLAYER_SPAWN),
            ControlledBy(session_id),
        ),
    )
    if with_starting_kit:
        starting_pistol = create_item(entities, "pistol")
        player.require(Inventory).item_ids.append(starting_pistol.id)
        player.require(Equipment).equipped_item_id = starting_pistol.id
    return player


def create_enemy_entity(
    runtime: GameRuntime,
    position: Vec3,
    weapon_key: str,
):
    enemy = runtime.entities.create(ENEMY_DEFINITION, (Transform(position),))
    weapon = create_item(runtime.entities, weapon_key)
    enemy.require(Inventory).item_ids.append(weapon.id)
    enemy.require(Equipment).equipped_item_id = weapon.id
    return enemy


def materialize_active_chunk_spawns(runtime: GameRuntime) -> None:
    for chunk_x, chunk_z in sorted(runtime.active_chunk_keys):
        chunk = runtime.world.require_chunk((chunk_x, chunk_z))
        for descriptor in chunk.spawn_descriptors:
            spawn_key = f"{chunk_x}:{chunk_z}:{descriptor.key}"
            if spawn_key in runtime.materialized_spawn_keys:
                continue
            local = descriptor.local_position
            position = Vec3(
                chunk_x * CHUNK_SIZE_X + local.x,
                local.y,
                chunk_z * CHUNK_SIZE_Z + local.z,
            )
            if descriptor.kind == "pickup":
                spawn_item(runtime.entities, descriptor.content_key, position)
            elif descriptor.kind == "enemy":
                create_enemy_entity(runtime, position, descriptor.content_key)
            else:
                raise KeyError(f"Unknown chunk spawn kind {descriptor.kind!r}.")
            runtime.materialized_spawn_keys.add(spawn_key)


def respawn_player(runtime: GameRuntime, session_id: str) -> int:
    session = runtime.require_session(session_id)
    old_player = runtime.entities.require(session.player_entity_id)
    inventory = old_player.get(Inventory)
    if inventory is not None:
        runtime.entities.remove_many(inventory.item_ids)
    runtime.entities.remove(old_player.id)
    new_player = create_player_entity(runtime.entities, session_id, with_starting_kit=True)
    session.player_entity_id = new_player.id
    session.command = InputCommand()
    session.survival_seconds = 0.0
    runtime.add_message("Respawned with a pistol; the world was not reset.")
    return new_player.id


def chunk_keys_near_positions(positions: list[Vec3], radius_chunks: int) -> set[ChunkKey]:
    keys: set[ChunkKey] = set()
    for position in positions:
        center_x = math.floor(position.x / CHUNK_SIZE_X)
        center_z = math.floor(position.z / CHUNK_SIZE_Z)
        keys.update(
            (center_x + offset_x, center_z + offset_z)
            for offset_x in range(-radius_chunks, radius_chunks + 1)
            for offset_z in range(-radius_chunks, radius_chunks + 1)
        )
    return keys


def spatial_entity_ids_in_chunks(
    runtime: GameRuntime,
    chunk_keys: set[ChunkKey],
) -> set[int]:
    return {
        entity.id
        for entity in runtime.entities.query(Transform)
        if (
            math.floor(entity.require(Transform).position.x / CHUNK_SIZE_X),
            math.floor(entity.require(Transform).position.z / CHUNK_SIZE_Z),
        )
        in chunk_keys
    }


def include_inventory_items(runtime: GameRuntime, entity_ids: set[int]) -> set[int]:
    included = set(entity_ids)
    pending = list(entity_ids)
    while pending:
        entity = runtime.entities.get(pending.pop())
        if entity is None:
            continue
        inventory = entity.get(Inventory)
        if inventory is None:
            continue
        for item_id in inventory.item_ids:
            if item_id not in included:
                included.add(item_id)
                pending.append(item_id)
    return included


def refresh_active_chunks(runtime: GameRuntime) -> None:
    player_positions = [
        runtime.entities.require(session.player_entity_id).require(Transform).position
        for session in runtime.sessions.values()
    ]
    generation_keys = chunk_keys_near_positions(player_positions, GENERATION_RADIUS_CHUNKS)
    for chunk_key in generation_keys:
        runtime.world.ensure_chunk(chunk_key)
    runtime.active_chunk_keys = chunk_keys_near_positions(player_positions, ACTIVE_RADIUS_CHUNKS)


def streamed_chunk_keys_for_session(runtime: GameRuntime, session_id: str) -> set[ChunkKey]:
    session = runtime.require_session(session_id)
    position = runtime.entities.require(session.player_entity_id).require(Transform).position
    return chunk_keys_near_positions([position], CLIENT_STREAM_RADIUS_CHUNKS)


def simulated_entity_ids(runtime: GameRuntime) -> set[int]:
    simulated_ids = {entity.id for entity in runtime.entities.query(AlwaysActive)}
    for session in runtime.sessions.values():
        simulated_ids.add(session.player_entity_id)

    simulated_ids.update(spatial_entity_ids_in_chunks(runtime, runtime.active_chunk_keys))
    return include_inventory_items(runtime, simulated_ids)


def visible_entity_ids_for_session(runtime: GameRuntime, session_id: str) -> set[int]:
    """Narrow the simulated union to one session without duplicating its rule."""

    simulated_ids = simulated_entity_ids(runtime)
    session = runtime.require_session(session_id)
    player = runtime.entities.require(session.player_entity_id)
    visible_ids = {player.id}
    visible_ids.update(
        spatial_entity_ids_in_chunks(runtime, streamed_chunk_keys_for_session(runtime, session_id))
    )
    visible_ids.update(entity.id for entity in runtime.entities.query(AlwaysActive))
    return include_inventory_items(runtime, visible_ids) & simulated_ids


def apply_session_commands(runtime: GameRuntime) -> None:
    for session in runtime.sessions.values():
        player = runtime.entities.require(session.player_entity_id)
        transform = player.require(Transform)
        velocity = player.require(Velocity)
        grounded = player.require(Grounded)
        command = session.command

        if player.require(Health).current <= 0:
            set_control_velocity(player, ZERO_VEC3)
            command.jump_requested = False
            continue

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
        set_control_velocity(
            player,
            Vec3(
                movement.x * PLAYER_MOVE_SPEED,
                0.0,
                movement.z * PLAYER_MOVE_SPEED,
            ),
        )
        if command.jump_requested and grounded.value:
            velocity.value = Vec3(velocity.value.x, JUMP_SPEED, velocity.value.z)
            grounded.value = False
        command.jump_requested = False


def step_runtime(runtime: GameRuntime, dt: float = FIXED_STEP_SECONDS) -> None:
    refresh_active_chunks(runtime)
    materialize_active_chunk_spawns(runtime)
    apply_session_commands(runtime)
    simulated_ids = simulated_entity_ids(runtime)
    step_physics(runtime.entities, runtime.world, dt, simulated_ids)
    step_weapon_cooldowns(runtime, dt, simulated_ids)
    step_player_vitals(runtime, dt)
    step_think(runtime, dt, simulated_ids)
    # Projectiles are transient and few; step them all so none freeze mid-flight
    # outside the active region and leak.
    from .combat3d import step_projectiles

    step_projectiles(runtime, dt)
    refresh_active_chunks(runtime)
    materialize_active_chunk_spawns(runtime)
    runtime.server_tick += 1


def step_player_vitals(runtime: GameRuntime, dt: float) -> None:
    for session in runtime.sessions.values():
        player = runtime.entities.require(session.player_entity_id)
        if player.require(Health).current <= 0:
            continue
        hunger = player.require(Hunger)
        hunger.current = max(0.0, hunger.current - HUNGER_LOSS_PER_SECOND * dt)
        session.survival_seconds += dt


def step_weapon_cooldowns(runtime: GameRuntime, dt: float, simulated_ids: set[int]) -> None:
    for entity in runtime.entities.query(Weapon):
        if entity.id not in simulated_ids:
            continue
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
        if think.seconds_until_tick <= 0:
            THINK_ROUTINES.lookup(think.routine)(runtime, entity, interval)
            think.seconds_until_tick = interval


def stop_session_movement(runtime: GameRuntime, session_id: str) -> None:
    session = runtime.require_session(session_id)
    session.command.forward = 0.0
    session.command.strafe = 0.0
    player = runtime.entities.require(session.player_entity_id)
    set_control_velocity(player, Vec3(0.0, 0.0, 0.0))
