"""Weapon firing and projectile simulation. Enemy collision hooks belong here later."""

import math

from .items import get_item_definition
from .models import Enemy, Game, Projectile, Vector
from .player import apply_damage_to_player, damage_after_armor, grant_xp
from .state import add_message, spawn_floor_item
from .world import is_walkable


def fire_equipped_weapon(game: Game, target_x: float, target_y: float) -> bool:
    equipped_id = game.player.equipped_item_id
    if equipped_id is None:
        add_message(game, "Equip a weapon before firing.")
        return False

    item = game.item_instances[equipped_id]
    definition = get_item_definition(item.definition_key)
    if definition.kind != "weapon":
        add_message(game, "That equipped item is not a weapon.")
        return False

    return fire_weapon(
        game,
        item.definition_key,
        game.player.position,
        Vector(target_x, target_y),
        owner_kind="player",
    )


def fire_weapon(
    game: Game, definition_key: str, origin: Vector, target: Vector, owner_kind: str
) -> bool:
    definition = get_item_definition(definition_key)
    delta_x = target.x - origin.x
    delta_y = target.y - origin.y
    length = math.hypot(delta_x, delta_y)
    if length == 0:
        return False

    projectile = Projectile(
        id=game.next_entity_id,
        x=origin.x,
        y=origin.y,
        velocity_x=(delta_x / length) * definition.projectile_speed,
        velocity_y=(delta_y / length) * definition.projectile_speed,
        damage=definition.damage,
        owner_kind=owner_kind,
        remaining_seconds=definition.projectile_lifetime,
    )
    game.projectiles[projectile.id] = projectile
    game.next_entity_id += 1
    return True


def step_projectiles(game: Game, dt: float) -> None:
    expired_ids = []
    for projectile in game.projectiles.values():
        projectile.x += projectile.velocity_x * dt
        projectile.y += projectile.velocity_y * dt
        projectile.remaining_seconds -= dt
        tile_position = Vector(projectile.x, projectile.y)
        if projectile.remaining_seconds <= 0 or not is_walkable(game.tile_map, tile_position):
            expired_ids.append(projectile.id)
            continue
        if projectile.owner_kind == "player":
            enemy = next(
                (
                    enemy
                    for enemy in game.enemies.values()
                    if math.dist((projectile.x, projectile.y), (enemy.position.x, enemy.position.y)) < 0.45
                ),
                None,
            )
            if enemy is not None:
                damage_enemy(game, enemy, projectile.damage)
                expired_ids.append(projectile.id)
        elif math.dist(
            (projectile.x, projectile.y), (game.player.position.x, game.player.position.y)
        ) < 0.45:
            damage = apply_damage_to_player(game, projectile.damage)
            add_message(game, f"You were hit for {damage}.")
            expired_ids.append(projectile.id)
    for projectile_id in expired_ids:
        del game.projectiles[projectile_id]


def damage_enemy(game: Game, enemy: Enemy, raw_damage: int) -> int:
    damage = damage_after_armor(raw_damage, enemy.armor)
    enemy.health = max(0, enemy.health - damage)
    if enemy.health == 0:
        del game.enemies[enemy.id]
        grant_xp(game, 25)
        drop_key = game.randomizer.choice(("health_up", "rifle"))
        spawn_floor_item(game, drop_key, enemy.position)
        add_message(game, f"Enemy defeated. Dropped {get_item_definition(drop_key).name}.")
    return damage
