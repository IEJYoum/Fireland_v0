import pytest

from game.blocks import AIR_BLOCK_KEY
from game.components import Health, Inventory, Transform
from game.entities import EntityDefinition, EntityStore
from game.registry import BehaviorRegistry
from game.vectors import Vec3
from game.world3d import create_test_arena, split_block_coordinate, World


def test_negative_world_coordinates_map_to_floor_divided_chunks():
    assert split_block_coordinate(-1, -17) == ((-1, -2), (15, 15))
    world = World()
    world.set_block(-1, 3, -17, "stone")
    assert world.get_block(-1, 3, -17) == "stone"
    assert world.require_chunk((-1, -2)).get_block(15, 3, 15) == "stone"


def test_missing_blocks_are_air_and_noop_air_writes_do_not_create_chunks():
    world = World()
    assert world.get_block(50, 20, -80) == AIR_BLOCK_KEY
    assert world.set_block(50, 20, -80, AIR_BLOCK_KEY) is False
    assert world.chunks == {}


def test_block_edit_bumps_only_the_affected_chunk_revision():
    world = World()
    world.set_block(0, 0, 0, "stone")
    world.set_block(16, 0, 0, "stone")
    first = world.require_chunk((0, 0))
    second = world.require_chunk((1, 0))
    first_revision = first.revision
    second_revision = second.revision

    assert world.set_block(1, 0, 0, "wood") is True
    assert first.revision == first_revision + 1
    assert second.revision == second_revision
    assert world.set_block(1, 0, 0, "wood") is False
    assert first.revision == first_revision + 1


def test_entity_definition_materializes_independent_mutable_components():
    definition = EntityDefinition(
        "test_actor",
        (
            Transform(Vec3(0, 0, 0)),
            Health(10, 10),
            Inventory(),
        ),
    )
    store = EntityStore()
    first = store.create(definition)
    second = store.create(definition, (Transform(Vec3(3, 2, 1)),))

    first.require(Inventory).item_ids.append(99)
    first.require(Health).current = 4

    assert second.require(Inventory).item_ids == []
    assert second.require(Health).current == 10
    assert second.require(Transform).position == Vec3(3, 2, 1)
    assert [entity.id for entity in store.query(Transform, Health)] == [first.id, second.id]


def test_duplicate_definition_components_fail_loudly():
    with pytest.raises(ValueError, match="repeats"):
        EntityDefinition("bad", (Inventory(), Inventory()))


def test_behaviour_registry_looks_up_keys_and_rejects_unknown_or_duplicate_keys():
    registry = BehaviorRegistry("think")

    def idle():
        return "idle"

    assert registry.register("idle", idle) is idle
    assert registry.lookup("idle")() == "idle"
    with pytest.raises(KeyError, match="Unknown think"):
        registry.lookup("missing")
    with pytest.raises(ValueError, match="Duplicate think"):
        registry.register("idle", idle)


def test_test_arena_contains_ground_obstacle_wall_and_platform():
    world = create_test_arena()
    assert world.is_solid(2, -1, 2)
    assert world.is_solid(6, 0, 2)
    assert all(world.is_solid(10, y, 0) for y in range(3))
    assert world.is_solid(16, 2, 4)
    assert not world.is_solid(2, 0, 2)
