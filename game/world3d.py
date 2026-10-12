"""Deterministic horizontal chunk generation and sparse block storage."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterator

from .blocks import AIR_BLOCK_KEY, get_block_definition
from .registry import BehaviorRegistry
from .vectors import Vec3


CHUNK_SIZE_X = 16
CHUNK_SIZE_Z = 16
ChunkKey = tuple[int, int]
LocalBlockKey = tuple[int, int, int]
WorldBlock = tuple[int, int, int, str]
GeneratedBlocks = dict[LocalBlockKey, str]
CHUNK_GENERATORS = BehaviorRegistry("chunk generator")


def split_block_coordinate(x: int, z: int) -> tuple[ChunkKey, tuple[int, int]]:
    chunk_x, local_x = divmod(x, CHUNK_SIZE_X)
    chunk_z, local_z = divmod(z, CHUNK_SIZE_Z)
    return (chunk_x, chunk_z), (local_x, local_z)


@dataclass
class Chunk:
    chunk_x: int
    chunk_z: int
    blocks: dict[LocalBlockKey, str] = field(default_factory=dict)
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
        if chunk is None:
            if self.generator_key is None:
                chunk = Chunk(*chunk_key)
            else:
                generator = CHUNK_GENERATORS.lookup(self.generator_key)
                blocks = generator(self.seed, chunk_key[0], chunk_key[1])
                for (local_x, _y, local_z), block_key in blocks.items():
                    if not (0 <= local_x < CHUNK_SIZE_X and 0 <= local_z < CHUNK_SIZE_Z):
                        raise ValueError(
                            f"Chunk generator {self.generator_key!r} emitted an out-of-range block."
                        )
                    get_block_definition(block_key)
                chunk = Chunk(*chunk_key, blocks=blocks, revision=1)
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


PLAYER_SPAWN = Vec3(2.5, 0.0, 2.5)
ENEMY_SPAWN = Vec3(16.5, 3.0, 4.5)
PICKUP_SPAWN = Vec3(6.5, 1.0, 2.5)


def _chunk_randomizer(world_seed: int, chunk_x: int, chunk_z: int) -> random.Random:
    # Avoid Python's randomized hash(); this integer mix is stable across runs.
    mixed_seed = (
        (world_seed * 0x9E3779B185EBCA87)
        ^ (chunk_x * 0xC2B2AE3D27D4EB4F)
        ^ (chunk_z * 0x165667B19E3779F9)
    ) & ((1 << 64) - 1)
    return random.Random(mixed_seed)


def _basic_flat_generator(world_seed: int, chunk_x: int, chunk_z: int) -> GeneratedBlocks:
    blocks: GeneratedBlocks = {
        (local_x, -1, local_z): "grass"
        for local_x in range(CHUNK_SIZE_X)
        for local_z in range(CHUNK_SIZE_Z)
    }
    randomizer = _chunk_randomizer(world_seed, chunk_x, chunk_z)
    # Keep the origin clear and add only chunk-local graybox landmarks. Rich
    # terrain belongs to content; this merely proves deterministic variation.
    if (chunk_x, chunk_z) != (0, 0) and randomizer.random() < 0.28:
        local_x = randomizer.randint(2, CHUNK_SIZE_X - 3)
        local_z = randomizer.randint(2, CHUNK_SIZE_Z - 3)
        height = randomizer.randint(1, 3)
        block_key = randomizer.choice(("stone", "wood"))
        for y in range(height):
            blocks[(local_x, y, local_z)] = block_key
    return blocks


def _test_arena_generator(world_seed: int, chunk_x: int, chunk_z: int) -> GeneratedBlocks:
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
    return blocks


CHUNK_GENERATORS.register("basic_flat", _basic_flat_generator)
CHUNK_GENERATORS.register("test_arena", _test_arena_generator)


def create_procedural_world(seed: int = 7, generator_key: str = "basic_flat") -> World:
    # Lookup now so a typo fails at construction rather than near a player later.
    CHUNK_GENERATORS.lookup(generator_key)
    return World(seed=seed, generator_key=generator_key)


def create_test_arena() -> World:
    """Create a finite arena that exposes the first physics failure modes."""

    world = create_procedural_world(generator_key="test_arena")
    for chunk_x in range(-1, 2):
        for chunk_z in range(-1, 2):
            world.ensure_chunk((chunk_x, chunk_z))
    return world
