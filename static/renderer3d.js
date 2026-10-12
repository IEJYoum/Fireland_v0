import * as THREE from "three";

const CHUNK_SIZE = 16;
const RENDER_DISTANCE_CHUNKS = 4;
const BLOCK_COLORS = {
  grass: 0x477a45,
  dirt: 0x765238,
  stone: 0x6d7479,
  wood: 0x855d35,
  leaves: 0x245f35,
  door: 0xa96f32,
};

export class FirelandRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x030508);
    this.scene.fog = new THREE.Fog(0x030508, 24, 58);
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    this.firstPersonCamera = new THREE.PerspectiveCamera(72, 1, 0.05, 90);
    this.topCamera = new THREE.OrthographicCamera(-18, 18, 12, -12, 0.1, 100);
    this.sideCamera = new THREE.OrthographicCamera(-18, 18, 12, -12, 0.1, 100);
    this.cameraMode = "first";
    this.localPlayerId = null;
    this.entityMeshes = new Map();
    this.entityTargets = new Map();
    this.chunkGroups = new Map();
    this.chunkRevisions = new Map();
    this.shotEffects = [];

    this.scene.add(new THREE.HemisphereLight(0xa8cbe0, 0x202018, 1.7));
    const sunlight = new THREE.DirectionalLight(0xffffff, 1.3);
    sunlight.position.set(12, 24, 8);
    this.scene.add(sunlight);

    this.blockGeometry = new THREE.BoxGeometry(1, 1, 1);
    this.blockMaterials = new Map(
      Object.entries(BLOCK_COLORS).map(([key, color]) => [
        key,
        new THREE.MeshLambertMaterial({ color }),
      ]),
    );
    window.addEventListener("resize", () => this.resize());
    this.resize();
  }

  setCameraMode(mode) {
    if (!["first", "top", "side"].includes(mode)) return;
    this.cameraMode = mode;
    document.body.dataset.camera = mode;
    document.querySelectorAll("[data-camera]").forEach((button) => {
      button.classList.toggle("active", button.dataset.camera === mode);
    });
  }

  resize() {
    const width = this.canvas.clientWidth || window.innerWidth;
    const height = this.canvas.clientHeight || window.innerHeight;
    this.renderer.setSize(width, height, false);
    this.firstPersonCamera.aspect = width / height;
    this.firstPersonCamera.updateProjectionMatrix();
    const vertical = 13;
    const horizontal = vertical * (width / height);
    for (const camera of [this.topCamera, this.sideCamera]) {
      camera.left = -horizontal;
      camera.right = horizontal;
      camera.top = vertical;
      camera.bottom = -vertical;
      camera.updateProjectionMatrix();
    }
  }

  chunkKey(x, z) {
    return `${x},${z}`;
  }

  hasChunkRevision(x, z, revision) {
    return this.chunkRevisions.get(this.chunkKey(x, z)) === revision;
  }

  setChunk(chunk) {
    const key = this.chunkKey(chunk.x, chunk.z);
    if (this.chunkRevisions.get(key) === chunk.revision) return;
    const previous = this.chunkGroups.get(key);
    if (previous) this.scene.remove(previous);

    const group = new THREE.Group();
    group.position.set(chunk.x * CHUNK_SIZE, 0, chunk.z * CHUNK_SIZE);
    const blocksByType = new Map();
    for (const block of chunk.blocks) {
      const [x, y, z, blockKey] = block;
      if (!blocksByType.has(blockKey)) blocksByType.set(blockKey, []);
      blocksByType.get(blockKey).push({ x, y, z });
    }
    const matrix = new THREE.Matrix4();
    for (const [blockKey, blocks] of blocksByType) {
      const material = this.blockMaterials.get(blockKey) || this.blockMaterials.get("stone");
      const mesh = new THREE.InstancedMesh(this.blockGeometry, material, blocks.length);
      blocks.forEach((block, index) => {
        matrix.makeTranslation(block.x + 0.5, block.y + 0.5, block.z + 0.5);
        mesh.setMatrixAt(index, matrix);
      });
      mesh.instanceMatrix.needsUpdate = true;
      group.add(mesh);
    }
    this.scene.add(group);
    this.chunkGroups.set(key, group);
    this.chunkRevisions.set(key, chunk.revision);
  }

  unloadDistantChunks(playerPosition) {
    for (const [key, group] of this.chunkGroups) {
      const [chunkX, chunkZ] = key.split(",").map(Number);
      const playerChunkX = Math.floor(playerPosition.x / CHUNK_SIZE);
      const playerChunkZ = Math.floor(playerPosition.z / CHUNK_SIZE);
      if (Math.max(Math.abs(chunkX - playerChunkX), Math.abs(chunkZ - playerChunkZ)) > RENDER_DISTANCE_CHUNKS) {
        this.scene.remove(group);
        this.chunkGroups.delete(key);
        this.chunkRevisions.delete(key);
      }
    }
  }

  isChunkNearPlayer(descriptor, playerPosition) {
    const playerChunkX = Math.floor(playerPosition.x / CHUNK_SIZE);
    const playerChunkZ = Math.floor(playerPosition.z / CHUNK_SIZE);
    return Math.max(Math.abs(descriptor.x - playerChunkX), Math.abs(descriptor.z - playerChunkZ)) <= RENDER_DISTANCE_CHUNKS;
  }

  createEntityMesh(entity) {
    const collider = entity.components.collider || { half_x: 0.3, height: 1, half_z: 0.3 };
    const appearance = entity.components.renderable?.appearance_key;
    const colors = {
      player: 0x4aa8e8,
      enemy: 0xd95757,
      pistol: 0xf0ca62,
      rifle: 0xd58648,
      sniper_rifle: 0x8cbce8,
      knife: 0xd8e2e8,
      health_up: 0x77d484,
      food: 0xe6bd55,
      pickup: 0xf0ca62,
    };
    const material = new THREE.MeshLambertMaterial({ color: colors[appearance] || 0xd7dce0 });
    return new THREE.Mesh(
      new THREE.BoxGeometry(collider.half_x * 2, collider.height, collider.half_z * 2),
      material,
    );
  }

  showShot(shot) {
    if (!shot.origin || !shot.end) return;
    const origin = new THREE.Vector3(shot.origin.x, shot.origin.y, shot.origin.z);
    const end = new THREE.Vector3(shot.end.x, shot.end.y, shot.end.z);
    const direction = end.clone().sub(origin);
    const distance = direction.length();
    if (distance <= 0) return;
    direction.divideScalar(distance);

    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(this.firstPersonCamera.quaternion);
    const down = new THREE.Vector3(0, -1, 0).applyQuaternion(this.firstPersonCamera.quaternion);
    const start = origin.clone()
      .addScaledVector(direction, Math.min(0.35, distance * 0.25))
      .addScaledVector(right, 0.12)
      .addScaledVector(down, 0.1);
    const geometry = new THREE.BufferGeometry().setFromPoints([start, end]);
    const material = new THREE.LineBasicMaterial({
      color: shot.hit_kind === "entity" ? 0xfff0a0 : 0xffd36a,
      depthTest: false,
      opacity: 0.95,
      transparent: true,
    });
    const line = new THREE.Line(geometry, material);
    line.renderOrder = 20;
    this.scene.add(line);
    this.shotEffects.push({ line, expiresAt: performance.now() + 90 });
  }

  updateShotEffects(now) {
    const active = [];
    for (const effect of this.shotEffects) {
      const remaining = effect.expiresAt - now;
      if (remaining <= 0) {
        this.scene.remove(effect.line);
        effect.line.geometry.dispose();
        effect.line.material.dispose();
        continue;
      }
      effect.line.material.opacity = Math.min(0.95, remaining / 45);
      active.push(effect);
    }
    this.shotEffects = active;
  }

  updateSnapshot(snapshot) {
    this.localPlayerId = snapshot.you.player_entity_id;
    const seen = new Set();
    for (const entity of snapshot.entities) {
      const transform = entity.components.transform;
      if (!transform || !entity.components.renderable) continue;
      seen.add(entity.id);
      let mesh = this.entityMeshes.get(entity.id);
      if (!mesh) {
        mesh = this.createEntityMesh(entity);
        mesh.position.set(transform.x, transform.y, transform.z);
        this.entityMeshes.set(entity.id, mesh);
        this.scene.add(mesh);
      }
      const height = entity.components.collider?.height || 1;
      this.entityTargets.set(entity.id, new THREE.Vector3(transform.x, transform.y + height / 2, transform.z));
      mesh.visible = !(this.cameraMode === "first" && entity.id === this.localPlayerId);
    }
    for (const [entityId, mesh] of this.entityMeshes) {
      if (!seen.has(entityId)) {
        this.scene.remove(mesh);
        mesh.geometry.dispose();
        mesh.material.dispose();
        this.entityMeshes.delete(entityId);
        this.entityTargets.delete(entityId);
      }
    }
  }

  render(yaw, pitch, frameSeconds) {
    this.updateShotEffects(performance.now());
    const playerMesh = this.entityMeshes.get(this.localPlayerId);
    const playerTarget = this.entityTargets.get(this.localPlayerId);
    if (!playerMesh || !playerTarget) return;
    const smoothing = Math.min(1, frameSeconds * 18);
    for (const [entityId, target] of this.entityTargets) {
      this.entityMeshes.get(entityId)?.position.lerp(target, smoothing);
    }
    playerMesh.visible = this.cameraMode !== "first";
    const feetY = playerMesh.position.y - playerMesh.geometry.parameters.height / 2;
    const focus = new THREE.Vector3(playerMesh.position.x, feetY + 0.9, playerMesh.position.z);
    let camera;
    if (this.cameraMode === "first") {
      camera = this.firstPersonCamera;
      camera.position.set(focus.x, feetY + 1.65, focus.z);
      camera.rotation.order = "YXZ";
      camera.rotation.set(pitch, yaw, 0);
    } else if (this.cameraMode === "top") {
      camera = this.topCamera;
      camera.position.set(focus.x, focus.y + 32, focus.z + 0.001);
      camera.up.set(0, 0, -1);
      camera.lookAt(focus);
    } else {
      camera = this.sideCamera;
      camera.position.set(focus.x + 32, focus.y + 6, focus.z);
      camera.up.set(0, 1, 0);
      camera.lookAt(focus);
    }
    this.renderer.render(this.scene, camera);
  }
}
