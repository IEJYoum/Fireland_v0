import pytest

from game.combat3d import fire_hitscan, interact_pickup, raycast
from game.components import Collider, Equipment, Health, Inventory, Pickup, Transform, Weapon
from game.entities import EntityDefinition, EntityStore
from game.runtime import create_runtime, step_runtime, step_weapon_cooldowns
from game.vectors import Aabb, Vec3
from game.world3d import World


TARGET = EntityDefinition(
    "target",
    (
        Transform(Vec3(0, 0, 0)),
        Collider(Aabb(0.4, 1.8, 0.4)),
        Health(50, 50),
    ),
)


def test_raycast_returns_nearest_entity_and_block_occludes_it():
    entities = EntityStore()
    near = entities.create(TARGET, (Transform(Vec3(0, 0, -3)),))
    entities.create(TARGET, (Transform(Vec3(0, 0, -6)),))
    world = World()
    origin = Vec3(0, 1, 0)

    hit = raycast(world, entities, origin, Vec3(0, 0, -1), 20, lambda entity: entity.has(Health))
    assert hit is not None
    assert hit.entity_id == near.id

    world.set_block(0, 1, -2, "stone")
    blocked = raycast(world, entities, origin, Vec3(0, 0, -1), 20, lambda entity: entity.has(Health))
    assert blocked is not None
    assert blocked.kind == "block"
    assert blocked.block == (0, 1, -2)


def test_vertical_aim_hits_elevated_target_and_misses_below_ray():
    entities = EntityStore()
    elevated = entities.create(TARGET, (Transform(Vec3(0, 4, -6)),))
    entities.create(TARGET, (Transform(Vec3(0, 0, -6)),))
    origin = Vec3(0, 1, 0)
    direction = Vec3(0, 3.8, -6)

    hit = raycast(World(), entities, origin, direction, 20, lambda entity: entity.has(Health))

    assert hit is not None
    assert hit.entity_id == elevated.id


def test_hitscan_damage_obeys_server_weapon_cooldown():
    runtime = create_runtime()
    session = runtime.require_session("local")
    player = runtime.entities.require(session.player_entity_id)
    player.require(Transform).position = Vec3(0, 0, 0)
    target = next(entity for entity in runtime.entities.entities.values() if entity.def_key == "test_enemy")
    target.require(Transform).position = Vec3(0, 0, -5)
    runtime.world = World()

    assert fire_hitscan(runtime, "local", Vec3(0, 0, -1)) is True
    assert target.require(Health).current == 50
    assert fire_hitscan(runtime, "local", Vec3(0, 0, -1)) is False
    assert target.require(Health).current == 50

    for _ in range(19):
        step_weapon_cooldowns(runtime, 1 / 60, set(runtime.entities.entities))
    assert fire_hitscan(runtime, "local", Vec3(0, 0, -1)) is True
    assert target.require(Health).current == 25


def test_pickup_interaction_transfers_the_same_entity_to_inventory():
    runtime = create_runtime()
    session = runtime.require_session("local")
    player = runtime.entities.require(session.player_entity_id)
    player.require(Transform).position = Vec3(0, 0, 0)
    pickup = next(entity for entity in runtime.entities.query(Pickup))
    pickup.require(Transform).position = Vec3(0, 1.4, -2)
    runtime.world = World()

    assert interact_pickup(runtime, "local", Vec3(0, 0, -1)) is True
    assert pickup.id in player.require(Inventory).item_ids
    assert player.require(Equipment).equipped_item_id == pickup.id
    assert pickup.get(Transform) is None
    assert pickup.get(Pickup) is None
    assert pickup.has(Weapon)


def test_out_of_range_pickup_interaction_fails():
    runtime = create_runtime()
    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    player.require(Transform).position = Vec3(0, 0, 0)
    pickup = next(entity for entity in runtime.entities.query(Pickup))
    pickup.require(Transform).position = Vec3(0, 1.4, -8)
    runtime.world = World()

    assert interact_pickup(runtime, "local", Vec3(0, 0, -1)) is False
    assert pickup.id not in player.require(Inventory).item_ids


def test_zero_or_nonfinite_rays_are_rejected():
    runtime = create_runtime()
    with pytest.raises(ValueError, match="zero"):
        fire_hitscan(runtime, "local", Vec3(0, 0, 0))
    with pytest.raises(ValueError, match="finite"):
        fire_hitscan(runtime, "local", Vec3(float("nan"), 0, -1))
