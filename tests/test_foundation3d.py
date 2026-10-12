import math

import pytest

from game.blocks import AIR_BLOCK_KEY
from game.components import Health, Inventory, Transform
from game.entities import EntityDefinition, EntityStore
from game.registry import BehaviorRegistry
from game.vectors import Vec3
from game.world3d import (
    CHUNK_GENERATORS,
    PLAYER_SPAWN,
    World,
    biome_for_chunk,
    create_procedural_world,
    create_test_arena,
    main_region_cells,
    split_block_coordinate,
)


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


def test_seeded_chunk_generation_is_deterministic_and_order_independent():
    first = create_procedural_world(seed=9182)
    second = create_procedural_world(seed=9182)
    first.ensure_chunk((-7, 11))
    first.ensure_chunk((4, -3))
    second.ensure_chunk((4, -3))
    second.ensure_chunk((-7, 11))

    assert first.require_chunk((-7, 11)).blocks == second.require_chunk((-7, 11)).blocks
    assert first.require_chunk((4, -3)).blocks == second.require_chunk((4, -3)).blocks
    assert first.require_chunk((4, -3)).revision == 1
    assert CHUNK_GENERATORS.has("basic_flat")


def test_generated_chunk_edits_apply_over_the_deterministic_base():
    world = create_procedural_world(seed=22)
    chunk = world.ensure_chunk((3, -2))
    base_revision = chunk.revision
    world_x = 3 * 16 + 5
    world_z = -2 * 16 + 7

    assert world.is_solid(world_x, -1, world_z)
    assert world.set_block(world_x, -1, world_z, "air") is True
    assert not world.is_solid(world_x, -1, world_z)
    assert chunk.revision == base_revision + 1


def test_origin_chunk_contains_start_room_door_pistol_and_connected_outside_enemies():
    world = create_procedural_world(seed=7)
    chunk = world.ensure_chunk((0, 0))

    assert chunk.biome_key == "origin"
    assert world.get_block(4, 0, 8) == "door"
    assert world.get_block(4, 1, 8) == "door"
    assert world.is_solid(math.floor(PLAYER_SPAWN.x), -1, math.floor(PLAYER_SPAWN.z))
    assert not world.is_solid(math.floor(PLAYER_SPAWN.x), 0, math.floor(PLAYER_SPAWN.z))
    assert world.is_solid(math.floor(PLAYER_SPAWN.x), 3, math.floor(PLAYER_SPAWN.z))
    assert {descriptor.key for descriptor in chunk.spawn_descriptors} == {
        "starter-pistol",
        "origin-enemy-0",
        "origin-enemy-1",
    }
    connected = set(main_region_cells(chunk.blocks))
    for descriptor in chunk.spawn_descriptors:
        if descriptor.kind == "enemy":
            assert (
                math.floor(descriptor.local_position.x),
                math.floor(descriptor.local_position.z),
            ) in connected


def test_biomes_are_deterministic_contiguous_regions_not_independent_chunk_rolls():
    coordinates = [
        (x, z)
        for x in range(-12, 13)
        for z in range(-12, 13)
        if (x, z) != (0, 0)
    ]
    first = {coordinate: biome_for_chunk(9182, *coordinate) for coordinate in coordinates}
    second_world = create_procedural_world(seed=9182)
    second = {
        coordinate: second_world.ensure_chunk(coordinate).biome_key
        for coordinate in reversed(coordinates)
    }

    assert first == second
    assert {"plains", "forest", "settled"} <= set(first.values())
    assert any(
        all(
            coordinate in first
            for coordinate in ((x, z), (x + 1, z), (x, z + 1), (x + 1, z + 1))
        )
        and first[(x, z)]
        == first[(x + 1, z)]
        == first[(x, z + 1)]
        == first[(x + 1, z + 1)]
        for x in range(-12, 12)
        for z in range(-12, 12)
    )


def test_seeded_enemy_density_increases_with_distance_from_origin():
    near_world = create_procedural_world(seed=7)
    far_world = create_procedural_world(seed=7)
    near_count = sum(
        descriptor.kind == "enemy"
        for x in range(-5, 5)
        for z in range(-5, 5)
        for descriptor in near_world.ensure_chunk((x, z)).spawn_descriptors
    )
    far_count = sum(
        descriptor.kind == "enemy"
        for x in range(50, 60)
        for z in range(50, 60)
        for descriptor in far_world.ensure_chunk((x, z)).spawn_descriptors
    )

    assert 0 < near_count < far_count
