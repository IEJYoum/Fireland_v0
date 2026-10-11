"""Translate untrusted frontend action payloads into game-rule calls."""

from typing import Any

from .combat import fire_equipped_weapon
from .models import Game
from .player import equip_item, interact_player, move_player, set_player_movement
from .state import add_message, reset_game


def apply_action(game: Game, payload: dict[str, Any]) -> bool:
    action_type = payload.get("type")
    if action_type == "restart":
        reset_game(game)
        return True
    if game.game_over:
        add_message(game, "Choose Play Again to start a new run.")
        return False
    if action_type == "move":
        return move_player(game, str(payload.get("direction", "")))
    if action_type == "input":
        x = payload.get("x")
        y = payload.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            add_message(game, "Movement input is invalid.")
            return False
        return set_player_movement(game, float(x), float(y))
    if action_type == "pickup":
        return interact_player(game)
    if action_type == "equip":
        item_id = payload.get("item_id")
        return equip_item(game, item_id if isinstance(item_id, int) else None)
    if action_type == "shoot":
        target = payload.get("target")
        if not isinstance(target, dict):
            add_message(game, "A shot needs a target.")
            return False
        target_x = target.get("x")
        target_y = target.get("y")
        if not isinstance(target_x, (int, float)) or not isinstance(target_y, (int, float)):
            add_message(game, "Shot target is invalid.")
            return False
        return fire_equipped_weapon(game, float(target_x), float(target_y))
    add_message(game, "Unknown action.")
    return False
