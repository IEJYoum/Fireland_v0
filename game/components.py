"""Typed capability data for entities. Systems own all behaviour."""

from dataclasses import dataclass, field

from .vectors import Aabb, Vec3, ZERO_VEC3


@dataclass
class Transform:
    position: Vec3
    yaw: float = 0.0
    pitch: float = 0.0


@dataclass
class Velocity:
    value: Vec3 = ZERO_VEC3


@dataclass
class ControlVelocity:
    """Horizontal movement intent recomputed by a controller or AI."""

    value: Vec3 = ZERO_VEC3


@dataclass
class Collider:
    box: Aabb


@dataclass
class Gravity:
    """Marker: the physics system applies gravity to this entity."""


@dataclass
class AlwaysActive:
    """Marker: systems step this entity even when no player is nearby."""


@dataclass
class Grounded:
    value: bool = False


@dataclass
class Health:
    current: int
    maximum: int


@dataclass
class Inventory:
    item_ids: list[int] = field(default_factory=list)


@dataclass
class Equipment:
    equipped_item_id: int | None = None


@dataclass
class Think:
    routine: str
    cadence_hz: float = 10.0
    seconds_until_tick: float = 0.0


@dataclass
class ControlledBy:
    session_id: str


@dataclass
class Pickup:
    kind: str = "interact"


@dataclass
class Drops:
    pool: str


@dataclass
class Spawner:
    routine: str
    interval_seconds: float
    seconds_until_spawn: float = 0.0


@dataclass
class Lifetime:
    seconds: float


@dataclass
class Damage:
    amount: int


@dataclass
class Owner:
    entity_id: int


@dataclass
class Renderable:
    appearance_key: str


@dataclass
class Weapon:
    damage: int
    max_distance: float
    cooldown_seconds: float
    seconds_until_ready: float = 0.0
