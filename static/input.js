const MOVEMENT_KEYS = new Set(["KeyW", "KeyA", "KeyS", "KeyD"]);

export class InputController {
  constructor(canvas, onCameraMode, onGameplayAction) {
    this.canvas = canvas;
    this.onCameraMode = onCameraMode;
    this.onGameplayAction = onGameplayAction;
    this.heldKeys = new Set();
    this.sequence = 0;
    this.yaw = 0;
    this.pitch = 0;
    this.jumpPending = false;
    this.dirty = true;
    this.lastSentAt = 0;
    this.pointerSensitivity = 0.0022;

    document.addEventListener("keydown", (event) => this.onKeyDown(event));
    document.addEventListener("keyup", (event) => this.onKeyUp(event));
    document.addEventListener("mousemove", (event) => this.onMouseMove(event));
    window.addEventListener("blur", () => this.releaseMovement());
  }

  onKeyDown(event) {
    if (MOVEMENT_KEYS.has(event.code)) {
      event.preventDefault();
      if (!this.heldKeys.has(event.code)) {
        this.heldKeys.add(event.code);
        this.dirty = true;
      }
      return;
    }
    if (event.code === "Space") {
      event.preventDefault();
      if (!event.repeat) {
        this.jumpPending = true;
        this.dirty = true;
      }
      return;
    }
    if (event.code === "KeyE" && !event.repeat) {
      event.preventDefault();
      this.onGameplayAction("interact", null);
      return;
    }
    if (event.code === "KeyQ" && !event.repeat) {
      event.preventDefault();
      this.onGameplayAction("equip_next", null);
      return;
    }
    if (event.code === "KeyF" && !event.repeat) {
      event.preventDefault();
      this.onGameplayAction("eat", null);
      return;
    }
    if (event.code === "KeyR" && !event.repeat) {
      event.preventDefault();
      this.onGameplayAction("restart", null);
      return;
    }
    const cameraModes = { Digit1: "first", Digit2: "top", Digit3: "side" };
    if (cameraModes[event.code] && !event.repeat) this.onCameraMode(cameraModes[event.code]);
  }

  lookDirection() {
    const cosPitch = Math.cos(this.pitch);
    return {
      x: -Math.sin(this.yaw) * cosPitch,
      y: Math.sin(this.pitch),
      z: -Math.cos(this.yaw) * cosPitch,
    };
  }

  onKeyUp(event) {
    if (this.heldKeys.delete(event.code)) this.dirty = true;
  }

  onMouseMove(event) {
    if (document.pointerLockElement !== this.canvas) return;
    this.yaw -= event.movementX * this.pointerSensitivity;
    this.pitch -= event.movementY * this.pointerSensitivity;
    const pitchLimit = Math.PI / 2 - 0.01;
    this.pitch = Math.max(-pitchLimit, Math.min(pitchLimit, this.pitch));
    this.dirty = true;
  }

  releaseMovement() {
    if (this.heldKeys.size > 0) {
      this.heldKeys.clear();
      this.dirty = true;
    }
  }

  takeCommand(now = performance.now()) {
    if (!this.dirty && now - this.lastSentAt < 1000) return null;
    this.sequence += 1;
    this.lastSentAt = now;
    const command = {
      type: "input",
      sequence: this.sequence,
      forward: Number(this.heldKeys.has("KeyW")) - Number(this.heldKeys.has("KeyS")),
      strafe: Number(this.heldKeys.has("KeyD")) - Number(this.heldKeys.has("KeyA")),
      yaw: this.yaw,
      pitch: this.pitch,
      jump: this.jumpPending,
    };
    this.jumpPending = false;
    this.dirty = false;
    return command;
  }
}
