"""Game construction, persistent world locations, transitions, and snapshots."""

import random

from .items import get_item_definition
from .models import Enemy, FloorItem, Game, ItemInstance, MapLocation, MapRequest, Player, Vector
from .world import MAP_TYPES, choose_enemy_spawn_positions, generate_map, starting_room_positions


INVENTORY_CAPACITY = 8
LOCATION_DELTAS = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}


def create_game(request: MapRequest | None = None) -> Game:
    request = request or MapRequest(generator_name="prefab")
    tile_map = generate_map(request)
    player_position, pistol_position = starting_room_positions(tile_map)
    pistol_item = ItemInstance(id=2, definition_key="pistol")
    pistol_floor_item = FloorItem(id=3, item_id=pistol_item.id, position=pistol_position)
    game = Game(
        tile_map=tile_map,
        player=Player(id=1, position=player_position),
        item_instances={pistol_item.id: pistol_item},
        floor_items={pistol_floor_item.id: pistol_floor_item},
        next_entity_id=4,
        randomizer=random.Random(request.seed + 2),
    )
    add_enemies(game, 2)
    add_building_pickups(game)
    game.world_locations[(0, 0)] = MapLocation(tile_map, game.floor_items, game.enemies)
    return game


def add_enemies(game: Game, count: int) -> None:
    for position in choose_enemy_spawn_positions(game.tile_map, game.player.position, game.randomizer, count):
        enemy = Enemy(id=game.next_entity_id, position=position)
        game.enemies[enemy.id] = enemy
        game.next_entity_id += 1


def add_building_pickups(game: Game) -> None:
    for building in game.tile_map.buildings:
        if building.has_door and game.randomizer.random() < 0.1:
            x, y = game.randomizer.choice(building.interior_cells)
            spawn_floor_item(game, game.randomizer.choice(("health_up", "rifle")), Vector(x + 0.5, y + 0.5))


def spawn_floor_item(game: Game, definition_key: str, position: Vector) -> FloorItem:
    item = ItemInstance(id=game.next_entity_id, definition_key=definition_key)
    game.next_entity_id += 1
    floor_item = FloorItem(id=game.next_entity_id, item_id=item.id, position=position)
    game.next_entity_id += 1
    game.item_instances[item.id] = item
    game.floor_items[floor_item.id] = floor_item
    return floor_item


def travel_to(game: Game, direction: str) -> bool:
    delta = LOCATION_DELTAS.get(direction)
    if delta is None:
        return False
    target = (game.world_position[0] + delta[0], game.world_position[1] + delta[1])
    game.enemy_count_for_new_locations += 1
    if target not in game.world_locations:
        create_location(game, target, direction)
    location = game.world_locations[target]
    game.tile_map = location.tile_map
    game.floor_items = location.floor_items
    game.enemies = location.enemies
    game.world_position = target
    game.player.position = entry_position(game.tile_map, direction)
    game.player.movement = Vector(0.0, 0.0)
    game.projectiles.clear()
    add_message(game, f"Entered {game.tile_map.generator_name} map at {target}.")
    return True


def create_location(game: Game, coordinate: tuple[int, int], entry_direction: str) -> None:
    map_type = game.randomizer.choice(MAP_TYPES)
    request = MapRequest(
        width=game.tile_map.width,
        height=game.tile_map.height,
        seed=game.randomizer.randrange(1, 2**31),
        generator_name=map_type,
    )
    tile_map = generate_map(request)
    game.tile_map = tile_map
    game.floor_items = {}
    game.enemies = {}
    game.player.position = entry_position(tile_map, entry_direction)
    add_enemies(game, game.enemy_count_for_new_locations)
    add_building_pickups(game)
    game.world_locations[coordinate] = MapLocation(tile_map, game.floor_items, game.enemies)


def entry_position(tile_map, direction: str) -> Vector:
    if direction == "north":
        return Vector(tile_map.width // 2 + 0.5, tile_map.height - 2.5)
    if direction == "south":
        return Vector(tile_map.width // 2 + 0.5, 1.5)
    if direction == "west":
        return Vector(tile_map.width - 2.5, tile_map.height // 2 + 0.5)
    return Vector(1.5, tile_map.height // 2 + 0.5)


def reset_game(game: Game) -> None:
    request = MapRequest(game.tile_map.width, game.tile_map.height, game.tile_map.seed, "prefab")
    fresh_game = create_game(request)
    fresh_game.messages.append("New run started.")
    game.__dict__.update(fresh_game.__dict__)


def add_message(game: Game, message: str) -> None:
    game.messages.append(message)
    del game.messages[:-4]


def game_snapshot(game: Game) -> dict:
    inventory = [
        {"id": item.id, "name": get_item_definition(item.definition_key).name, "kind": get_item_definition(item.definition_key).kind, "key": item.definition_key}
        for item_id in game.player.inventory
        for item in [game.item_instances[item_id]]
    ]
    floor_items = [
        {"id": floor_item.id, "name": get_item_definition(game.item_instances[floor_item.item_id].definition_key).name, "kind": get_item_definition(game.item_instances[floor_item.item_id].definition_key).kind, "key": game.item_instances[floor_item.item_id].definition_key, "x": floor_item.position.x, "y": floor_item.position.y}
        for floor_item in game.floor_items.values()
    ]
    return {
        "map": {"width": game.tile_map.width, "height": game.tile_map.height, "tiles": game.tile_map.tiles, "type": game.tile_map.generator_name},
        "world_position": {"x": game.world_position[0], "y": game.world_position[1], "known_locations": len(game.world_locations)},
        "player": {"x": game.player.position.x, "y": game.player.position.y, "health": game.player.health, "max_health": game.player.max_health, "armor": game.player.armor, "xp": game.player.xp, "level": game.player.level, "inventory": inventory, "equipped_item_id": game.player.equipped_item_id, "movement_x": game.player.movement.x, "movement_y": game.player.movement.y},
        "floor_items": floor_items,
        "projectiles": [{"x": projectile.x, "y": projectile.y} for projectile in game.projectiles.values()],
        "enemies": [{"id": enemy.id, "x": enemy.position.x, "y": enemy.position.y, "health": enemy.health, "max_health": enemy.max_health, "mode": enemy.mode} for enemy in game.enemies.values()],
        "messages": game.messages,
        "game_over": game.game_over,
    }
