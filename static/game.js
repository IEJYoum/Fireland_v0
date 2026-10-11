const canvas = document.querySelector("#game");
const context = canvas.getContext("2d");
const status = document.querySelector("#status");
const gameOverScreen = document.querySelector("#game-over");
const playAgainButton = document.querySelector("#play-again");
const tileSize = 32;
const viewportWidth = 960;
const viewportHeight = 640;
const heldKeys = new Set();
let state = null;
let visualPlayer = null;
let previousFrameTime = performance.now();
let stateRequestInFlight = false;

const weaponVisuals = {
  pistol: { color: "#e7c75c", length: 9 },
  rifle: { color: "#d58648", length: 16 },
  sniper_rifle: { color: "#8cbce8", length: 21 },
  knife: { color: "#d8e2e8", length: 11 },
};

const itemMarkers = { pistol: "P", rifle: "R", sniper_rifle: "S", knife: "K", health_up: "+" };

canvas.width = viewportWidth;
canvas.height = viewportHeight;

function equippedWeaponKey(player) {
  return player.inventory.find((item) => item.id === player.equipped_item_id)?.key;
}

function drawWeaponShape(drawingContext, weaponKey, screen, direction) {
  const visual = weaponVisuals[weaponKey];
  if (!visual) return;
  const angle = Math.atan2(direction.y, direction.x);
  drawingContext.save();
  drawingContext.translate(screen.x, screen.y);
  drawingContext.rotate(angle);
  if (weaponKey === "knife") {
    drawingContext.fillStyle = "#48352c";
    drawingContext.fillRect(-6, -2, 5, 4);
    drawingContext.fillStyle = visual.color;
    drawingContext.fillRect(-1, -1, visual.length, 2);
  } else {
    drawingContext.fillStyle = visual.color;
    drawingContext.fillRect(-3, -2, visual.length, 4);
    drawingContext.fillStyle = "#382c27";
    drawingContext.fillRect(-5, 1, 5, 4);
    if (weaponKey === "sniper_rifle") {
      drawingContext.fillStyle = "#25303a";
      drawingContext.fillRect(2, -5, 7, 2);
    }
  }
  drawingContext.restore();
}

// Add display-only details here. Each overlay receives the rendered entity
// and its camera-adjusted screen position, never gameplay/map coordinates.
registerCosmeticOverlay("pickup", (drawingContext, item, screen) => {
  drawingContext.fillStyle = "#ffffff";
  drawingContext.font = "bold 10px system-ui";
  drawingContext.textAlign = "center";
  drawingContext.fillText(itemMarkers[item.key] || "?", screen.x, screen.y - 11);
});

registerCosmeticOverlay("enemy", (drawingContext, enemy, screen) => {
  drawWeaponShape(drawingContext, enemy.weapon_key, { x: screen.x, y: screen.y + 5 }, { x: 1, y: 0 });
});

registerCosmeticOverlay("enemy", (drawingContext, enemy, screen) => {
  drawingContext.fillStyle = "#2a1d1d";
  drawingContext.fillRect(screen.x - 12, screen.y - 16, 24, 4);
  drawingContext.fillStyle = "#7fe080";
  drawingContext.fillRect(screen.x - 12, screen.y - 16, 24 * (enemy.health / enemy.max_health), 4);
});

registerCosmeticOverlay("player", (drawingContext, player, screen) => {
  const weaponKey = equippedWeaponKey(player);
  if (weaponKey) drawWeaponShape(drawingContext, weaponKey, screen, {
    x: player.facing_x,
    y: player.facing_y,
  });
});

registerCosmeticOverlay("player", (drawingContext, player, screen) => {
  // The face dot follows the last movement or aim direction.
  drawingContext.fillStyle = "#050505";
  drawingContext.fillRect(
    Math.round(screen.x + player.facing_x * 7) - 1,
    Math.round(screen.y + player.facing_y * 7) - 1,
    3,
    3,
  );
});

registerCosmeticOverlay("player", (drawingContext, player, screen) => {
  drawingContext.fillStyle = "#14212b";
  drawingContext.fillRect(screen.x - 12, screen.y - 17, 24, 4);
  drawingContext.fillStyle = "#79d890";
  drawingContext.fillRect(screen.x - 12, screen.y - 17, 24 * (player.health / player.max_health), 4);
});

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
  gameOverScreen.hidden = !state.game_over;
  const equipped = state.player.inventory.find((item) => item.id === state.player.equipped_item_id);
  const inventory = state.player.inventory.map((item) => item.name).join(", ") || "empty";
  status.innerHTML = [
    `<p>Health: ${state.player.health}/${state.player.max_health} &middot; Armor: ${state.player.armor} &middot; XP: ${state.player.xp}</p>`,
    `<p>Inventory: ${inventory} &middot; Equipped: ${equipped ? equipped.name : "none"} &middot; Hostiles: ${state.enemies.length}</p>`,
    `<p>Map: ${state.map.type} &middot; Level: ${state.world_position.level_index} &middot; Grid: (${state.world_position.x}, ${state.world_position.y}) &middot; Known maps: ${state.world_position.known_locations}</p>`,
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
  const colors = { floor: "#28352b", wall: "#46505a", tree: "#1d5b36", door_closed: "#a57437", level_exit: "#3f95a5" };
  context.fillStyle = colors[tile];
  context.fillRect(screenX, screenY, tileSize, tileSize);
  if (tile !== "floor") {
    context.strokeStyle = tile === "wall" ? "#64717c" : tile === "door_closed" ? "#e7b45f" : "#8ee6f2";
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
        drawWeaponShape(context, item.key, screen, { x: 1, y: 0 });
      }
      drawCosmeticOverlays("pickup", item, screen);
    });
    state.enemies.forEach((enemy) => {
      const screen = worldToScreen(enemy, camera);
      context.fillStyle = enemy.mode === "evade" ? "#b775d9" : "#d95b5b";
      context.fillRect(screen.x - 10, screen.y - 10, 20, 20);
      drawCosmeticOverlays("enemy", enemy, screen);
    });
    state.projectiles.forEach((projectile) => {
      const screen = worldToScreen(projectile, camera);
      context.fillStyle = "#f5f2d0";
      context.fillRect(screen.x - 2, screen.y - 2, 4, 4);
    });
    const playerScreen = worldToScreen(visualPlayer, camera);
    context.fillStyle = "#63b3ed";
    context.fillRect(playerScreen.x - 10, playerScreen.y - 10, 20, 20);
    drawCosmeticOverlays("player", state.player, playerScreen);
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
  if ((event.button !== 0 && event.button !== 2) || !state || !visualPlayer) return;
  const bounds = canvas.getBoundingClientRect();
  const camera = cameraForPlayer(visualPlayer);
  const screenX = (event.clientX - bounds.left) * (canvas.width / bounds.width);
  const screenY = (event.clientY - bounds.top) * (canvas.height / bounds.height);
  sendAction({
    type: "shoot",
    target: { x: camera.x + screenX / tileSize, y: camera.y + screenY / tileSize },
  });
});

playAgainButton.addEventListener("click", () => {
  heldKeys.clear();
  sendAction({ type: "restart" });
});

refreshState();
setInterval(refreshState, 33);
requestAnimationFrame(drawFrame);
