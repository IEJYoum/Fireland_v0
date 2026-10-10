"""Simple enemy state updates. More complex behaviours can grow from here."""

import math

from .combat import fire_weapon
from .models import Game, Vector
from .world import is_on_players_screen, move_with_collision


ENEMY_SPEED_TILES_PER_SECOND = 2.4
RIFLE_RANGE_TILES = 13.0
PREFERRED_RANGE_TILES = 8.0


def step_enemies(game: Game, dt: float) -> None:
    for enemy in game.enemies.values():
        enemy.fire_cooldown = max(0.0, enemy.fire_cooldown - dt)
        if not is_on_players_screen(game.tile_map, game.player.position, enemy.position):
            continue

        delta_x = game.player.position.x - enemy.position.x
        delta_y = game.player.position.y - enemy.position.y
        distance = math.hypot(delta_x, delta_y)
        if distance > PREFERRED_RANGE_TILES:
            direction = Vector(delta_x / distance, delta_y / distance)
            enemy.position = move_with_collision(
                game.tile_map, enemy.position, direction, ENEMY_SPEED_TILES_PER_SECOND, dt
            )
        if distance <= RIFLE_RANGE_TILES and enemy.fire_cooldown == 0:
            fire_enemy_rifle(game, enemy.position)
            enemy.fire_cooldown = game.randomizer.uniform(0.85, 1.3)


def fire_enemy_rifle(game: Game, origin: Vector) -> None:
    player = game.player.position
    base_angle = math.atan2(player.y - origin.y, player.x - origin.x)
    aim_angle = base_angle + game.randomizer.uniform(-0.18, 0.18)
    target = Vector(origin.x + math.cos(aim_angle), origin.y + math.sin(aim_angle))
    fire_weapon(game, "rifle", origin, target, owner_kind="enemy")
