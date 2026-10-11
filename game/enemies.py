"""Simple enemy state updates. More complex behaviours can grow from here."""

import math

from .combat import fire_weapon
from .models import Game, Vector
from .world import has_walkable_path, is_on_players_screen, move_with_collision


ENEMY_SPEED_TILES_PER_SECOND = 2.4
RIFLE_RANGE_TILES = 13.0
PREFERRED_RANGE_TILES = 8.0
EVADE_CHANCE = 0.33
MODE_ROLL_SECONDS = 1.0


def step_enemies(game: Game, dt: float) -> None:
    for enemy in game.enemies.values():
        enemy.fire_cooldown = max(0.0, enemy.fire_cooldown - dt)
        if not is_on_players_screen(game.tile_map, game.player.position, enemy.position):
            continue
        if not has_walkable_path(game.tile_map, enemy.position, game.player.position):
            continue

        update_enemy_mode(game, enemy, dt)
        delta_x = game.player.position.x - enemy.position.x
        delta_y = game.player.position.y - enemy.position.y
        distance = math.hypot(delta_x, delta_y)
        direction = enemy_movement_direction(enemy, delta_x, delta_y, distance)
        if direction is not None:
            enemy.position = move_with_collision(
                game.tile_map, enemy.position, direction, ENEMY_SPEED_TILES_PER_SECOND, dt
            )
        if distance <= RIFLE_RANGE_TILES and enemy.fire_cooldown == 0:
            fire_enemy_rifle(game, enemy.position)
            enemy.fire_cooldown = game.randomizer.uniform(0.85, 1.3)


def update_enemy_mode(game: Game, enemy, dt: float) -> None:
    enemy.seconds_until_mode_roll -= dt
    while enemy.seconds_until_mode_roll <= 0:
        enemy.seconds_until_mode_roll += MODE_ROLL_SECONDS
        roll_enemy_mode(game, enemy)


def roll_enemy_mode(game: Game, enemy) -> None:
    if game.randomizer.random() < EVADE_CHANCE:
        enemy.mode = "evade"
        enemy.evade_target = choose_evade_target(game, enemy.position)
    else:
        enemy.mode = "chase"
        enemy.evade_target = None


def choose_evade_target(game: Game, origin: Vector) -> Vector:
    """Pick a nearby walkable random target for one second of evasive movement."""
    for _ in range(12):
        angle = game.randomizer.uniform(0, math.tau)
        distance = game.randomizer.uniform(3.0, 6.0)
        target = Vector(origin.x + math.cos(angle) * distance, origin.y + math.sin(angle) * distance)
        if has_walkable_path(game.tile_map, origin, target):
            return target
    return origin


def enemy_movement_direction(enemy, player_delta_x: float, player_delta_y: float, player_distance: float) -> Vector | None:
    if enemy.mode == "evade" and enemy.evade_target is not None:
        evade_delta_x = enemy.evade_target.x - enemy.position.x
        evade_delta_y = enemy.evade_target.y - enemy.position.y
        evade_distance = math.hypot(evade_delta_x, evade_delta_y)
        if evade_distance > 0.2:
            return Vector(evade_delta_x / evade_distance, evade_delta_y / evade_distance)
        return None
    if player_distance > PREFERRED_RANGE_TILES:
        return Vector(player_delta_x / player_distance, player_delta_y / player_distance)
    return None


def fire_enemy_rifle(game: Game, origin: Vector) -> None:
    player = game.player.position
    base_angle = math.atan2(player.y - origin.y, player.x - origin.x)
    aim_angle = base_angle + game.randomizer.uniform(-0.18, 0.18)
    target = Vector(origin.x + math.cos(aim_angle), origin.y + math.sin(aim_angle))
    fire_weapon(game, "rifle", origin, target, owner_kind="enemy")
