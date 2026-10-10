from game.combat import damage_enemy, fire_equipped_weapon
from game.models import MapRequest
from game.player import equip_item, pick_up_item
from game.state import create_game
from game.update import step_game
from game.world import choose_start_positions, generate_map, is_on_players_screen, is_outside_starting_room, is_walkable


def test_room_generator_has_reachable_start_positions():
    tile_map = generate_map(MapRequest(width=8, height=8, seed=12))
    player_position, pistol_position = choose_start_positions(tile_map, 12)
    assert player_position != pistol_position
    assert is_walkable(tile_map, player_position)
    assert is_walkable(tile_map, pistol_position)


def test_pistol_creates_and_expires_projectile():
    game = create_game(MapRequest(width=8, height=8, seed=5))
    game.enemies.clear()
    game.player.position = next(iter(game.floor_items.values())).position
    pick_up_item(game)
    equip_item(game)
    assert fire_equipped_weapon(game, 6, 3) is True
    assert len(game.projectiles) == 1
    step_game(game, 1.0)
    assert game.projectiles == {}


def test_standard_game_has_fixed_starter_room_and_two_outside_enemies():
    game = create_game(MapRequest(seed=7))
    assert game.player.position.x == 9.5
    assert game.player.position.y == 7.5
    assert next(iter(game.floor_items.values())).position.x == 11.5
    assert len(game.enemies) == 2
    assert all(is_outside_starting_room(enemy.position) for enemy in game.enemies.values())
    assert all(is_on_players_screen(game.tile_map, game.player.position, enemy.position) for enemy in game.enemies.values())


def test_enemy_death_drops_health_or_rifle_and_awards_xp():
    game = create_game(MapRequest(seed=7))
    enemy = next(iter(game.enemies.values()))
    damage_enemy(game, enemy, 999)
    floor_item_keys = {
        game.item_instances[floor_item.item_id].definition_key
        for floor_item in game.floor_items.values()
    }
    assert enemy.id not in game.enemies
    assert floor_item_keys & {"health_up", "rifle"}
    assert game.player.xp == 25
