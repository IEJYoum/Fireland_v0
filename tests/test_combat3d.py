import pytest

from game.combat3d import apply_damage, fire_hitscan, raycast
from game.components import Collider, Equipment, Health, Hunger, Inventory, Pickup, Transform, Weapon, Xp
from game.entities import EntityDefinition, EntityStore
from game.inventory import consume_food, equip_next, interact_nearby
from game.items import create_item, spawn_item
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


def equip_weapon(runtime, item_key="pistol"):
    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    weapon = create_item(runtime.entities, item_key)
    player.require(Inventory).item_ids.append(weapon.id)
    player.require(Equipment).equipped_item_id = weapon.id
    return weapon


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
    equip_weapon(runtime)
    player.require(Transform).position = Vec3(0, 0, 0)
    target = next(entity for entity in runtime.entities.entities.values() if entity.def_key == "test_enemy")
    target.require(Transform).position = Vec3(0, 0, -5)
    runtime.world = World()

    first_shot = fire_hitscan(runtime, "local", Vec3(0, 0, -1))
    assert first_shot.fired is True
    assert first_shot.hit_kind == "entity"
    assert first_shot.entity_id == target.id
    assert first_shot.origin is not None
    assert first_shot.end is not None
    assert target.require(Health).current == 40
    assert fire_hitscan(runtime, "local", Vec3(0, 0, -1)).fired is False
    assert target.require(Health).current == 40

    for _ in range(19):
        step_weapon_cooldowns(runtime, 1 / 60, set(runtime.entities.entities))
    assert fire_hitscan(runtime, "local", Vec3(0, 0, -1)).fired is True
    assert target.require(Health).current == 20


def test_hitscan_feedback_distinguishes_block_and_miss_endpoints():
    runtime = create_runtime()
    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    equip_weapon(runtime)
    player.require(Transform).position = Vec3(0, 0, 0)
    runtime.world = World()
    runtime.world.set_block(0, 1, -3, "stone")

    blocked = fire_hitscan(runtime, "local", Vec3(0, 0, -1))

    assert blocked.fired is True
    assert blocked.hit_kind == "block"
    assert blocked.end == Vec3(0, 1.65, -2)

    player.require(Equipment).equipped_item_id = runtime.entities.create(
        EntityDefinition("test_pistol", (Weapon(25, 12, 0.3),))
    ).id
    runtime.world = World()
    missed = fire_hitscan(runtime, "local", Vec3(0, 0, -1))

    assert missed.fired is True
    assert missed.hit_kind == "miss"
    assert missed.end == Vec3(0, 1.65, -12)


def test_pickup_interaction_transfers_the_same_entity_to_inventory():
    runtime = create_runtime()
    session = runtime.require_session("local")
    player = runtime.entities.require(session.player_entity_id)
    player.require(Transform).position = Vec3(0, 0, 0)
    pickup = next(entity for entity in runtime.entities.query(Pickup))
    pickup.require(Transform).position = Vec3(0, 0, -1)
    runtime.world = World()

    assert interact_nearby(runtime, "local") is True
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

    assert interact_nearby(runtime, "local") is False
    assert pickup.id not in player.require(Inventory).item_ids


def test_zero_or_nonfinite_rays_are_rejected():
    runtime = create_runtime()
    equip_weapon(runtime)
    with pytest.raises(ValueError, match="zero"):
        fire_hitscan(runtime, "local", Vec3(0, 0, 0))
    with pytest.raises(ValueError, match="finite"):
        fire_hitscan(runtime, "local", Vec3(float("nan"), 0, -1))


def test_health_and_food_use_the_shared_pickup_and_consumable_paths():
    runtime = create_runtime()
    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    player_position = player.require(Transform).position
    player.require(Health).current = 50
    health_up = spawn_item(runtime.entities, "health_up", player_position)

    assert interact_nearby(runtime, "local") is True
    assert player.require(Health).current == 75
    assert runtime.entities.get(health_up.id) is None

    player.require(Hunger).current = 50
    food = spawn_item(runtime.entities, "food", player_position)
    assert interact_nearby(runtime, "local") is True
    assert food.id in player.require(Inventory).item_ids
    assert consume_food(runtime, "local") is True
    assert player.require(Hunger).current == 85
    assert runtime.entities.get(food.id) is None


def test_equip_cycle_uses_item_entities_without_a_parallel_inventory_model():
    runtime = create_runtime()
    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    pistol = create_item(runtime.entities, "pistol")
    knife = create_item(runtime.entities, "knife")
    player.require(Inventory).item_ids.extend((pistol.id, knife.id))

    assert equip_next(runtime, "local") is True
    assert player.require(Equipment).equipped_item_id == pistol.id
    assert equip_next(runtime, "local") is True
    assert player.require(Equipment).equipped_item_id == knife.id


def test_nearby_door_opens_only_after_pickup_priority_is_exhausted():
    runtime = create_runtime()
    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    player.require(Transform).position = Vec3(4.5, 0, 7.0)

    assert runtime.world.get_block(4, 0, 8) == "door"
    assert interact_nearby(runtime, "local") is True
    assert runtime.world.get_block(4, 0, 8) == "air"
    assert runtime.world.get_block(4, 1, 8) == "air"


def test_enemy_death_grants_xp_and_can_drop_the_actual_held_weapon_instance():
    class WeaponDropRandomizer:
        @staticmethod
        def randrange(_stop):
            return 0

    runtime = create_runtime()
    runtime.randomizer = WeaponDropRandomizer()
    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    enemy = next(entity for entity in runtime.entities.entities.values() if entity.def_key == "test_enemy")
    weapon_id = enemy.require(Equipment).equipped_item_id
    assert weapon_id is not None
    death_position = enemy.require(Transform).position
    enemy.require(Health).current = 1

    assert apply_damage(runtime, enemy, 5, player) == 5

    assert runtime.entities.get(enemy.id) is None
    assert player.require(Xp).points == 25
    dropped_weapon = runtime.entities.require(weapon_id)
    assert dropped_weapon.has(Pickup, Transform)
    assert dropped_weapon.require(Transform).position == death_position
