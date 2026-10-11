"""Player movement, inventory, equipment, and progression rules."""

import math

from .items import is_equippable
from .items import get_item_definition
from .models import Game, Vector
from .state import INVENTORY_CAPACITY, add_message
from .world import can_occupy, nearby_level_exit_direction, open_nearby_door


DIRECTIONS = {
    "up": Vector(0, -1),
    "down": Vector(0, 1),
    "left": Vector(-1, 0),
    "right": Vector(1, 0),
}
PLAYER_SPEED_TILES_PER_SECOND = 6.0
PICKUP_DISTANCE = 0.8


def move_player(game: Game, direction: str) -> bool:
    offset = DIRECTIONS.get(direction)
    if offset is None:
        add_message(game, "Unknown direction.")
        return False

    current = game.player.position
    destination = Vector(current.x + offset.x, current.y + offset.y)
    if not can_occupy(game.tile_map, destination):
        return False
    game.player.position = destination
    return True


def set_player_movement(game: Game, x: float, y: float) -> bool:
    """Store normalized player input for the fixed-step simulation."""
    length = math.hypot(x, y)
    if length > 1:
        x /= length
        y /= length
    game.player.movement = Vector(x, y)
    return True


def step_player_movement(game: Game, dt: float) -> None:
    movement = game.player.movement
    if movement.x == 0 and movement.y == 0:
        return
    current = game.player.position
    distance = PLAYER_SPEED_TILES_PER_SECOND * dt
    horizontal = Vector(current.x + movement.x * distance, current.y)
    if can_occupy(game.tile_map, horizontal):
        current = horizontal
    vertical = Vector(current.x, current.y + movement.y * distance)
    if can_occupy(game.tile_map, vertical):
        current = vertical
    game.player.position = current


def pick_up_item(game: Game, announce_when_empty: bool = True) -> bool:
    player_position = game.player.position
    matching_item = min(
        game.floor_items.values(),
        key=lambda item: math.dist(
            (item.position.x, item.position.y), (player_position.x, player_position.y)
        ),
        default=None,
    )
    if matching_item is None or math.dist(
        (matching_item.position.x, matching_item.position.y),
        (player_position.x, player_position.y),
    ) > PICKUP_DISTANCE:
        if announce_when_empty:
            add_message(game, "Nothing here to pick up.")
        return False

    item = game.item_instances[matching_item.item_id]
    definition = get_item_definition(item.definition_key)
    if definition.kind == "consumable":
        game.player.health = min(game.player.max_health, game.player.health + definition.healing)
        del game.floor_items[matching_item.id]
        add_message(game, f"Recovered {definition.healing} health.")
        return True
    if len(game.player.inventory) >= INVENTORY_CAPACITY:
        add_message(game, "Inventory is full.")
        return False

    game.player.inventory.append(matching_item.item_id)
    del game.floor_items[matching_item.id]
    if definition.equippable:
        game.player.equipped_item_id = matching_item.item_id
        add_message(game, f"Picked up and equipped {definition.name}.")
    else:
        add_message(game, f"Picked up {definition.name}.")
    return True


def interact_player(game: Game) -> bool:
    """Pick up a nearby item, or open a nearby door when there is no item."""
    if pick_up_item(game, announce_when_empty=False):
        return True
    if open_nearby_door(game.tile_map, game.player.position):
        add_message(game, "Opened door.")
        return True
    exit_direction = nearby_level_exit_direction(game.tile_map, game.player.position)
    if exit_direction is not None:
        add_message(game, f"The {exit_direction} exit has no level connected yet.")
        return True
    add_message(game, "Nothing nearby to interact with.")
    return False


def equip_item(game: Game, item_id: int | None = None) -> bool:
    if item_id is None:
        equippable_ids = [
            inventory_item_id
            for inventory_item_id in game.player.inventory
            if is_equippable(game.item_instances[inventory_item_id].definition_key)
        ]
        if game.player.equipped_item_id in equippable_ids and len(equippable_ids) > 1:
            equipped_index = equippable_ids.index(game.player.equipped_item_id)
            item_id = equippable_ids[(equipped_index + 1) % len(equippable_ids)]
        elif equippable_ids:
            item_id = equippable_ids[0]
    if item_id is None or item_id not in game.player.inventory:
        add_message(game, "That item is not in your inventory.")
        return False

    item = game.item_instances[item_id]
    if not is_equippable(item.definition_key):
        add_message(game, "That item cannot be equipped.")
        return False
    if game.player.equipped_item_id == item_id:
        game.player.equipped_item_id = None
        add_message(game, f"Unequipped {item.definition_key}.")
    else:
        game.player.equipped_item_id = item_id
        add_message(game, f"Equipped {item.definition_key}.")
    return True


def damage_after_armor(raw_damage: int, armor: int) -> int:
    return max(1, raw_damage - armor)


def apply_damage_to_player(game: Game, raw_damage: int) -> int:
    if game.game_over:
        return 0
    damage = damage_after_armor(raw_damage, game.player.armor)
    game.player.health = max(0, game.player.health - damage)
    if game.player.health == 0:
        game.game_over = True
        add_message(game, "Game over.")
    return damage


def grant_xp(game: Game, amount: int) -> None:
    if amount > 0:
        game.player.xp += amount
