async function requestJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${detail}`);
  }
  return response.json();
}

export function fetchState() {
  return requestJson("/api/state");
}

export function fetchChunk(chunkX, chunkZ) {
  return requestJson(`/api/chunks/${chunkX}/${chunkZ}`);
}

export function sendAction(payload) {
  return requestJson("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
