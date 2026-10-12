"""One interaction and inventory path for all item entity definitions."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .blocks import AIR_BLOCK_KEY
from .components import Consumable, Equipment, Health, Hunger, Inventory, Item, Pickup, Transform, Weapon

if TYPE_CHECKING:
    from .ecs import Entity
    from .runtime import GameRuntime


PICKUP_DISTANCE = 1.25
DOOR_INTERACTION_DISTANCE = 1.75


def _apply_immediate_consumable(runtime: GameRuntime, player, item) -> bool:
    consumable = item.get(Consumable)
    if consumable is None or consumable.effect != "heal":
        return False
    health = player.require(Health)
    health.current = min(health.maximum, health.current + int(consumable.amount))
    runtime.entities.remove(item.id)
    runtime.add_message(f"Recovered {int(consumable.amount)} health.")
    return True


def _nearest_pickup(runtime: GameRuntime, player_position) -> Entity | None:
    candidates = []
    for entity in runtime.entities.query(Transform, Pickup, Item):
        position = entity.require(Transform).position
        distance = math.dist(
            (player_position.x, player_position.y, player_position.z),
            (position.x, position.y, position.z),
        )
        if distance <= PICKUP_DISTANCE:
            candidates.append((distance, entity.id, entity))
    return min(candidates, default=(None, None, None))[2]


def _open_nearby_door(runtime: GameRuntime, player_position) -> bool:
    nearest: tuple[float, int, int] | None = None
    radius = math.ceil(DOOR_INTERACTION_DISTANCE)
    center_x = math.floor(player_position.x)
    center_z = math.floor(player_position.z)
    for x in range(center_x - radius, center_x + radius + 1):
        for z in range(center_z - radius, center_z + radius + 1):
            if not any(runtime.world.get_block(x, y, z) == "door" for y in range(3)):
                continue
            distance = math.hypot(x + 0.5 - player_position.x, z + 0.5 - player_position.z)
            if distance <= DOOR_INTERACTION_DISTANCE and (
                nearest is None or distance < nearest[0]
            ):
                nearest = (distance, x, z)
    if nearest is None:
        return False
    _, door_x, door_z = nearest
    for y in range(3):
        if runtime.world.get_block(door_x, y, door_z) == "door":
            runtime.world.set_block(door_x, y, door_z, AIR_BLOCK_KEY)
    runtime.add_message("Opened door.")
    return True


def interact_nearby(runtime: GameRuntime, session_id: str) -> bool:
    player = runtime.entities.require(runtime.require_session(session_id).player_entity_id)
    player_position = player.require(Transform).position
    item = _nearest_pickup(runtime, player_position)
    if item is not None:
        if _apply_immediate_consumable(runtime, player, item):
            return True
        inventory = player.require(Inventory)
        if len(inventory.item_ids) >= inventory.capacity:
            runtime.add_message("Inventory is full.")
            return False
        item.remove(Transform)
        item.remove(Pickup)
        inventory.item_ids.append(item.id)
        item_data = item.require(Item)
        if item.has(Weapon):
            player.require(Equipment).equipped_item_id = item.id
            runtime.add_message(f"Picked up and equipped {item_data.display_name}.")
        else:
            runtime.add_message(f"Picked up {item_data.display_name}.")
        return True
    if _open_nearby_door(runtime, player_position):
        return True
    runtime.add_message("Nothing nearby to interact with.")
    return False


def equip_next(runtime: GameRuntime, session_id: str) -> bool:
    player = runtime.entities.require(runtime.require_session(session_id).player_entity_id)
    inventory = player.require(Inventory)
    equipment = player.require(Equipment)
    equippable_ids = [
        item_id
        for item_id in inventory.item_ids
        if runtime.entities.require(item_id).has(Weapon)
    ]
    if not equippable_ids:
        runtime.add_message("No weapon in inventory.")
        return False
    if equipment.equipped_item_id in equippable_ids:
        current_index = equippable_ids.index(equipment.equipped_item_id)
        if len(equippable_ids) == 1:
            item = runtime.entities.require(equippable_ids[0]).require(Item)
            equipment.equipped_item_id = None
            runtime.add_message(f"Unequipped {item.display_name}.")
            return True
        next_id = equippable_ids[(current_index + 1) % len(equippable_ids)]
    else:
        next_id = equippable_ids[0]
    equipment.equipped_item_id = next_id
    runtime.add_message(f"Equipped {runtime.entities.require(next_id).require(Item).display_name}.")
    return True


def consume_food(runtime: GameRuntime, session_id: str) -> bool:
    player = runtime.entities.require(runtime.require_session(session_id).player_entity_id)
    inventory = player.require(Inventory)
    food_id = next(
        (
            item_id
            for item_id in inventory.item_ids
            if (consumable := runtime.entities.require(item_id).get(Consumable)) is not None
            and consumable.effect == "hunger"
        ),
        None,
    )
    if food_id is None:
        runtime.add_message("You do not have any food.")
        return False
    food = runtime.entities.require(food_id)
    consumable = food.require(Consumable)
    hunger = player.require(Hunger)
    hunger.current = min(hunger.maximum, hunger.current + consumable.amount)
    inventory.item_ids.remove(food_id)
    runtime.entities.remove(food_id)
    runtime.add_message(f"Ate {food.require(Item).display_name}. Recovered {int(consumable.amount)} hunger.")
    return True
