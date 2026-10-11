// Cosmetic overlays are deliberately client-only: they read the snapshot but
// never affect movement, combat, or any other game state.
const cosmeticOverlays = new Map();

function registerCosmeticOverlay(kind, draw) {
  if (!cosmeticOverlays.has(kind)) cosmeticOverlays.set(kind, []);
  cosmeticOverlays.get(kind).push(draw);
}

function drawCosmeticOverlays(kind, entity, screen) {
  const overlays = cosmeticOverlays.get(kind) || [];
  overlays.forEach((draw) => draw(context, entity, screen));
}
