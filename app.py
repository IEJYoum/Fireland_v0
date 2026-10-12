"""HTTP shell for the authoritative 3D Fireland simulation."""

import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from game.actions3d import apply_action
from game.runtime import FixedStepClock, GameRuntime, create_runtime, step_runtime
from game.vectors import Vec3
from game.wire import chunk_to_wire, snapshot_for_session


ROOT = Path(__file__).parent
LOCAL_SESSION_ID = "local"


@dataclass
class ServerRuntime:
    game: GameRuntime
    clock: FixedStepClock


runtime_lock = asyncio.Lock()
active_runtime: ServerRuntime | None = None
game_task: asyncio.Task[None] | None = None


def require_runtime() -> ServerRuntime:
    if active_runtime is None:
        raise HTTPException(status_code=503, detail="Game is starting.")
    return active_runtime


async def run_game_loop() -> None:
    loop = asyncio.get_running_loop()
    previous_time = loop.time()
    while True:
        await asyncio.sleep(1 / 120)
        current_time = loop.time()
        elapsed = current_time - previous_time
        previous_time = current_time
        async with runtime_lock:
            server = require_runtime()
            server.clock.advance(elapsed, lambda dt: step_runtime(server.game, dt))


@asynccontextmanager
async def lifespan(_: FastAPI):
    global active_runtime, game_task
    active_runtime = ServerRuntime(create_runtime(LOCAL_SESSION_ID), FixedStepClock())
    game_task = asyncio.create_task(run_game_loop())
    yield
    if game_task is not None:
        game_task.cancel()
        with suppress(asyncio.CancelledError):
            await game_task
    active_runtime = None


app = FastAPI(title="Fireland", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    async with runtime_lock:
        return snapshot_for_session(require_runtime().game, LOCAL_SESSION_ID)


@app.get("/api/chunks/{chunk_x}/{chunk_z}")
async def get_chunk(chunk_x: int, chunk_z: int) -> dict[str, Any]:
    async with runtime_lock:
        try:
            return chunk_to_wire(require_runtime().game, chunk_x, chunk_z)
        except KeyError as error:
            raise HTTPException(status_code=425, detail="Chunk is not generated yet.") from error


def _vector_to_wire(vector: Vec3) -> dict[str, float]:
    return {"x": vector.x, "y": vector.y, "z": vector.z}


@app.post("/api/action")
async def post_action(payload: dict[str, Any]) -> dict[str, Any]:
    async with runtime_lock:
        try:
            result = apply_action(require_runtime().game, LOCAL_SESSION_ID, payload)
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    response: dict[str, Any] = {"changed": result.changed}
    if result.shot is not None:
        shot = result.shot
        response["shot"] = {
            "fired": shot.fired,
            "hit_kind": shot.hit_kind,
            "entity_id": shot.entity_id,
            "origin": _vector_to_wire(shot.origin) if shot.origin is not None else None,
            "end": _vector_to_wire(shot.end) if shot.end is not None else None,
        }
    return response


if __name__ == "__main__":
    import threading
    import webbrowser

    import uvicorn

    host, port = "127.0.0.1", 8000
    threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    uvicorn.run(app, host=host, port=port)
