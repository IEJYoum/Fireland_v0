import math
from dataclasses import dataclass

import pytest

from game.actions3d import apply_action
from game.components import AlwaysActive, Collider, Gravity, Grounded, Inventory, Think, Transform, Velocity, Weapon
from game.entities import EntityDefinition
from game.runtime import (
    ACTIVE_RADIUS_CHUNKS,
    GENERATION_RADIUS_CHUNKS,
    create_runtime,
    step_runtime,
)
from game.vectors import Aabb, Vec3
from game.wire import snapshot_for_session
from game.world3d import World


@dataclass
class Counter:
    ticks: int = 0


FALLING_ACTOR = EntityDefinition(
    "falling_actor",
    (
        Transform(Vec3(0, 0, 0)),
        Velocity(),
        Collider(Aabb(0.3, 1.0, 0.3)),
        Gravity(),
        Grounded(),
    ),
)


def test_respawn_replaces_player_but_preserves_world_and_other_entities():
    runtime = create_runtime()
    session = runtime.require_session("local")
    old_player = runtime.entities.require(session.player_entity_id)
    old_item_ids = list(old_player.require(Inventory).item_ids)
    world = runtime.world
    enemy_id = next(entity.id for entity in runtime.entities.entities.values() if entity.def_key == "test_enemy")
    runtime.world.set_block(4, 0, 4, "wood")

    assert apply_action(runtime, "local", {"type": "restart"}) is True

    new_player = runtime.entities.require(session.player_entity_id)
    assert new_player.id != old_player.id
    assert runtime.entities.get(old_player.id) is None
    assert all(runtime.entities.get(item_id) is None for item_id in old_item_ids)
    assert runtime.entities.get(enemy_id) is not None
    assert runtime.world is world
    assert runtime.world.get_block(4, 0, 4) == "wood"
    assert len(new_player.require(Inventory).item_ids) == 1


def test_distant_entities_do_not_run_spatial_physics_until_active():
    runtime = create_runtime()
    distant = runtime.entities.create(FALLING_ACTOR, (Transform(Vec3(1000, 10, 1000)),))

    step_runtime(runtime)
    assert distant.require(Transform).position.y == 10

    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    player.require(Transform).position = Vec3(1000, 10, 1000)
    step_runtime(runtime)
    assert distant.require(Transform).position.y < 10


def test_session_snapshot_excludes_distant_entities_and_chunks():
    runtime = create_runtime()
    distant = runtime.entities.create(FALLING_ACTOR, (Transform(Vec3(1000, 10, 1000)),))
    runtime.world.set_block(1000, 0, 1000, "stone")

    snapshot = snapshot_for_session(runtime, "local")

    assert distant.id not in {entity["id"] for entity in snapshot["entities"]}
    assert (62, 62) not in {(chunk["x"], chunk["z"]) for chunk in snapshot["chunks"]}


def test_unknown_think_key_fails_when_the_system_uses_it():
    runtime = create_runtime()
    enemy = next(entity for entity in runtime.entities.entities.values() if entity.def_key == "test_enemy")
    enemy.require(Think).routine = "typo"

    try:
        step_runtime(runtime)
    except KeyError as error:
        assert "Unknown think behaviour key 'typo'" in str(error)
    else:
        raise AssertionError("An unknown behavior key must fail loudly.")


def test_non_spatial_always_active_entity_thinks_and_is_in_snapshot():
    from game.runtime import THINK_ROUTINES

    runtime = create_runtime()
    routine_key = "test_count_always_active"
    if not THINK_ROUTINES.has(routine_key):
        THINK_ROUTINES.register(
            routine_key,
            lambda _runtime, entity, _dt: setattr(
                entity.require(Counter), "ticks", entity.require(Counter).ticks + 1
            ),
        )
    timer = runtime.entities.create(
        EntityDefinition(
            "world_timer",
            (AlwaysActive(), Think(routine_key, cadence_hz=60), Counter()),
        )
    )

    step_runtime(runtime)
    snapshot = snapshot_for_session(runtime, "local")

    assert timer.require(Counter).ticks == 1
    assert timer.id in {entity["id"] for entity in snapshot["entities"]}


def test_far_weapon_cooldown_freezes_and_resumes_near_player():
    runtime = create_runtime()
    far_weapon = runtime.entities.create(
        EntityDefinition(
            "far_weapon",
            (
                Transform(Vec3(1000, 0, 1000)),
                Weapon(1, 1, 1, seconds_until_ready=1),
            ),
        )
    )

    step_runtime(runtime)
    assert far_weapon.require(Weapon).seconds_until_ready == 1

    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    player.require(Transform).position = Vec3(1000, 0, 1000)
    step_runtime(runtime)
    assert far_weapon.require(Weapon).seconds_until_ready < 1


def test_distant_enemy_freezes_think_and_movement_then_resumes_near_player():
    runtime = create_runtime()
    enemy = next(entity for entity in runtime.entities.entities.values() if entity.def_key == "test_enemy")
    enemy.require(Transform).position = Vec3(1000.5, 0, 1000.5)
    initial_think_delay = enemy.require(Think).seconds_until_tick

    step_runtime(runtime)

    assert enemy.require(Transform).position == Vec3(1000.5, 0, 1000.5)
    assert enemy.require(Think).seconds_until_tick == initial_think_delay

    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    player.require(Transform).position = Vec3(1004.5, 0, 1000.5)
    step_runtime(runtime)
    step_runtime(runtime)

    assert enemy.require(Transform).position.x > 1000.5
    assert enemy.require(Think).seconds_until_tick > 0


def test_enemy_uses_shared_control_and_physics_to_fall_and_stop_at_wall():
    runtime = create_runtime()
    runtime.world = World()
    for x in range(-2, 7):
        for z in range(-2, 3):
            runtime.world.set_block(x, -1, z, "grass")
    for y in range(3):
        runtime.world.set_block(2, y, 0, "stone")

    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    player.require(Transform).position = Vec3(4.5, 0, 0.5)
    enemy = next(entity for entity in runtime.entities.entities.values() if entity.def_key == "test_enemy")
    enemy.require(Transform).position = Vec3(0.5, 3, 0.5)

    for _ in range(240):
        step_runtime(runtime)

    assert enemy.require(Grounded).value is True
    assert enemy.require(Transform).position.y == pytest.approx(0, abs=1e-5)
    assert enemy.require(Transform).position.x < 2
    assert enemy.require(Transform).position.x == pytest.approx(1.65, abs=1e-4)


def test_chunk_streaming_generates_around_player_and_keeps_old_chunks_resident():
    runtime = create_runtime()
    initial_keys = set(runtime.world.chunks)
    assert len(runtime.active_chunk_keys) == (ACTIVE_RADIUS_CHUNKS * 2 + 1) ** 2
    assert len(initial_keys) == (GENERATION_RADIUS_CHUNKS * 2 + 1) ** 2

    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    player.require(Transform).position = Vec3(16 * 9 + 2.5, 0, 2.5)
    step_runtime(runtime)

    assert runtime.world.is_solid(16 * 9 + 2, -1, 2)
    assert initial_keys <= set(runtime.world.chunks)
    assert len(runtime.world.chunks) > len(initial_keys)
    snapshot = snapshot_for_session(runtime, "local")
    assert all((chunk["x"], chunk["z"]) in runtime.world.chunks for chunk in snapshot["chunks"])


@pytest.mark.parametrize("position", [(-150.5, 0.5), (150.5, 0.5), (0.5, -150.5), (0.5, 150.5)])
def test_ground_is_generated_in_every_horizontal_direction(position):
    runtime = create_runtime()
    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    player.require(Transform).position = Vec3(position[0], 0, position[1])

    step_runtime(runtime)

    assert runtime.world.is_solid(math.floor(position[0]), -1, math.floor(position[1]))
