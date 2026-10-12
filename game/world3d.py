"""Sparse horizontal chunks and the finite 3D foundation test arena."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from .blocks import AIR_BLOCK_KEY, get_block_definition
from .vectors import Vec3


CHUNK_SIZE_X = 16
CHUNK_SIZE_Z = 16
ChunkKey = tuple[int, int]
LocalBlockKey = tuple[int, int, int]
WorldBlock = tuple[int, int, int, str]


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
    chunks: dict[ChunkKey, Chunk] = field(default_factory=dict)

    def get_chunk(self, chunk_key: ChunkKey) -> Chunk | None:
        return self.chunks.get(chunk_key)

    def require_chunk(self, chunk_key: ChunkKey) -> Chunk:
        chunk = self.get_chunk(chunk_key)
        if chunk is None:
            raise KeyError(f"Unknown chunk {chunk_key}.")
        return chunk

    def get_or_create_chunk(self, chunk_key: ChunkKey) -> Chunk:
        chunk = self.chunks.get(chunk_key)
        if chunk is None:
            chunk = Chunk(*chunk_key)
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
        if chunk is None and block_key == AIR_BLOCK_KEY:
            return False
        if chunk is None:
            chunk = self.get_or_create_chunk(chunk_key)
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


def create_test_arena() -> World:
    """Create a finite arena that exposes the first physics failure modes."""

    world = World()

    # The walking surface is y=0 because its solid ground blocks occupy y=-1..0.
    for x in range(-16, 32):
        for z in range(-16, 32):
            world.set_block(x, -1, z, "grass")

    # A single jump-height obstacle near the spawn.
    world.set_block(6, 0, 2, "stone")

    # A three-block-high occluding wall.
    for y in range(0, 3):
        for z in range(-3, 9):
            world.set_block(10, y, z, "stone")

    # Elevated platform and a block staircase on its far side.
    for x in range(14, 20):
        for z in range(1, 8):
            world.set_block(x, 2, z, "wood")
    world.set_block(13, 0, 7, "stone")
    world.set_block(14, 1, 7, "stone")
    return world
