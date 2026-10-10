# Game RPG

A deliberately small top-down RPG foundation: Python owns the game rules and state; a browser canvas renders snapshots and sends player actions.

## Run

From this directory, create and activate a dedicated Conda environment, install dependencies, and start the game:

```powershell
conda create -n game-rpg python=3.11 -y
conda activate game-rpg
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8000`.

Controls: WASD moves, `E` picks up nearby drops, `1` equips or cycles weapons, and right-click fires. Start in a fixed room with a pistol. Two rifle enemies spawn elsewhere in the reachable map; they pursue and fire only while on screen. Defeated enemies award XP and drop either a Health Up (restores 25 health on pickup) or a rifle.

## Design

The dataclasses in `game/models.py` are data containers only. Player and enemy coordinates are continuous `Vector(x, y)` values in tile units, and the backend advances the world at a fixed 60 Hz. Rule modules use small functions such as `step_player_movement`, `step_enemies`, `pick_up_item`, `fire_equipped_weapon`, and `step_game`. The deterministic map generator creates a fixed starter room plus a large, seeded obstacle field; all generators return the same `TileMap` shape.

Run tests with:

```powershell
py -m pytest
```
