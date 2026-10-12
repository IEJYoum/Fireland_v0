# Fireland

Fireland is an authoritative 3D game foundation. Python owns the continuous
simulation, block collision, entities, inventory, and combat. A Three.js browser
client renders versioned snapshots and sends sequenced player intent.

The current world is an early playable slice built on that foundation. It has
deterministic biome regions, forests, building prefabs, distance-scaled hostile
spawns, inventory items, consumables, drops, and a development HUD. The content
is intentionally simple; each feature exercises a reusable engine seam rather
than defining a final game design.

## Run

The existing Conda environment is named `Fireland`:

```powershell
conda activate Fireland
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8000`. Running `app.py` also opens it automatically.
Three.js `0.180.0` and its license are vendored under `static/vendor`, so the
game client works without an internet connection.

Controls:

- `WASD`: move relative to the camera
- `Space`: jump while grounded
- Mouse: look
- Click: use the equipped weapon; accepted shots draw a brief tracer and entity
  hits flash a hit marker
- `E`: pick up the nearest item or open a nearby door
- `Q`: cycle equipped weapons; with one weapon, toggle it holstered/equipped
- `F`: consume food from the inventory
- `R`: respawn with a starter pistol without resetting the world
- `1`: first-person camera
- `2`: top orthographic debug camera
- `3`: side orthographic debug camera
- `Esc`: release pointer lock

For a persistent diagnostic view on reload, use `?camera=top` or
`?camera=side` in the URL.

## Architecture

Coordinates use `x/z` as the horizontal plane and positive `y` as up. Static
terrain is stored as sparse 16×16 horizontal chunks. Missing blocks are air;
chunk revisions let clients fetch block data only when it changes.

Dynamic world objects are entities composed from typed dataclass components.
Definitions produce fully independent mutable instances. Weapons, consumables,
pickups, and equipped hostile weapons are real item entities created from one
definition table. Systems query the components they require; string-keyed
behavior registries leave AI, world generation, and drop behavior serializable
without storing callables on entities.

Movement is composed from controller intent and persistent residual velocity.
Players and AI write `ControlVelocity`; gravity, jumping, knockback, and other
impulses use `Velocity`. Shared physics combines them, decays horizontal
momentum, and cancels residual motion against colliding block faces.

The default world uses the registered `overworld` generator (`basic_flat` remains
an alias for compatibility). Chunk generation is deterministic from
`(world seed, chunk x, chunk z)`. Coherent plains, forest, and settled regions
come from deterministic cellular biome sites. Trees and building prefabs emit
blocks; generation emits stable spawn descriptors for entities. The runtime
materializes each descriptor once, keeping content generation separate from ECS
ownership and future persistence.

Hostile spawn probability rises with chunk distance and chooses only walkable
cells connected to the chunk's outdoor boundary. This is an honest reachability
constraint, not pathfinding: current hostiles use shared direct steering and can
still become stuck on complex geometry. A later navigation system can replace
the AI policy without replacing physics, combat, item, or spawn data.

The server generates one extra chunk ring beyond the streamed client region.
Generated chunks remain resident for v1; entities outside every session's active
chunks are frozen without losing state. Non-spatial or global logic opts into
simulation with `AlwaysActive`.

The simulation advances at a fixed 60 Hz. Movement is split into bounded
substeps and resolves AABBs independently along X, Z, and Y against solid voxel
blocks. The browser owns immediate camera movement, but the server decides
movement, grounded state, jumping, ray hits, armor-adjusted damage, pickups,
inventory, consumption, doors, drops, hostile actions, and cooldowns.

HTTP is intentionally a replaceable transport:

- `GET /api/state` returns the per-session entity snapshot and visible chunk
  revision descriptors.
- `GET /api/chunks/{x}/{z}` returns a full chunk at a specific current revision.
- `POST /api/action` accepts sequenced input and discrete gameplay intent. Shoot
  responses include the authoritative ray endpoints and hit kind for feedback.

First-person, top, and side views are camera modes over one Three.js scene. They
do not alter simulation or determine which entities are active.

## Tests

```powershell
conda run -n Fireland python -m pytest -q
```

The focused suite covers chunk boundaries, deterministic generation and
streaming, entity construction, behavior lookup, simulated/frozen sets, composed
movement and impulses, shared player/enemy physics, 3D collision and jumping,
action sequencing, wire snapshots, ray/block/entity intersection, occlusion,
elevation, biome continuity, building reachability, scaled hostile density,
pickup identity, inventory and consumables, hostile combat, random drops,
weapon cooldowns, death/respawn, and HTTP behavior.

The current architecture plan and deferred content work live in
`planning/architecture_update_plan_v1.txt` and `planning/content_plan_v0.txt`.
