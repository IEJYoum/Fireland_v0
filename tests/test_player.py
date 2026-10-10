from game.models import ItemInstance, MapRequest, Vector
from game.player import apply_damage_to_player, damage_after_armor, equip_item, move_player, pick_up_item, set_player_movement
from game.state import create_game


def make_game():
    return create_game(MapRequest(width=8, height=8, seed=3))


def test_player_cannot_walk_through_wall():
    game = make_game()
    game.player.position = Vector(1.5, 1.5)
    assert move_player(game, "left") is False
    assert game.player.position == Vector(1.5, 1.5)


def test_diagonal_input_is_normalized():
    game = make_game()
    set_player_movement(game, 1, 1)
    assert round(game.player.movement.x, 3) == 0.707
    assert round(game.player.movement.y, 3) == 0.707


def test_pickup_then_equip_pistol():
    game = make_game()
    floor_item = next(iter(game.floor_items.values()))
    game.player.position = floor_item.position
    assert pick_up_item(game) is True
    assert equip_item(game) is True
    assert game.player.equipped_item_id == 2


def test_equip_cycles_to_the_next_weapon():
    game = make_game()
    game.player.inventory = [2, 99]
    game.item_instances[99] = ItemInstance(id=99, definition_key="rifle")
    assert equip_item(game) is True
    assert game.player.equipped_item_id == 2
    assert equip_item(game) is True
    assert game.player.equipped_item_id == 99


def test_damage_never_goes_below_one_after_armor():
    game = make_game()
    game.player.armor = 99
    assert damage_after_armor(20, game.player.armor) == 1
    assert apply_damage_to_player(game, 20) == 1
    assert game.player.health == 99
