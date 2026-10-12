const vitalsElement = document.querySelector("#vitals");
const equipmentElement = document.querySelector("#equipment");
const inventoryElement = document.querySelector("#inventory");
const messagesElement = document.querySelector("#messages");
const positionElement = document.querySelector("#position");
const worldStatusElement = document.querySelector("#world-status");
const connectionElement = document.querySelector("#connection");
const crosshairElement = document.querySelector("#crosshair");

function restartAnimation(element, className) {
  element.classList.remove(className);
  void element.offsetWidth;
  element.classList.add(className);
}

export function showShotFeedback() {
  restartAnimation(crosshairElement, "fired");
}

export function showConnection(message, isError = false) {
  connectionElement.textContent = message;
  connectionElement.style.color = isError ? "#ff8989" : "#9eb0ba";
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function meterHtml(label, current, maximum, className) {
  const ratio = maximum > 0 ? Math.max(0, Math.min(1, current / maximum)) : 0;
  return [
    '<div class="meter-row">',
    `<span>${label}</span><span>${Math.ceil(current)}/${maximum}</span>`,
    '</div>',
    '<div class="meter-track">',
    `<span class="meter-fill ${className}" style="width:${ratio * 100}%"></span>`,
    '</div>',
  ].join("");
}

const itemMarkers = {
  pistol: "P",
  rifle: "R",
  sniper_rifle: "S",
  knife: "K",
  health_up: "+",
  food: "F",
};

export function updateHud(snapshot) {
  const player = snapshot.entities.find((entity) => entity.id === snapshot.you.player_entity_id);
  if (!player) return;
  const components = player.components;
  const health = components.health;
  const hunger = components.hunger;
  const transform = components.transform;
  const grounded = components.grounded?.value ? "GROUND" : "AIR";
  const armor = components.armor?.value || 0;
  const xp = components.xp?.points || 0;
  vitalsElement.innerHTML = [
    health ? meterHtml("HEALTH", health.current, health.maximum, "health") : "",
    hunger ? meterHtml("HUNGER", hunger.current, hunger.maximum, "hunger") : "",
    `<div class="stat-line"><span>${grounded}</span><span>ARMOR ${armor}</span><span>XP ${xp}</span></div>`,
    `<div class="stat-line"><span>TIME ${snapshot.you.survival_seconds.toFixed(1)}s</span>${health?.current === 0 ? '<span class="dead">DEAD // R RESPAWN</span>' : ""}</div>`,
  ].join("");

  const entitiesById = new Map(snapshot.entities.map((entity) => [entity.id, entity]));
  const inventory = components.inventory || { item_ids: [], capacity: 0 };
  const equippedId = components.equipment?.equipped_item_id;
  const inventoryItems = inventory.item_ids
    .map((itemId) => entitiesById.get(itemId))
    .filter(Boolean);
  const equipped = equippedId ? entitiesById.get(equippedId) : null;
  equipmentElement.textContent = equipped?.components.item
    ? `HELD // ${equipped.components.item.display_name}`
    : "HELD // UNARMED";
  const slots = inventoryItems.map((entity) => {
    const item = entity.components.item;
    const marker = itemMarkers[entity.def_key] || "?";
    const equippedClass = entity.id === equippedId ? " equipped" : "";
    return `<span class="inventory-slot${equippedClass}" title="${escapeHtml(item?.display_name || entity.def_key)}"><b>${marker}</b><small>${escapeHtml(item?.display_name || entity.def_key)}</small></span>`;
  });
  for (let index = slots.length; index < inventory.capacity; index += 1) {
    slots.push('<span class="inventory-slot empty"></span>');
  }
  inventoryElement.innerHTML = slots.join("");

  messagesElement.innerHTML = (snapshot.messages || [])
    .map((message) => `<div>${escapeHtml(message)}</div>`)
    .join("");
  positionElement.textContent = `XYZ ${transform.x.toFixed(2)} ${transform.y.toFixed(2)} ${transform.z.toFixed(2)} // CHUNK ${snapshot.world.player_chunk.join(",")}`;
  worldStatusElement.textContent = `BIOME ${snapshot.world.biome.toUpperCase()} // HOSTILES ${snapshot.debug.visible_hostiles} // ENT ${snapshot.debug.visible_entities} // CHUNKS ${snapshot.debug.active_chunks}/${snapshot.debug.resident_chunks} // TICK ${snapshot.server_tick}`;
  showConnection(`WORLD ${snapshot.world_id} // SCHEMA ${snapshot.schema_version}`);
}
