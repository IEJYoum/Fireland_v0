"""Deterministic biome, structure, and spawn-descriptor chunk generation."""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterator

from .blocks import AIR_BLOCK_KEY, get_block_definition
from .registry import BehaviorRegistry
from .vectors import Vec3


CHUNK_SIZE_X = 16
CHUNK_SIZE_Z = 16
BIOME_REGION_SIZE_CHUNKS = 6
ChunkKey = tuple[int, int]
LocalBlockKey = tuple[int, int, int]
WorldBlock = tuple[int, int, int, str]
GeneratedBlocks = dict[LocalBlockKey, str]
CHUNK_GENERATORS = BehaviorRegistry("chunk generator")
_MASK_64 = (1 << 64) - 1


@dataclass(frozen=True)
class SpawnDescriptor:
    """Stable chunk-owned request; runtime materialization supplies entity ids."""

    key: str
    kind: str
    content_key: str
    local_position: Vec3


@dataclass(frozen=True)
class GeneratedChunk:
    biome_key: str
    blocks: GeneratedBlocks
    spawns: tuple[SpawnDescriptor, ...] = ()


def split_block_coordinate(x: int, z: int) -> tuple[ChunkKey, tuple[int, int]]:
    chunk_x, local_x = divmod(x, CHUNK_SIZE_X)
    chunk_z, local_z = divmod(z, CHUNK_SIZE_Z)
    return (chunk_x, chunk_z), (local_x, local_z)


@dataclass
class Chunk:
    chunk_x: int
    chunk_z: int
    blocks: dict[LocalBlockKey, str] = field(default_factory=dict)
    biome_key: str = "custom"
    spawn_descriptors: tuple[SpawnDescriptor, ...] = ()
    revision: int = 0

    @property
    def key(self) -> ChunkKey:
        return self.chunk_x, self.chunk_z

    def get_block(self, local_x: int, y: int, local_z: int) -> str:
        return self.blocks.get((local_x, y, local_z), AIR_BLOCK_KEY)

    def set_block(self, local_x: int, y: int, local_z: int, block_key: str) -> bool:
        if not (0 <= local_x < CHUNK_SIZE_X and 0 <= local_z < CHUNK_SIZE_Z):
            raise ValueError("Local block coordinates fall outside the chunk.")
        get_block_definition(block_key)
        coordinate = (local_x, y, local_z)
        previous = self.blocks.get(coordinate, AIR_BLOCK_KEY)
        if previous == block_key:
            return False
        if block_key == AIR_BLOCK_KEY:
            self.blocks.pop(coordinate, None)
        else:
            self.blocks[coordinate] = block_key
        self.revision += 1
        return True


@dataclass
class World:
    seed: int = 1
    generator_key: str | None = None
    chunks: dict[ChunkKey, Chunk] = field(default_factory=dict)

    def get_chunk(self, chunk_key: ChunkKey) -> Chunk | None:
        return self.chunks.get(chunk_key)

    def require_chunk(self, chunk_key: ChunkKey) -> Chunk:
        chunk = self.get_chunk(chunk_key)
        if chunk is None:
            raise KeyError(f"Unknown chunk {chunk_key}.")
        return chunk

    def get_or_create_chunk(self, chunk_key: ChunkKey) -> Chunk:
        return self.ensure_chunk(chunk_key)

    def ensure_chunk(self, chunk_key: ChunkKey) -> Chunk:
        chunk = self.chunks.get(chunk_key)
        if chunk is not None:
            return chunk
        if self.generator_key is None:
            chunk = Chunk(*chunk_key)
        else:
            generator = CHUNK_GENERATORS.lookup(self.generator_key)
            generated = generator(self.seed, chunk_key[0], chunk_key[1])
            if not isinstance(generated, GeneratedChunk):
                raise TypeError(
                    f"Chunk generator {self.generator_key!r} must return GeneratedChunk."
                )
            for (local_x, _y, local_z), block_key in generated.blocks.items():
                if not (0 <= local_x < CHUNK_SIZE_X and 0 <= local_z < CHUNK_SIZE_Z):
                    raise ValueError(
                        f"Chunk generator {self.generator_key!r} emitted an out-of-range block."
                    )
                get_block_definition(block_key)
            for descriptor in generated.spawns:
                position = descriptor.local_position
                if (
                    not descriptor.key
                    or not descriptor.kind
                    or not descriptor.content_key
                    or not position.is_finite()
                    or not (0 <= position.x < CHUNK_SIZE_X)
                    or not (0 <= position.z < CHUNK_SIZE_Z)
                ):
                    raise ValueError(
                        f"Chunk generator {self.generator_key!r} emitted an invalid spawn descriptor."
                    )
            chunk = Chunk(
                *chunk_key,
                blocks=dict(generated.blocks),
                biome_key=generated.biome_key,
                spawn_descriptors=tuple(generated.spawns),
                revision=1,
            )
        self.chunks[chunk_key] = chunk
        return chunk

    def get_block(self, x: int, y: int, z: int) -> str:
        chunk_key, (local_x, local_z) = split_block_coordinate(x, z)
        chunk = self.chunks.get(chunk_key)
        if chunk is None:
            return AIR_BLOCK_KEY
        return chunk.get_block(local_x, y, local_z)

    def set_block(self, x: int, y: int, z: int, block_key: str) -> bool:
        get_block_definition(block_key)
        chunk_key, (local_x, local_z) = split_block_coordinate(x, z)
        chunk = self.chunks.get(chunk_key)
        if chunk is None and block_key == AIR_BLOCK_KEY and self.generator_key is None:
            return False
        if chunk is None:
            chunk = self.ensure_chunk(chunk_key)
        return chunk.set_block(local_x, y, local_z, block_key)

    def is_solid(self, x: int, y: int, z: int) -> bool:
        return get_block_definition(self.get_block(x, y, z)).solid

    def iter_non_air_blocks(self, chunk_key: ChunkKey) -> Iterator[WorldBlock]:
        chunk = self.chunks.get(chunk_key)
        if chunk is None:
            return iter(())
        base_x = chunk.chunk_x * CHUNK_SIZE_X
        base_z = chunk.chunk_z * CHUNK_SIZE_Z
        return (
            (base_x + local_x, y, base_z + local_z, block_key)
            for (local_x, y, local_z), block_key in chunk.blocks.items()
        )


PLAYER_SPAWN = Vec3(4.5, 0.0, 4.5)


def stable_coordinate_seed(world_seed: int, x: int, z: int, salt: int = 0) -> int:
    """Stable integer mixing; unlike hash(), this is repeatable across processes."""

    value = (
        (world_seed & _MASK_64)
        ^ ((x * 0x9E3779B185EBCA87) & _MASK_64)
        ^ ((z * 0xC2B2AE3D27D4EB4F) & _MASK_64)
        ^ ((salt * 0x165667B19E3779F9) & _MASK_64)
    )
    value = (value ^ (value >> 30)) * 0xBF58476D1CE4E5B9 & _MASK_64
    value = (value ^ (value >> 27)) * 0x94D049BB133111EB & _MASK_64
    return value ^ (value >> 31)


def _chunk_randomizer(
    world_seed: int,
    chunk_x: int,
    chunk_z: int,
    salt: int = 0,
) -> random.Random:
    return random.Random(stable_coordinate_seed(world_seed, chunk_x, chunk_z, salt))


@lru_cache(maxsize=4096)
def _biome_site(world_seed: int, macro_x: int, macro_z: int) -> tuple[float, float, str]:
    randomizer = _chunk_randomizer(world_seed, macro_x, macro_z, salt=0xB10)
    site_x = (macro_x + 0.15 + randomizer.random() * 0.70) * BIOME_REGION_SIZE_CHUNKS
    site_z = (macro_z + 0.15 + randomizer.random() * 0.70) * BIOME_REGION_SIZE_CHUNKS
    roll = randomizer.random()
    biome_key = "plains" if roll < 0.46 else "forest" if roll < 0.78 else "settled"
    return site_x, site_z, biome_key


@lru_cache(maxsize=16384)
def biome_for_chunk(world_seed: int, chunk_x: int, chunk_z: int) -> str:
    macro_x = math.floor(chunk_x / BIOME_REGION_SIZE_CHUNKS)
    macro_z = math.floor(chunk_z / BIOME_REGION_SIZE_CHUNKS)
    center_x = chunk_x + 0.5
    center_z = chunk_z + 0.5
    sites = []
    for offset_x in range(-1, 2):
        for offset_z in range(-1, 2):
            owner_x = macro_x + offset_x
            owner_z = macro_z + offset_z
            site_x, site_z, biome_key = _biome_site(world_seed, owner_x, owner_z)
            distance_squared = (site_x - center_x) ** 2 + (site_z - center_z) ** 2
            sites.append((distance_squared, owner_x, owner_z, biome_key))
    return min(sites)[3]


def _flat_ground() -> GeneratedBlocks:
    return {
        (local_x, -1, local_z): "grass"
        for local_x in range(CHUNK_SIZE_X)
        for local_z in range(CHUNK_SIZE_Z)
    }


def _emit_world_block(
    blocks: GeneratedBlocks,
    chunk_x: int,
    chunk_z: int,
    world_x: int,
    y: int,
    world_z: int,
    block_key: str,
) -> None:
    local_x = world_x - chunk_x * CHUNK_SIZE_X
    local_z = world_z - chunk_z * CHUNK_SIZE_Z
    if 0 <= local_x < CHUNK_SIZE_X and 0 <= local_z < CHUNK_SIZE_Z:
        blocks[(local_x, y, local_z)] = block_key


def _add_forest(
    world_seed: int,
    chunk_x: int,
    chunk_z: int,
    blocks: GeneratedBlocks,
) -> None:
    base_x = chunk_x * CHUNK_SIZE_X
    base_z = chunk_z * CHUNK_SIZE_Z
    anchor_biomes: dict[ChunkKey, str] = {}
    for world_x in range(base_x - 1, base_x + CHUNK_SIZE_X + 1):
        for world_z in range(base_z - 1, base_z + CHUNK_SIZE_Z + 1):
            anchor_chunk_x = math.floor(world_x / CHUNK_SIZE_X)
            anchor_chunk_z = math.floor(world_z / CHUNK_SIZE_Z)
            anchor_chunk_key = (anchor_chunk_x, anchor_chunk_z)
            if anchor_chunk_key not in anchor_biomes:
                anchor_biomes[anchor_chunk_key] = biome_for_chunk(
                    world_seed, anchor_chunk_x, anchor_chunk_z
                )
            if anchor_biomes[anchor_chunk_key] != "forest":
                continue
            randomizer = random.Random(
                stable_coordinate_seed(world_seed, world_x, world_z, salt=0x7EED)
            )
            if randomizer.random() >= 0.035:
                continue
            for y in range(3):
                _emit_world_block(blocks, chunk_x, chunk_z, world_x, y, world_z, "wood")
            for offset_x in range(-1, 2):
                for offset_z in range(-1, 2):
                    if offset_x == 0 and offset_z == 0:
                        continue
                    _emit_world_block(
                        blocks,
                        chunk_x,
                        chunk_z,
                        world_x + offset_x,
                        2,
                        world_z + offset_z,
                        "leaves",
                    )
            for offset_x, offset_z in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                _emit_world_block(
                    blocks,
                    chunk_x,
                    chunk_z,
                    world_x + offset_x,
                    3,
                    world_z + offset_z,
                    "leaves",
                )


def _prefab_interior(randomizer: random.Random) -> tuple[str, set[tuple[int, int]]]:
    kind = randomizer.choice(("square", "l"))
    if kind == "square":
        width = randomizer.randint(4, 6)
        depth = randomizer.randint(4, 6)
        return kind, {(x, z) for x in range(width) for z in range(depth)}
    width = randomizer.randint(7, 9)
    depth = randomizer.randint(7, 9)
    arm_width = randomizer.randint(3, 4)
    arm_depth = randomizer.randint(3, 4)
    interior = {
        (x, z)
        for x in range(width)
        for z in range(depth)
        if x < arm_width or z >= depth - arm_depth
    }
    return kind, interior


def _prefab_walls(interior: set[tuple[int, int]]) -> set[tuple[int, int]]:
    return {
        neighbor
        for x, z in interior
        for neighbor in ((x + 1, z), (x - 1, z), (x, z + 1), (x, z - 1))
        if neighbor not in interior
    }


def _random_pickup_key(randomizer: random.Random) -> str:
    category = randomizer.randrange(3)
    if category == 0:
        return randomizer.choice(("pistol", "rifle", "sniper_rifle", "knife"))
    return "health_up" if category == 1 else "food"


def _add_settled_prefab(
    world_seed: int,
    chunk_x: int,
    chunk_z: int,
    blocks: GeneratedBlocks,
) -> tuple[SpawnDescriptor, ...]:
    randomizer = _chunk_randomizer(world_seed, chunk_x, chunk_z, salt=0xB17D)
    if randomizer.random() >= 0.78:
        return ()
    _kind, interior = _prefab_interior(randomizer)
    walls = _prefab_walls(interior)
    all_cells = interior | walls
    min_x = min(x for x, _ in all_cells)
    max_x = max(x for x, _ in all_cells)
    min_z = min(z for _, z in all_cells)
    max_z = max(z for _, z in all_cells)
    origin_x = randomizer.randint(1 - min_x, 14 - max_x)
    origin_z = randomizer.randint(1 - min_z, 14 - max_z)
    translated_interior = {(origin_x + x, origin_z + z) for x, z in interior}
    translated_walls = {(origin_x + x, origin_z + z) for x, z in walls}

    for x, z in translated_interior:
        blocks[(x, -1, z)] = "stone"
        blocks[(x, 3, z)] = "wood"
    for x, z in translated_walls:
        for y in range(3):
            blocks[(x, y, z)] = "stone"

    door_candidates = sorted(
        (x, z)
        for x, z in translated_walls
        if sum((x + dx, z + dz) in translated_interior for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))) == 1
    )
    door_x, door_z = randomizer.choice(door_candidates)
    has_door = randomizer.random() < 0.5
    for y in range(2):
        if has_door:
            blocks[(door_x, y, door_z)] = "door"
        else:
            blocks.pop((door_x, y, door_z), None)

    if not has_door or randomizer.random() >= 0.10:
        return ()
    pickup_x, pickup_z = randomizer.choice(sorted(translated_interior))
    return (
        SpawnDescriptor(
            "building-pickup",
            "pickup",
            _random_pickup_key(randomizer),
            Vec3(pickup_x + 0.5, 0.0, pickup_z + 0.5),
        ),
    )


def _add_origin_building(blocks: GeneratedBlocks) -> tuple[SpawnDescriptor, ...]:
    interior = {(x, z) for x in range(2, 8) for z in range(2, 8)}
    walls = _prefab_walls(interior)
    for x, z in interior:
        blocks[(x, -1, z)] = "stone"
        blocks[(x, 3, z)] = "wood"
    for x, z in walls:
        for y in range(3):
            blocks[(x, y, z)] = "stone"
    for y in range(2):
        blocks[(4, y, 8)] = "door"
    return (
        SpawnDescriptor("starter-pistol", "pickup", "pistol", Vec3(6.5, 0.0, 4.5)),
        SpawnDescriptor("origin-enemy-0", "enemy", "pistol", Vec3(4.5, 0.0, 13.5)),
        SpawnDescriptor("origin-enemy-1", "enemy", "rifle", Vec3(12.5, 0.0, 12.5)),
    )


def main_region_cells(blocks: GeneratedBlocks) -> list[tuple[int, int]]:
    """Walkable cells connected to a chunk boundary through two-block clearance."""
    def is_solid(x: int, y: int, z: int) -> bool:
        return get_block_definition(blocks.get((x, y, z), AIR_BLOCK_KEY)).solid

    walkable = {
        (x, z)
        for x in range(CHUNK_SIZE_X)
        for z in range(CHUNK_SIZE_Z)
        if is_solid(x, -1, z) and not is_solid(x, 0, z) and not is_solid(x, 1, z)
    }
    boundary = sorted(
        cell
        for cell in walkable
        if cell[0] in (0, CHUNK_SIZE_X - 1) or cell[1] in (0, CHUNK_SIZE_Z - 1)
    )
    connected = set(boundary)
    frontier = deque(boundary)
    while frontier:
        x, z = frontier.popleft()
        for neighbor in ((x + 1, z), (x - 1, z), (x, z + 1), (x, z - 1)):
            if neighbor in walkable and neighbor not in connected:
                connected.add(neighbor)
                frontier.append(neighbor)
    return sorted(
        (x, z)
        for x, z in connected
        if 1 <= x < CHUNK_SIZE_X - 1 and 1 <= z < CHUNK_SIZE_Z - 1
    )


def _enemy_spawn_descriptors(
    world_seed: int,
    chunk_x: int,
    chunk_z: int,
    blocks: GeneratedBlocks,
) -> tuple[SpawnDescriptor, ...]:
    distance_chunks = max(abs(chunk_x), abs(chunk_z))
    randomizer = _chunk_randomizer(world_seed, chunk_x, chunk_z, salt=0xE3E)
    spawn_chance = min(0.24, 0.04 + distance_chunks * 0.006)
    if randomizer.random() >= spawn_chance:
        return ()
    count = 1
    if distance_chunks >= 24 and randomizer.random() < 0.55:
        count += 1
    if distance_chunks >= 64 and randomizer.random() < 0.45:
        count += 1
    candidates = [
        (x, z)
        for x, z in main_region_cells(blocks)
        if math.hypot(chunk_x * CHUNK_SIZE_X + x + 0.5, chunk_z * CHUNK_SIZE_Z + z + 0.5) >= 8
    ]
    randomizer.shuffle(candidates)
    descriptors = []
    used: list[tuple[int, int]] = []
    for x, z in candidates:
        if any(math.hypot(x - used_x, z - used_z) < 4 for used_x, used_z in used):
            continue
        weapon_choices = ["pistol", "knife"]
        if distance_chunks >= 8:
            weapon_choices.append("rifle")
        if distance_chunks >= 24:
            weapon_choices.append("sniper_rifle")
        descriptors.append(
            SpawnDescriptor(
                f"enemy-{len(descriptors)}",
                "enemy",
                randomizer.choice(weapon_choices),
                Vec3(x + 0.5, 0.0, z + 0.5),
            )
        )
        used.append((x, z))
        if len(descriptors) == count:
            break
    return tuple(descriptors)


def _overworld_generator(world_seed: int, chunk_x: int, chunk_z: int) -> GeneratedChunk:
    blocks = _flat_ground()
    if (chunk_x, chunk_z) == (0, 0):
        return GeneratedChunk("origin", blocks, _add_origin_building(blocks))

    biome_key = biome_for_chunk(world_seed, chunk_x, chunk_z)
    spawns: tuple[SpawnDescriptor, ...] = ()
    if biome_key == "forest":
        _add_forest(world_seed, chunk_x, chunk_z, blocks)
    elif biome_key == "settled":
        spawns = _add_settled_prefab(world_seed, chunk_x, chunk_z, blocks)
    spawns += _enemy_spawn_descriptors(world_seed, chunk_x, chunk_z, blocks)
    return GeneratedChunk(biome_key, blocks, spawns)


def _test_arena_generator(world_seed: int, chunk_x: int, chunk_z: int) -> GeneratedChunk:
    blocks: GeneratedBlocks = {}
    base_x = chunk_x * CHUNK_SIZE_X
    base_z = chunk_z * CHUNK_SIZE_Z
    for local_x in range(CHUNK_SIZE_X):
        for local_z in range(CHUNK_SIZE_Z):
            x = base_x + local_x
            z = base_z + local_z
            if -16 <= x < 32 and -16 <= z < 32:
                blocks[(local_x, -1, local_z)] = "grass"
            if (x, z) == (6, 2):
                blocks[(local_x, 0, local_z)] = "stone"
            if x == 10 and -3 <= z < 9:
                for y in range(3):
                    blocks[(local_x, y, local_z)] = "stone"
            if 14 <= x < 20 and 1 <= z < 8:
                blocks[(local_x, 2, local_z)] = "wood"
            if (x, z) == (13, 7):
                blocks[(local_x, 0, local_z)] = "stone"
            if (x, z) == (14, 7):
                blocks[(local_x, 1, local_z)] = "stone"
    return GeneratedChunk("arena", blocks)


CHUNK_GENERATORS.register("overworld", _overworld_generator)
CHUNK_GENERATORS.register("basic_flat", _overworld_generator)
CHUNK_GENERATORS.register("test_arena", _test_arena_generator)


def create_procedural_world(seed: int = 7, generator_key: str = "overworld") -> World:
    CHUNK_GENERATORS.lookup(generator_key)
    return World(seed=seed, generator_key=generator_key)


def create_test_arena() -> World:
    """Create a finite arena that exposes the first physics failure modes."""

    world = create_procedural_world(generator_key="test_arena")
    for chunk_x in range(-1, 2):
        for chunk_z in range(-1, 2):
            world.ensure_chunk((chunk_x, chunk_z))
    return world
