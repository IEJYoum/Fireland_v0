from game.combat import damage_enemy, fire_equipped_weapon
from game.enemies import roll_enemy_mode
from game.items import get_item_definition
from game.models import MapRequest
from game.player import equip_item, interact_player, pick_up_item
from game.state import create_game, spawn_floor_item, travel_to
from game.update import step_game
from game.world import LEVEL_EXIT, MAP_TYPES, TREE, choose_start_positions, generate_map, has_walkable_path, is_outside_starting_room, is_walkable


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
    assert set(game.tile_map.prefab_kinds) == {"square", "l"}
    assert len(game.tile_map.prefab_kinds) == 8
    assert game.tile_map.tiles[0][game.tile_map.width // 2] == LEVEL_EXIT
    assert game.tile_map.tiles[game.tile_map.height - 1][game.tile_map.width // 2] == LEVEL_EXIT
    assert game.tile_map.tiles[game.tile_map.height // 2][0] == LEVEL_EXIT
    assert game.tile_map.tiles[game.tile_map.height // 2][game.tile_map.width - 1] == LEVEL_EXIT


def test_rifle_projectile_is_faster_than_pistol_projectile():
    assert get_item_definition("rifle").projectile_speed > get_item_definition("pistol").projectile_speed


def test_closed_starter_door_blocks_enemy_paths_until_opened():
    game = create_game(MapRequest(seed=7))
    outside_start_room = game.player.position.__class__(9.5, 13.5)
    assert not has_walkable_path(game.tile_map, game.player.position, outside_start_room)
    game.player.position = game.player.position.__class__(9.5, 11.5)
    assert interact_player(game) is True
    assert has_walkable_path(game.tile_map, game.player.position, outside_start_room)


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


def test_evade_roll_assigns_a_reachable_random_target():
    class AlwaysEvade:
        def random(self):
            return 0.0

        def uniform(self, low, high):
            return (low + high) / 2

    game = create_game(MapRequest(seed=7))
    game.randomizer = AlwaysEvade()
    enemy = next(iter(game.enemies.values()))
    roll_enemy_mode(game, enemy)
    assert enemy.mode == "evade"
    assert enemy.evade_target is not None
    assert has_walkable_path(game.tile_map, enemy.position, enemy.evade_target)


def test_all_map_generators_are_available():
    for map_type in MAP_TYPES:
        tile_map = generate_map(MapRequest(seed=17, generator_name=map_type))
        assert tile_map.generator_name == map_type
        assert tile_map.tiles[0][tile_map.width // 2] == LEVEL_EXIT
    forest = generate_map(MapRequest(seed=17, generator_name="forest"))
    assert any(TREE in row for row in forest.tiles)


def test_world_locations_persist_and_enemy_budget_grows():
    game = create_game(MapRequest(seed=17))
    spawned_item = spawn_floor_item(game, "rifle", game.player.position)
    start_enemies = game.enemies
    assert travel_to(game, "north") is True
    assert game.world_position == (0, -1)
    assert len(game.enemies) == 3
    assert travel_to(game, "south") is True
    assert game.world_position == (0, 0)
    assert game.enemies is start_enemies
    assert spawned_item.id in game.floor_items
    assert travel_to(game, "west") is True
    assert len(game.enemies) == 5
    assert len(game.world_locations) == 3
