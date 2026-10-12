from game.actions3d import apply_action
from game.components import Collider, Gravity, Grounded, Inventory, Think, Transform, Velocity
from game.entities import EntityDefinition
from game.runtime import create_runtime, step_runtime
from game.vectors import Aabb, Vec3
from game.wire import snapshot_for_session


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
