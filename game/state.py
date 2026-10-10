"""Game construction and frontend-safe state snapshots."""

import random

from .items import get_item_definition
from .models import Enemy, FloorItem, Game, ItemInstance, MapRequest, Player, Vector
from .world import choose_enemy_spawn_positions, generate_map, starting_room_positions


INVENTORY_CAPACITY = 8


def create_game(request: MapRequest | None = None) -> Game:
    request = request or MapRequest()
    tile_map = generate_map(request)
    player_position, pistol_position = starting_room_positions(tile_map)
    pistol_item = ItemInstance(id=2, definition_key="pistol")
    pistol_floor_item = FloorItem(id=3, item_id=pistol_item.id, position=pistol_position)
    player = Player(id=1, position=player_position)
    game = Game(
        tile_map=tile_map,
        player=player,
        item_instances={pistol_item.id: pistol_item},
        floor_items={pistol_floor_item.id: pistol_floor_item},
        next_entity_id=4,
        randomizer=random.Random(request.seed + 2),
    )
    add_starting_enemies(game)
    return game


def add_starting_enemies(game: Game) -> None:
    for position in choose_enemy_spawn_positions(game.tile_map, game.player.position, game.randomizer):
        enemy = Enemy(id=game.next_entity_id, position=position)
        game.enemies[enemy.id] = enemy
        game.next_entity_id += 1


def spawn_floor_item(game: Game, definition_key: str, position: Vector) -> FloorItem:
    item = ItemInstance(id=game.next_entity_id, definition_key=definition_key)
    game.next_entity_id += 1
    floor_item = FloorItem(id=game.next_entity_id, item_id=item.id, position=position)
    game.next_entity_id += 1
    game.item_instances[item.id] = item
    game.floor_items[floor_item.id] = floor_item
    return floor_item


def add_message(game: Game, message: str) -> None:
    game.messages.append(message)
    del game.messages[:-4]


def game_snapshot(game: Game) -> dict:
    inventory = []
    for item_id in game.player.inventory:
        item = game.item_instances[item_id]
        definition = get_item_definition(item.definition_key)
        inventory.append({"id": item.id, "name": definition.name, "kind": definition.kind, "key": definition.key})

    floor_items = []
    for floor_item in game.floor_items.values():
        item = game.item_instances[floor_item.item_id]
        definition = get_item_definition(item.definition_key)
        floor_items.append(
            {
                "id": floor_item.id,
                "name": definition.name,
                "kind": definition.kind,
                "key": definition.key,
                "x": floor_item.position.x,
                "y": floor_item.position.y,
            }
        )

    return {
        "map": {"width": game.tile_map.width, "height": game.tile_map.height, "tiles": game.tile_map.tiles},
        "player": {
            "x": game.player.position.x,
            "y": game.player.position.y,
            "health": game.player.health,
            "max_health": game.player.max_health,
            "armor": game.player.armor,
            "xp": game.player.xp,
            "level": game.player.level,
            "inventory": inventory,
            "equipped_item_id": game.player.equipped_item_id,
            "movement_x": game.player.movement.x,
            "movement_y": game.player.movement.y,
        },
        "floor_items": floor_items,
        "projectiles": [
            {"x": projectile.x, "y": projectile.y}
            for projectile in game.projectiles.values()
        ],
        "enemies": [
            {"id": enemy.id, "x": enemy.position.x, "y": enemy.position.y, "health": enemy.health, "max_health": enemy.max_health}
            for enemy in game.enemies.values()
        ],
        "messages": game.messages,
    }
