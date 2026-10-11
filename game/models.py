"""Data containers used by the game rules.  Behaviour lives in other modules."""

import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Vector:
    """A world-space coordinate measured in tile units."""

    x: float
    y: float


@dataclass
class MapRequest:
    width: int = 80
    height: int = 50
    seed: int = 1
    generator_name: str = "room"


@dataclass
class TileMap:
    width: int
    height: int
    tiles: list[list[str]]
    seed: int
    generator_name: str
    prefab_kinds: list[str] = field(default_factory=list)
    buildings: list["Building"] = field(default_factory=list)


@dataclass(frozen=True)
class ItemDefinition:
    key: str
    name: str
    kind: str
    equippable: bool = False
    damage: int = 0
    projectile_speed: float = 0.0
    projectile_lifetime: float = 0.0
    attack_style: str = "projectile"
    attack_range: float = 0.0
    healing: int = 0


@dataclass
class ItemInstance:
    id: int
    definition_key: str


@dataclass
class FloorItem:
    id: int
    item_id: int
    position: Vector


@dataclass
class Player:
    id: int
    position: Vector
    health: int = 100
    max_health: int = 100
    armor: int = 0
    xp: int = 0
    level: int = 1
    inventory: list[int] = field(default_factory=list)
    equipped_item_id: int | None = None
    movement: Vector = field(default_factory=lambda: Vector(0.0, 0.0))
    facing: Vector = field(default_factory=lambda: Vector(0.0, 1.0))


@dataclass
class Projectile:
    id: int
    x: float
    y: float
    velocity_x: float
    velocity_y: float
    damage: int
    owner_kind: str
    remaining_seconds: float = 0.7


@dataclass
class Enemy:
    id: int
    position: Vector
    health: int = 60
    max_health: int = 60
    armor: int = 0
    equipped_item_id: int = 0
    fire_cooldown: float = 0.0
    mode: str = "chase"
    seconds_until_mode_roll: float = 1.0
    evade_target: Vector | None = None


@dataclass
class Building:
    kind: str
    interior_cells: list[tuple[int, int]]
    has_door: bool


@dataclass
class MapLocation:
    tile_map: TileMap
    floor_items: dict[int, FloorItem]
    enemies: dict[int, Enemy]


@dataclass
class Game:
    tile_map: TileMap
    player: Player
    item_instances: dict[int, ItemInstance]
    floor_items: dict[int, FloorItem]
    projectiles: dict[int, Projectile] = field(default_factory=dict)
    enemies: dict[int, Enemy] = field(default_factory=dict)
    next_entity_id: int = 1
    elapsed_seconds: float = 0.0
    messages: list[str] = field(default_factory=list)
    randomizer: random.Random = field(default_factory=random.Random)
    game_over: bool = False
    world_position: tuple[int, int] = (0, 0)
    world_locations: dict[tuple[int, int], MapLocation] = field(default_factory=dict)
    level_index: int = 1
