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

Controls: WASD moves, `E` picks up nearby drops, opens doors, or uses an edge exit, `1` equips or cycles weapons, and either mouse button fires. Start in a fixed room with a pistol. Pistol, rifle, sniper rifle, and knife pickups automatically equip; the knife is a short-range melee attack while the guns fire projectiles. Every unvisited grid coordinate generates one of three seeded map types: scattered square/L prefab buildings, a gridded prefab neighborhood, or a forest. Half of prefab buildings have closed doors; one in ten door-bearing buildings receives a random weapon or Health Up pickup.

The world starts at grid location `(0, 0)`. Using a cardinal edge exit enters its neighboring coordinate and preserves the current map's remaining enemies and pickups. New maps use `int(level_index ** 1.5) + 1` enemies, where the initial map is level 1 and every exit traversal advances the level index. Enemies can spawn in prefab interiors but never in the player start building. Each enemy holds a random weapon instance from the same item system as the player, pursues and attacks only when on screen and connected by walkable terrain, and has a 50/50 chance to drop that held weapon or a Health Up (restores 25 health). Each second, active enemies have a 33% chance to evade briefly toward a random target (purple) instead of chasing (red). At zero health, select **Play again** to reset the run.

## Design

The dataclasses in `game/models.py` are data containers only. `ItemInstance` is the shared weapon object: it can be in a player inventory, equipped by an enemy, or on the floor, while `ItemDefinition` holds its common stats. Player and enemy coordinates are continuous `Vector(x, y)` values in tile units, and the backend advances the world at a fixed 60 Hz. Rule modules use small functions such as `step_player_movement`, `step_enemies`, `pick_up_item`, `fire_equipped_weapon`, `travel_to`, and `step_game`. Each `MapLocation` retains a map plus the live enemy and pickup dictionaries for that grid coordinate.

Run tests with:

```powershell
py -m pytest
```
