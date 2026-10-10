"""Tile-map creation and terrain queries."""

import math
import random

from .models import MapRequest, TileMap, Vector


WALL = "wall"
FLOOR = "floor"
OBSTACLE = "obstacle"
START_ROOM_LEFT = 4
START_ROOM_TOP = 4
START_ROOM_RIGHT = 14
START_ROOM_BOTTOM = 12
VIEW_WIDTH_TILES = 30
VIEW_HEIGHT_TILES = 20


def generate_map(request: MapRequest) -> TileMap:
    if request.generator_name == "room":
        return generate_room_map(request)
    raise ValueError(f"Unknown map generator: {request.generator_name}")


def generate_room_map(request: MapRequest) -> TileMap:
    if request.width < 5 or request.height < 5:
        raise ValueError("A room must be at least 5 by 5 tiles.")

    tiles = [[FLOOR for _ in range(request.width)] for _ in range(request.height)]
    for x in range(request.width):
        tiles[0][x] = WALL
        tiles[request.height - 1][x] = WALL
    for y in range(request.height):
        tiles[y][0] = WALL
        tiles[y][request.width - 1] = WALL

    randomizer = random.Random(request.seed)
    for y in range(1, request.height - 1):
        for x in range(1, request.width - 1):
            if randomizer.random() < 0.055:
                tiles[y][x] = OBSTACLE
    add_starting_room(tiles, request.width, request.height)

    return TileMap(
        width=request.width,
        height=request.height,
        tiles=tiles,
        seed=request.seed,
        generator_name=request.generator_name,
    )


def add_starting_room(tiles: list[list[str]], width: int, height: int) -> None:
    """Carve a fixed, enclosed player room with one south-facing exit."""
    if width <= START_ROOM_RIGHT + 1 or height <= START_ROOM_BOTTOM + 1:
        return
    for y in range(START_ROOM_TOP, START_ROOM_BOTTOM + 1):
        for x in range(START_ROOM_LEFT, START_ROOM_RIGHT + 1):
            is_border = x in (START_ROOM_LEFT, START_ROOM_RIGHT) or y in (START_ROOM_TOP, START_ROOM_BOTTOM)
            tiles[y][x] = WALL if is_border else FLOOR
    door_x = (START_ROOM_LEFT + START_ROOM_RIGHT) // 2
    tiles[START_ROOM_BOTTOM][door_x] = FLOOR
    for y in range(START_ROOM_BOTTOM + 1, height - 1):
        tiles[y][door_x] = FLOOR


def tile_at(tile_map: TileMap, position: Vector) -> str:
    x = math.floor(position.x)
    y = math.floor(position.y)
    if x < 0 or x >= tile_map.width:
        return WALL
    if y < 0 or y >= tile_map.height:
        return WALL
    return tile_map.tiles[y][x]


def is_walkable(tile_map: TileMap, position: Vector) -> bool:
    return tile_at(tile_map, position) == FLOOR


def can_occupy(tile_map: TileMap, position: Vector, radius: float = 0.3) -> bool:
    """Return whether a square actor centred at position avoids solid tiles."""
    corners = (
        Vector(position.x - radius, position.y - radius),
        Vector(position.x + radius, position.y - radius),
        Vector(position.x - radius, position.y + radius),
        Vector(position.x + radius, position.y + radius),
    )
    return all(is_walkable(tile_map, corner) for corner in corners)


def choose_start_positions(tile_map: TileMap, seed: int) -> tuple[Vector, Vector]:
    """Choose deterministic player and pistol positions in the same open region."""
    floors = [
        Vector(float(x), float(y))
        for y in range(tile_map.height)
        for x in range(tile_map.width)
        if is_walkable(tile_map, Vector(float(x), float(y)))
    ]
    if len(floors) < 2:
        raise ValueError("Map does not have enough floor tiles for starting entities.")
    randomizer = random.Random(seed + 1)
    player_cell = randomizer.choice(floors)
    reachable_cells = find_reachable_floor_cells(tile_map, player_cell)
    if len(reachable_cells) < 2:
        raise ValueError("Player spawn has no reachable tile for the pistol.")
    pistol_cell = randomizer.choice([cell for cell in reachable_cells if cell != player_cell])
    return center_of_cell(player_cell), center_of_cell(pistol_cell)


def center_of_cell(cell: Vector) -> Vector:
    return Vector(cell.x + 0.5, cell.y + 0.5)


def find_reachable_floor_cells(tile_map: TileMap, start: Vector) -> list[Vector]:
    start_cell = (math.floor(start.x), math.floor(start.y))
    frontier = [start_cell]
    visited = {start_cell}
    while frontier:
        x, y = frontier.pop()
        for next_cell in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if next_cell in visited:
                continue
            next_position = Vector(float(next_cell[0]), float(next_cell[1]))
            if is_walkable(tile_map, next_position):
                visited.add(next_cell)
                frontier.append(next_cell)
    return [Vector(float(x), float(y)) for x, y in visited]


def starting_room_positions(tile_map: TileMap) -> tuple[Vector, Vector]:
    """Return the fixed player and pistol positions, or a small-map fallback."""
    if tile_map.width > START_ROOM_RIGHT + 1 and tile_map.height > START_ROOM_BOTTOM + 1:
        return Vector(9.5, 7.5), Vector(11.5, 7.5)
    return choose_start_positions(tile_map, tile_map.seed)


def is_outside_starting_room(position: Vector) -> bool:
    return not (
        START_ROOM_LEFT <= position.x <= START_ROOM_RIGHT + 1
        and START_ROOM_TOP <= position.y <= START_ROOM_BOTTOM + 1
    )


def choose_enemy_spawn_positions(tile_map: TileMap, player_position: Vector, randomizer: random.Random) -> list[Vector]:
    reachable = find_reachable_floor_cells(tile_map, player_position)
    candidates = [
        center_of_cell(cell)
        for cell in reachable
        if is_outside_starting_room(cell) and math.dist((cell.x, cell.y), (player_position.x, player_position.y)) >= 10
    ]
    visible_candidates = [
        position for position in candidates if is_on_players_screen(tile_map, player_position, position)
    ]
    if len(visible_candidates) >= 2:
        candidates = visible_candidates
    if len(candidates) < 2:
        candidates = [center_of_cell(cell) for cell in reachable if center_of_cell(cell) != player_position]
    if len(candidates) < 2:
        raise ValueError("Map does not have two reachable enemy spawn positions.")
    return randomizer.sample(candidates, 2)


def move_with_collision(
    tile_map: TileMap, position: Vector, direction: Vector, speed: float, dt: float, radius: float = 0.3
) -> Vector:
    distance = speed * dt
    horizontal = Vector(position.x + direction.x * distance, position.y)
    if can_occupy(tile_map, horizontal, radius):
        position = horizontal
    vertical = Vector(position.x, position.y + direction.y * distance)
    if can_occupy(tile_map, vertical, radius):
        position = vertical
    return position


def camera_origin_for(tile_map: TileMap, center: Vector) -> Vector:
    return Vector(
        max(0, min(tile_map.width - VIEW_WIDTH_TILES, center.x - VIEW_WIDTH_TILES / 2)),
        max(0, min(tile_map.height - VIEW_HEIGHT_TILES, center.y - VIEW_HEIGHT_TILES / 2)),
    )


def is_on_players_screen(tile_map: TileMap, player_position: Vector, position: Vector) -> bool:
    camera = camera_origin_for(tile_map, player_position)
    return (
        camera.x <= position.x <= camera.x + VIEW_WIDTH_TILES
        and camera.y <= position.y <= camera.y + VIEW_HEIGHT_TILES
    )
