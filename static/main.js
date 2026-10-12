import { updateHud, showConnection, showShotFeedback } from "/static/hud.js";
import { InputController } from "/static/input.js";
import { FirelandRenderer } from "/static/renderer3d.js";
import { fetchChunk, fetchState, sendAction } from "/static/transport.js";

const canvas = document.querySelector("#game");
const startOverlay = document.querySelector("#start-overlay");
const renderer = new FirelandRenderer(canvas);
const input = new InputController(canvas, setCameraMode, sendGameplayAction);
let stateRequestInFlight = false;
let previousFrameTime = performance.now();

function setCameraMode(mode) {
  renderer.setCameraMode(mode);
  if (mode !== "first" && document.pointerLockElement === canvas) document.exitPointerLock();
  startOverlay.hidden = mode !== "first" || document.pointerLockElement === canvas;
}

async function sendGameplayAction(type, direction) {
  const payload = direction ? { type, direction } : { type };
  try {
    const result = await sendAction(payload);
    if (type === "shoot" && result.shot?.fired) {
      showShotFeedback();
    }
  } catch (error) {
    showConnection(error.message, true);
  }
}

document.querySelectorAll("[data-camera]").forEach((button) => {
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    setCameraMode(button.dataset.camera);
  });
});
const requestedCamera = new URLSearchParams(window.location.search).get("camera");
setCameraMode(["first", "top", "side"].includes(requestedCamera) ? requestedCamera : "first");

startOverlay.addEventListener("click", () => canvas.requestPointerLock());
canvas.addEventListener("click", () => {
  if (renderer.cameraMode === "first" && document.pointerLockElement !== canvas) {
    canvas.requestPointerLock();
  } else if (renderer.cameraMode === "first") {
    sendGameplayAction("shoot", input.lookDirection());
  }
});
document.addEventListener("pointerlockchange", () => {
  startOverlay.hidden = document.pointerLockElement === canvas || renderer.cameraMode !== "first";
  if (document.pointerLockElement !== canvas) input.releaseMovement();
});

async function refreshState() {
  if (stateRequestInFlight) return;
  stateRequestInFlight = true;
  try {
    const snapshot = await fetchState();
    renderer.updateSnapshot(snapshot);
    updateHud(snapshot);
    const player = snapshot.entities.find((entity) => entity.id === snapshot.you.player_entity_id);
    const playerPosition = player?.components.transform;
    if (playerPosition) {
      const staleChunks = snapshot.chunks.filter(
        (chunk) => renderer.isChunkNearPlayer(chunk, playerPosition)
          && !renderer.hasChunkRevision(chunk.x, chunk.z, chunk.revision),
      );
      const chunks = await Promise.all(staleChunks.map((chunk) => fetchChunk(chunk.x, chunk.z)));
      chunks.forEach((chunk) => renderer.setChunk(chunk));
      renderer.unloadDistantChunks(playerPosition);
    }
  } catch (error) {
    showConnection(error.message, true);
  } finally {
    stateRequestInFlight = false;
  }
}

setInterval(() => {
  const command = input.takeCommand();
  if (command) sendAction(command).catch((error) => showConnection(error.message, true));
}, 33);

function drawFrame(frameTime) {
  const frameSeconds = Math.min(0.1, (frameTime - previousFrameTime) / 1000);
  previousFrameTime = frameTime;
  renderer.render(input.yaw, input.pitch, frameSeconds);
  requestAnimationFrame(drawFrame);
}

refreshState();
setInterval(refreshState, 50);
requestAnimationFrame(drawFrame);
