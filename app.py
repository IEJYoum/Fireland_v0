"""HTTP shell for the function-oriented RPG rules."""

import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from game.actions import apply_action
from game.models import Game, MapRequest
from game.state import create_game, game_snapshot
from game.update import step_game


ROOT = Path(__file__).parent
TICK_SECONDS = 1 / 60
game_lock = asyncio.Lock()
active_game: Game | None = None
game_task: asyncio.Task[None] | None = None


async def run_game_loop() -> None:
    loop = asyncio.get_running_loop()
    previous_time = loop.time()
    while True:
        await asyncio.sleep(TICK_SECONDS)
        current_time = loop.time()
        dt = min(current_time - previous_time, 0.1)
        previous_time = current_time
        async with game_lock:
            if active_game is not None:
                step_game(active_game, dt)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global active_game, game_task
    active_game = create_game(MapRequest(seed=7, width=80, height=50))
    game_task = asyncio.create_task(run_game_loop())
    yield
    if game_task is not None:
        game_task.cancel()
        with suppress(asyncio.CancelledError):
            await game_task


app = FastAPI(title="Game RPG", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


def require_game() -> Game:
    if active_game is None:
        raise HTTPException(status_code=503, detail="Game is starting.")
    return active_game


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    async with game_lock:
        return game_snapshot(require_game())


@app.post("/api/action")
async def post_action(payload: dict[str, Any]) -> dict[str, bool]:
    async with game_lock:
        changed = apply_action(require_game(), payload)
    return {"changed": changed}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
