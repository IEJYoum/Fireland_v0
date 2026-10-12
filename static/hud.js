const vitalsElement = document.querySelector("#vitals");
const positionElement = document.querySelector("#position");
const connectionElement = document.querySelector("#connection");

export function showConnection(message, isError = false) {
  connectionElement.textContent = message;
  connectionElement.style.color = isError ? "#ff8989" : "#9eb0ba";
}

export function updateHud(snapshot) {
  const player = snapshot.entities.find((entity) => entity.id === snapshot.you.player_entity_id);
  if (!player) return;
  const components = player.components;
  const health = components.health;
  const transform = components.transform;
  const grounded = components.grounded?.value ? "GROUND" : "AIR";
  vitalsElement.textContent = health ? `HP ${health.current}/${health.maximum} // ${grounded}` : grounded;
  positionElement.textContent = `XYZ ${transform.x.toFixed(2)}  ${transform.y.toFixed(2)}  ${transform.z.toFixed(2)} // TICK ${snapshot.server_tick}`;
  showConnection(`WORLD ${snapshot.world_id} // SCHEMA ${snapshot.schema_version}`);
}
