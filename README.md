# Fireland

Fireland is an authoritative 3D game foundation. Python owns the continuous
simulation, block collision, entities, inventory, and combat. A Three.js browser
client renders versioned snapshots and sends sequenced player intent.

The current world is deliberately a graybox physics arena rather than a game. It
exists to exercise the reusable foundation: chunk coordinates, elevation,
gravity, jumping, 3D AABB hitboxes, pickups, block occlusion, and vertical aim.

## Run

The existing Conda environment is named `Fireland`:

```powershell
conda activate Fireland
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8000`. Running `app.py` also opens it automatically.
The client loads the pinned Three.js `0.180.0` ES module from jsDelivr, so the
browser needs network access until the dependency is vendored locally.

Controls:

- `WASD`: move relative to the camera
- `Space`: jump while grounded
- Mouse: look
- Click: fire the equipped hitscan weapon
- `E`: interact with an aimed pickup
- `R`: respawn the player without resetting the world
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
Definitions produce fully independent mutable instances. Systems query the
components they require; string-keyed behavior registries leave AI, spawning,
and drop behavior serializable without storing callables on entities.

The simulation advances at a fixed 60 Hz. Movement is split into bounded
substeps and resolves AABBs independently along X, Z, and Y against solid voxel
blocks. The browser owns immediate camera movement, but the server decides
movement, grounded state, jumping, ray hits, damage, pickups, and cooldowns.

HTTP is intentionally a replaceable transport:

- `GET /api/state` returns the per-session entity snapshot and visible chunk
  revision descriptors.
- `GET /api/chunks/{x}/{z}` returns a full chunk at a specific current revision.
- `POST /api/action` accepts sequenced input and discrete gameplay intent.

First-person, top, and side views are camera modes over one Three.js scene. They
do not alter simulation or determine which entities are active.

## Tests

```powershell
conda run -n Fireland python -m pytest -q
```

The focused suite covers chunk boundaries and revisions, entity construction,
behavior lookup, fixed stepping, 3D collision and jumping, action sequencing,
wire snapshots, ray/block/entity intersection, occlusion, elevation, pickup
identity, weapon cooldowns, respawn, and HTTP boundary behavior.

The architectural implementation plan and deferred expansion work live in
`planning/general_architecture_update_plan_v0.2.txt`.
