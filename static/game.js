const canvas = document.querySelector("#game");
const context = canvas.getContext("2d");
const status = document.querySelector("#status");
const tileSize = 32;
const viewportWidth = 960;
const viewportHeight = 640;
const heldKeys = new Set();
let state = null;
let visualPlayer = null;
let previousFrameTime = performance.now();
let stateRequestInFlight = false;

canvas.width = viewportWidth;
canvas.height = viewportHeight;

async function sendAction(payload) {
  await fetch("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function sendMovementInput() {
  const x = Number(heldKeys.has("d")) - Number(heldKeys.has("a"));
  const y = Number(heldKeys.has("s")) - Number(heldKeys.has("w"));
  sendAction({ type: "input", x, y });
}

async function refreshState() {
  if (stateRequestInFlight) return;
  stateRequestInFlight = true;
  try {
    const response = await fetch("/api/state");
    state = await response.json();
    if (!visualPlayer) visualPlayer = { x: state.player.x, y: state.player.y };
    updateStatus();
  } finally {
    stateRequestInFlight = false;
  }
}

function updateStatus() {
  if (!state) return;
  const equipped = state.player.inventory.find((item) => item.id === state.player.equipped_item_id);
  const inventory = state.player.inventory.map((item) => item.name).join(", ") || "empty";
  status.innerHTML = [
    `<p>Health: ${state.player.health}/${state.player.max_health} &middot; Armor: ${state.player.armor} &middot; XP: ${state.player.xp}</p>`,
    `<p>Inventory: ${inventory} &middot; Equipped: ${equipped ? equipped.name : "none"} &middot; Hostiles: ${state.enemies.length}</p>`,
    `<p>${state.messages.join(" ")}</p>`,
  ].join("");
}

function cameraForPlayer(player) {
  const visibleColumns = viewportWidth / tileSize;
  const visibleRows = viewportHeight / tileSize;
  return {
    x: Math.max(0, Math.min(state.map.width - visibleColumns, player.x - visibleColumns / 2)),
    y: Math.max(0, Math.min(state.map.height - visibleRows, player.y - visibleRows / 2)),
  };
}

function drawTile(tile, x, y, camera) {
  const screenX = (x - camera.x) * tileSize;
  const screenY = (y - camera.y) * tileSize;
  const colors = { floor: "#28352b", wall: "#46505a", obstacle: "#76634b" };
  context.fillStyle = colors[tile];
  context.fillRect(screenX, screenY, tileSize, tileSize);
  if (tile !== "floor") {
    context.strokeStyle = tile === "wall" ? "#64717c" : "#9b835e";
    context.strokeRect(screenX + .5, screenY + .5, tileSize - 1, tileSize - 1);
  }
}

function worldToScreen(position, camera) {
  return { x: (position.x - camera.x) * tileSize, y: (position.y - camera.y) * tileSize };
}

function drawFrame(frameTime) {
  const frameSeconds = Math.min((frameTime - previousFrameTime) / 1000, 0.1);
  previousFrameTime = frameTime;
  if (state && visualPlayer) {
    const smoothing = Math.min(1, frameSeconds * 20);
    visualPlayer.x += (state.player.x - visualPlayer.x) * smoothing;
    visualPlayer.y += (state.player.y - visualPlayer.y) * smoothing;
    const camera = cameraForPlayer(visualPlayer);
    const firstX = Math.floor(camera.x);
    const firstY = Math.floor(camera.y);
    const lastX = Math.min(state.map.width, Math.ceil(camera.x + viewportWidth / tileSize) + 1);
    const lastY = Math.min(state.map.height, Math.ceil(camera.y + viewportHeight / tileSize) + 1);

    context.fillStyle = "#151718";
    context.fillRect(0, 0, viewportWidth, viewportHeight);
    for (let y = firstY; y < lastY; y += 1) {
      for (let x = firstX; x < lastX; x += 1) drawTile(state.map.tiles[y][x], x, y, camera);
    }
    state.floor_items.forEach((item) => {
      const screen = worldToScreen(item, camera);
      if (item.key === "health_up") {
        context.fillStyle = "#77d484";
        context.fillRect(screen.x - 7, screen.y - 7, 14, 14);
        context.fillStyle = "#e8fff0";
        context.fillRect(screen.x - 2, screen.y - 5, 4, 10);
        context.fillRect(screen.x - 5, screen.y - 2, 10, 4);
      } else {
        context.fillStyle = item.key === "rifle" ? "#d58648" : "#e7c75c";
        const barrelLength = item.key === "rifle" ? 17 : 8;
        context.fillRect(screen.x - 7, screen.y - 4, 13, 8);
        context.fillRect(screen.x + 4, screen.y - 1, barrelLength, 3);
      }
      context.fillStyle = "#ffffff";
      context.font = "bold 10px system-ui";
      context.textAlign = "center";
      context.fillText(item.key === "health_up" ? "+" : item.key === "rifle" ? "R" : "P", screen.x, screen.y - 11);
    });
    state.enemies.forEach((enemy) => {
      const screen = worldToScreen(enemy, camera);
      context.fillStyle = "#d95b5b";
      context.fillRect(screen.x - 10, screen.y - 10, 20, 20);
      context.fillStyle = "#2a1d1d";
      context.fillRect(screen.x - 12, screen.y - 16, 24, 4);
      context.fillStyle = "#7fe080";
      context.fillRect(screen.x - 12, screen.y - 16, 24 * (enemy.health / enemy.max_health), 4);
    });
    state.projectiles.forEach((projectile) => {
      const screen = worldToScreen(projectile, camera);
      context.fillStyle = "#f5f2d0";
      context.fillRect(screen.x - 2, screen.y - 2, 4, 4);
    });
    const playerScreen = worldToScreen(visualPlayer, camera);
    context.fillStyle = "#63b3ed";
    context.fillRect(playerScreen.x - 10, playerScreen.y - 10, 20, 20);
  }
  requestAnimationFrame(drawFrame);
}

document.addEventListener("keydown", (event) => {
  const key = event.key.toLowerCase();
  if ("wasd".includes(key)) {
    event.preventDefault();
    if (!heldKeys.has(key)) {
      heldKeys.add(key);
      sendMovementInput();
    }
  } else if (key === "e" && !event.repeat) {
    event.preventDefault();
    sendAction({ type: "pickup" });
  } else if (key === "1" && !event.repeat) {
    event.preventDefault();
    sendAction({ type: "equip" });
  }
});

document.addEventListener("keyup", (event) => {
  if (heldKeys.delete(event.key.toLowerCase())) sendMovementInput();
});

window.addEventListener("blur", () => {
  if (heldKeys.size > 0) {
    heldKeys.clear();
    sendMovementInput();
  }
});

canvas.addEventListener("contextmenu", (event) => event.preventDefault());
canvas.addEventListener("mousedown", (event) => {
  if (event.button !== 2 || !state || !visualPlayer) return;
  const bounds = canvas.getBoundingClientRect();
  const camera = cameraForPlayer(visualPlayer);
  const screenX = (event.clientX - bounds.left) * (canvas.width / bounds.width);
  const screenY = (event.clientY - bounds.top) * (canvas.height / bounds.height);
  sendAction({
    type: "shoot",
    target: { x: camera.x + screenX / tileSize, y: camera.y + screenY / tileSize },
  });
});

refreshState();
setInterval(refreshState, 33);
requestAnimationFrame(drawFrame);
