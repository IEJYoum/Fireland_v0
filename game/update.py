"""Fixed-step world update entry point."""

from .combat import step_projectiles
from .enemies import step_enemies
from .models import Game
from .player import step_player_movement


def step_game(game: Game, dt: float) -> None:
    game.elapsed_seconds += dt
    if game.game_over:
        return
    step_player_movement(game, dt)
    step_enemies(game, dt)
    step_projectiles(game, dt)
