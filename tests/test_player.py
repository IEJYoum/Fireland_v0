from game.models import ItemInstance, MapRequest, Vector
from game.actions import apply_action
from game.player import apply_damage_to_player, damage_after_armor, equip_item, move_player, pick_up_item, set_player_movement, step_hunger
from game.state import clear_scorecard, create_game, game_snapshot, scorecard_entries, spawn_floor_item
from game.update import step_game


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
    assert round(game.player.facing.x, 3) == 0.707
    assert round(game.player.facing.y, 3) == 0.707


def test_pickup_then_equip_pistol():
    game = make_game()
    floor_item = next(iter(game.floor_items.values()))
    game.player.position = floor_item.position
    assert pick_up_item(game) is True
    assert game.player.equipped_item_id == 2


def test_equip_cycles_to_the_next_weapon():
    game = make_game()
    game.player.inventory = [2, 99]
    game.item_instances[99] = ItemInstance(id=99, definition_key="rifle")
    assert equip_item(game) is True
    assert game.player.equipped_item_id == 2
    assert equip_item(game) is True
    assert game.player.equipped_item_id == 99


def test_pickup_automatically_equips_new_weapon():
    game = make_game()
    spawn_floor_item(game, "rifle", game.player.position)
    assert pick_up_item(game) is True
    assert game.item_instances[game.player.equipped_item_id].definition_key == "rifle"


def test_food_is_carried_then_restores_hunger_when_eaten():
    game = make_game()
    food = spawn_floor_item(game, "food", game.player.position)
    assert pick_up_item(game) is True
    assert food.item_id in game.player.inventory
    game.player.hunger = 40
    assert apply_action(game, {"type": "eat"}) is True
    assert game.player.hunger == 75
    assert food.item_id not in game.item_instances


def test_hunger_decreases_over_time_without_going_negative():
    game = make_game()
    step_hunger(game, 2)
    assert game.player.hunger == 99
    step_hunger(game, 1_000)
    assert game.player.hunger == 0


def test_zero_health_marks_game_over():
    game = make_game()
    apply_damage_to_player(game, 999)
    assert game.player.health == 0
    assert game.game_over is True


def test_scorecard_rounds_and_freezes_survival_time_after_death():
    clear_scorecard()
    try:
        game = make_game()
        game.elapsed_seconds = 12.34
        apply_damage_to_player(game, 999)
        snapshot = game_snapshot(game)
        assert snapshot["scorecard"]["survival_seconds"] == 12.3
        assert snapshot["scorecard"]["qualifies"] is True
        assert apply_action(game, {"type": "record_score", "name": "A<ce>"}) is True
        assert scorecard_entries[0].name == "Ace"
        assert scorecard_entries[0].seconds == 12.3
        step_game(game, 10)
        assert game.elapsed_seconds == 12.34
        assert game.score_recorded is True
    finally:
        clear_scorecard()


def test_only_top_ten_survival_scores_qualify():
    clear_scorecard()
    try:
        for seconds in range(1, 11):
            game = make_game()
            game.elapsed_seconds = seconds
            apply_damage_to_player(game, 999)
            assert apply_action(game, {"type": "record_score", "name": f"P{seconds}"}) is True
        low_score_game = make_game()
        low_score_game.elapsed_seconds = 0.9
        apply_damage_to_player(low_score_game, 999)
        assert game_snapshot(low_score_game)["scorecard"]["qualifies"] is False
        assert apply_action(low_score_game, {"type": "record_score", "name": "Late"}) is False
        assert len(scorecard_entries) == 10
    finally:
        clear_scorecard()


def test_restart_replaces_a_finished_run():
    game = make_game()
    apply_damage_to_player(game, 999)
    assert apply_action(game, {"type": "restart"}) is True
    assert game.game_over is False
    assert game.player.health == game.player.max_health


def test_damage_never_goes_below_one_after_armor():
    game = make_game()
    game.player.armor = 99
    assert damage_after_armor(20, game.player.armor) == 1
    assert apply_damage_to_player(game, 20) == 1
    assert game.player.health == 99
