"""Map generators, terrain queries, prefab placement, and map-exit helpers."""

import math
import random

from .models import Building, MapRequest, TileMap, Vector


WALL = "wall"
FLOOR = "floor"
TREE = "tree"
DOOR_CLOSED = "door_closed"
LEVEL_EXIT = "level_exit"
START_ROOM_LEFT = 4
START_ROOM_TOP = 4
START_ROOM_RIGHT = 14
START_ROOM_BOTTOM = 12
VIEW_WIDTH_TILES = 30
VIEW_HEIGHT_TILES = 20
PREFAB_KINDS = ("square", "l")
PREFAB_BUILDING_COUNT = 8
MAP_TYPES = ("prefab", "neighborhood", "forest")


def generate_map(request: MapRequest) -> TileMap:
    generator = "prefab" if request.generator_name == "room" else request.generator_name
    if generator not in MAP_TYPES:
        raise ValueError(f"Unknown map generator: {request.generator_name}")
    if request.width < 20 or request.height < 16:
        return generate_small_test_map(request, generator)

    tiles = make_empty_tiles(request.width, request.height)
    add_starting_room(tiles, request.width, request.height)
    randomizer = random.Random(request.seed)
    if generator == "prefab":
        buildings = place_scattered_prefabs(tiles, request.width, request.height, randomizer)
    elif generator == "neighborhood":
        buildings = place_neighborhood_prefabs(tiles, request.width, request.height, randomizer)
    else:
        buildings = []
        place_forest(tiles, request.width, request.height, randomizer)
    add_level_exits(tiles, request.width, request.height)
    return TileMap(
        width=request.width,
        height=request.height,
        tiles=tiles,
        seed=request.seed,
        generator_name=generator,
        prefab_kinds=[building.kind for building in buildings],
        buildings=buildings,
    )


def generate_small_test_map(request: MapRequest, generator: str) -> TileMap:
    tiles = make_empty_tiles(request.width, request.height)
    return TileMap(request.width, request.height, tiles, request.seed, generator)


def make_empty_tiles(width: int, height: int) -> list[list[str]]:
    tiles = [[FLOOR for _ in range(width)] for _ in range(height)]
    for x in range(width):
        tiles[0][x] = WALL
        tiles[height - 1][x] = WALL
    for y in range(height):
        tiles[y][0] = WALL
        tiles[y][width - 1] = WALL
    return tiles


def add_starting_room(tiles: list[list[str]], width: int, height: int) -> None:
    for y in range(START_ROOM_TOP, START_ROOM_BOTTOM + 1):
        for x in range(START_ROOM_LEFT, START_ROOM_RIGHT + 1):
            is_border = x in (START_ROOM_LEFT, START_ROOM_RIGHT) or y in (START_ROOM_TOP, START_ROOM_BOTTOM)
            tiles[y][x] = WALL if is_border else FLOOR
    door_x = (START_ROOM_LEFT + START_ROOM_RIGHT) // 2
    tiles[START_ROOM_BOTTOM][door_x] = DOOR_CLOSED
    for y in range(START_ROOM_BOTTOM + 1, height - 1):
        tiles[y][door_x] = FLOOR


def place_scattered_prefabs(
    tiles: list[list[str]], width: int, height: int, randomizer: random.Random
) -> list[Building]:
    buildings: list[Building] = []
    occupied = starting_building_cells(width, height)
    for index in range(PREFAB_BUILDING_COUNT):
        kind = PREFAB_KINDS[index % len(PREFAB_KINDS)]
        building = try_place_prefab(tiles, width, height, kind, occupied, randomizer)
        if building is not None:
            buildings.append(building)
    return buildings


def place_neighborhood_prefabs(
    tiles: list[list[str]], width: int, height: int, randomizer: random.Random
) -> list[Building]:
    """Populate a loose grid, with each lot independently choosing a prefab."""
    buildings: list[Building] = []
    occupied = starting_building_cells(width, height)
    lot_size = 14
    for lot_y in range(2, height - 2, lot_size):
        for lot_x in range(2, width - 2, lot_size):
            if randomizer.random() > 0.7:
                continue
            kind = randomizer.choice(PREFAB_KINDS)
            building = try_place_prefab(
                tiles, width, height, kind, occupied, randomizer, (lot_x, lot_y, lot_size, lot_size)
            )
            if building is not None:
                buildings.append(building)
    return buildings


def try_place_prefab(
    tiles: list[list[str]],
    width: int,
    height: int,
    kind: str,
    occupied: set[tuple[int, int]],
    randomizer: random.Random,
    lot: tuple[int, int, int, int] | None = None,
) -> Building | None:
    interior = make_prefab_interior(kind, randomizer)
    walls = prefab_wall_cells(interior)
    local_cells = interior | walls
    max_x = max(x for x, _ in local_cells)
    max_y = max(y for _, y in local_cells)
    for _ in range(100):
        if lot is None:
            origin_x = randomizer.randint(2, width - 3)
            origin_y = randomizer.randint(2, height - 3)
        else:
            lot_x, lot_y, lot_width, lot_height = lot
            origin_x = randomizer.randint(lot_x, min(width - 3, lot_x + lot_width - 2))
            origin_y = randomizer.randint(lot_y, min(height - 3, lot_y + lot_height - 2))
        if origin_x + max_x >= width - 1 or origin_y + max_y >= height - 1:
            continue
        if not prefab_fits(tiles, origin_x, origin_y, local_cells, occupied):
            continue
        has_door = randomizer.random() < 0.5
        place_prefab(tiles, origin_x, origin_y, interior, walls, has_door, randomizer)
        translated_cells = [(origin_x + x, origin_y + y) for x, y in interior]
        occupied.update((origin_x + x, origin_y + y) for x, y in local_cells)
        return Building(kind=kind, interior_cells=translated_cells, has_door=has_door)
    return None


def make_prefab_interior(kind: str, randomizer: random.Random) -> set[tuple[int, int]]:
    if kind == "square":
        width = randomizer.randint(4, 7)
        height = randomizer.randint(4, 7)
        return {(x, y) for y in range(height) for x in range(width)}
    width = randomizer.randint(7, 10)
    height = randomizer.randint(7, 10)
    arm_width = randomizer.randint(3, 4)
    arm_height = randomizer.randint(3, 4)
    vertical_arm = {(x, y) for y in range(height) for x in range(arm_width)}
    horizontal_arm = {(x, y) for y in range(height - arm_height, height) for x in range(width)}
    return vertical_arm | horizontal_arm


def prefab_wall_cells(interior: set[tuple[int, int]]) -> set[tuple[int, int]]:
    walls = set()
    for x, y in interior:
        for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if neighbor not in interior:
                walls.add(neighbor)
    return walls


def prefab_fits(
    tiles: list[list[str]], origin_x: int, origin_y: int, cells: set[tuple[int, int]], occupied: set[tuple[int, int]]
) -> bool:
    for local_x, local_y in cells:
        x, y = origin_x + local_x, origin_y + local_y
        if tiles[y][x] != FLOOR or (x, y) in occupied or is_starting_exit_corridor(x, y):
            return False
    return True


def place_prefab(
    tiles: list[list[str]],
    origin_x: int,
    origin_y: int,
    interior: set[tuple[int, int]],
    walls: set[tuple[int, int]],
    has_door: bool,
    randomizer: random.Random,
) -> None:
    for x, y in walls:
        tiles[origin_y + y][origin_x + x] = WALL
    for x, y in interior:
        tiles[origin_y + y][origin_x + x] = FLOOR
    if has_door:
        door_x, door_y = randomizer.choice(sorted(walls))
        tiles[origin_y + door_y][origin_x + door_x] = DOOR_CLOSED


def place_forest(tiles: list[list[str]], width: int, height: int, randomizer: random.Random) -> None:
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            if tiles[y][x] == FLOOR and not is_starting_exit_corridor(x, y) and randomizer.random() < 0.075:
                tiles[y][x] = TREE


def starting_building_cells(width: int, height: int) -> set[tuple[int, int]]:
    return {
        (x, y)
        for y in range(START_ROOM_TOP, min(height, START_ROOM_BOTTOM + 1))
        for x in range(START_ROOM_LEFT, min(width, START_ROOM_RIGHT + 1))
    }


def is_starting_exit_corridor(x: int, y: int) -> bool:
    return x == (START_ROOM_LEFT + START_ROOM_RIGHT) // 2 and y >= START_ROOM_BOTTOM


def add_level_exits(tiles: list[list[str]], width: int, height: int) -> None:
    exits = ((width // 2, 0, 0, 1), (width // 2, height - 1, 0, -1), (0, height // 2, 1, 0), (width - 1, height // 2, -1, 0))
    for x, y, inward_x, inward_y in exits:
        tiles[y][x] = LEVEL_EXIT
        tiles[y + inward_y][x + inward_x] = FLOOR
        tiles[y + inward_y * 2][x + inward_x * 2] = FLOOR


def tile_at(tile_map: TileMap, position: Vector) -> str:
    x, y = math.floor(position.x), math.floor(position.y)
    if x < 0 or x >= tile_map.width or y < 0 or y >= tile_map.height:
        return WALL
    return tile_map.tiles[y][x]


def is_walkable(tile_map: TileMap, position: Vector) -> bool:
    return tile_at(tile_map, position) == FLOOR


def can_occupy(tile_map: TileMap, position: Vector, radius: float = 0.3) -> bool:
    corners = (
        Vector(position.x - radius, position.y - radius), Vector(position.x + radius, position.y - radius),
        Vector(position.x - radius, position.y + radius), Vector(position.x + radius, position.y + radius),
    )
    return all(is_walkable(tile_map, corner) for corner in corners)


def open_nearby_door(tile_map: TileMap, position: Vector, interaction_range: float = 1.25) -> bool:
    nearest: tuple[int, int] | None = None
    nearest_distance = interaction_range
    for y, row in enumerate(tile_map.tiles):
        for x, tile in enumerate(row):
            if tile != DOOR_CLOSED:
                continue
            distance = math.dist((position.x, position.y), (x + 0.5, y + 0.5))
            if distance <= nearest_distance:
                nearest, nearest_distance = (x, y), distance
    if nearest is None:
        return False
    tile_map.tiles[nearest[1]][nearest[0]] = FLOOR
    return True


def nearby_level_exit_direction(tile_map: TileMap, position: Vector, interaction_range: float = 1.25) -> str | None:
    exits = {
        (tile_map.width // 2, 0): "north", (tile_map.width // 2, tile_map.height - 1): "south",
        (0, tile_map.height // 2): "west", (tile_map.width - 1, tile_map.height // 2): "east",
    }
    for (x, y), direction in exits.items():
        if math.dist((position.x, position.y), (x + 0.5, y + 0.5)) <= interaction_range:
            return direction
    return None


def has_walkable_path(tile_map: TileMap, start: Vector, destination: Vector) -> bool:
    start_cell = (math.floor(start.x), math.floor(start.y))
    destination_cell = (math.floor(destination.x), math.floor(destination.y))
    if not is_walkable(tile_map, start) or not is_walkable(tile_map, destination):
        return False
    frontier = [start_cell]
    visited = {start_cell}
    while frontier:
        x, y = frontier.pop()
        if (x, y) == destination_cell:
            return True
        for next_cell in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if next_cell not in visited and is_walkable(tile_map, Vector(float(next_cell[0]), float(next_cell[1]))):
                visited.add(next_cell)
                frontier.append(next_cell)
    return False


def find_reachable_floor_cells(tile_map: TileMap, start: Vector) -> list[Vector]:
    start_cell = (math.floor(start.x), math.floor(start.y))
    frontier = [start_cell]
    visited = {start_cell}
    while frontier:
        x, y = frontier.pop()
        for next_cell in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if next_cell not in visited and is_walkable(tile_map, Vector(float(next_cell[0]), float(next_cell[1]))):
                visited.add(next_cell)
                frontier.append(next_cell)
    return [Vector(float(x), float(y)) for x, y in visited]


def choose_start_positions(tile_map: TileMap, seed: int) -> tuple[Vector, Vector]:
    floors = [Vector(float(x), float(y)) for y in range(tile_map.height) for x in range(tile_map.width) if is_walkable(tile_map, Vector(float(x), float(y)))]
    randomizer = random.Random(seed + 1)
    player_cell, pistol_cell = randomizer.sample(floors, 2)
    return center_of_cell(player_cell), center_of_cell(pistol_cell)


def starting_room_positions(tile_map: TileMap) -> tuple[Vector, Vector]:
    if tile_map.width >= 20 and tile_map.height >= 16:
        return Vector(9.5, 7.5), Vector(11.5, 7.5)
    return choose_start_positions(tile_map, tile_map.seed)


def center_of_cell(cell: Vector) -> Vector:
    return Vector(cell.x + 0.5, cell.y + 0.5)


def is_outside_starting_room(position: Vector) -> bool:
    return not (START_ROOM_LEFT <= position.x <= START_ROOM_RIGHT + 1 and START_ROOM_TOP <= position.y <= START_ROOM_BOTTOM + 1)


def choose_enemy_spawn_positions(tile_map: TileMap, player_position: Vector, randomizer: random.Random, count: int = 2) -> list[Vector]:
    candidates = [
        Vector(x + 0.5, y + 0.5)
        for y in range(1, tile_map.height - 1)
        for x in range(1, tile_map.width - 1)
        if is_walkable(tile_map, Vector(float(x), float(y)))
        and is_outside_starting_room(Vector(float(x), float(y)))
        and math.dist((x + 0.5, y + 0.5), (player_position.x, player_position.y)) >= 8
    ]
    if len(candidates) < count:
        candidates = [
            Vector(x + 0.5, y + 0.5)
            for y in range(1, tile_map.height - 1)
            for x in range(1, tile_map.width - 1)
            if is_walkable(tile_map, Vector(float(x), float(y)))
            and (x + 0.5, y + 0.5) != (player_position.x, player_position.y)
        ]
    if len(candidates) < count:
        raise ValueError("Map does not have enough enemy spawn positions.")
    return randomizer.sample(candidates, count)


def move_with_collision(tile_map: TileMap, position: Vector, direction: Vector, speed: float, dt: float, radius: float = 0.3) -> Vector:
    distance = speed * dt
    horizontal = Vector(position.x + direction.x * distance, position.y)
    if can_occupy(tile_map, horizontal, radius):
        position = horizontal
    vertical = Vector(position.x, position.y + direction.y * distance)
    if can_occupy(tile_map, vertical, radius):
        position = vertical
    return position


def camera_origin_for(tile_map: TileMap, center: Vector) -> Vector:
    return Vector(max(0, min(tile_map.width - VIEW_WIDTH_TILES, center.x - VIEW_WIDTH_TILES / 2)), max(0, min(tile_map.height - VIEW_HEIGHT_TILES, center.y - VIEW_HEIGHT_TILES / 2)))


def is_on_players_screen(tile_map: TileMap, player_position: Vector, position: Vector) -> bool:
    camera = camera_origin_for(tile_map, player_position)
    return camera.x <= position.x <= camera.x + VIEW_WIDTH_TILES and camera.y <= position.y <= camera.y + VIEW_HEIGHT_TILES
