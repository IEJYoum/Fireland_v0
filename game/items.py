"""Item entity definitions shared by players, enemies, pickups, and drops."""

from __future__ import annotations

from .components import Collider, Consumable, Item, Pickup, Renderable, Transform, Weapon
from .entities import Entity, EntityDefinition, EntityStore
from .vectors import Aabb, Vec3


ITEM_COLLIDER = Collider(Aabb(half_x=0.18, height=0.28, half_z=0.18))


ITEM_DEFINITIONS: dict[str, EntityDefinition] = {
    "pistol": EntityDefinition(
        "pistol",
        (
            ITEM_COLLIDER,
            Item("Pistol", "weapon", projectile_speed=11.0, projectile_lifetime=0.7),
            Renderable("pistol"),
            Weapon(damage=20, max_distance=11.0 * 0.7, cooldown_seconds=0.30),
        ),
    ),
    "rifle": EntityDefinition(
        "rifle",
        (
            ITEM_COLLIDER,
            Item("Rifle", "weapon", projectile_speed=24.0, projectile_lifetime=1.25),
            Renderable("rifle"),
            Weapon(damage=35, max_distance=24.0 * 1.25, cooldown_seconds=0.18),
        ),
    ),
    "sniper_rifle": EntityDefinition(
        "sniper_rifle",
        (
            ITEM_COLLIDER,
            Item("Sniper Rifle", "weapon", projectile_speed=40.0, projectile_lifetime=1.6),
            Renderable("sniper_rifle"),
            Weapon(damage=65, max_distance=40.0 * 1.6, cooldown_seconds=0.80),
        ),
    ),
    "knife": EntityDefinition(
        "knife",
        (
            ITEM_COLLIDER,
            Item("Knife", "weapon"),
            Renderable("knife"),
            Weapon(damage=45, max_distance=1.2, cooldown_seconds=0.45, attack_style="melee"),
        ),
    ),
    "health_up": EntityDefinition(
        "health_up",
        (
            ITEM_COLLIDER,
            Item("Health Up", "consumable"),
            Consumable("heal", 25),
            Renderable("health_up"),
        ),
    ),
    "food": EntityDefinition(
        "food",
        (
            ITEM_COLLIDER,
            Item("Food", "food"),
            Consumable("hunger", 35),
            Renderable("food"),
        ),
    ),
}


WEAPON_KEYS = tuple(
    key
    for key, definition in ITEM_DEFINITIONS.items()
    if any(isinstance(component, Weapon) for component in definition.components)
)


def require_item_definition(item_key: str) -> EntityDefinition:
    try:
        return ITEM_DEFINITIONS[item_key]
    except KeyError as error:
        raise KeyError(f"Unknown item definition {item_key!r}.") from error


def create_item(entities: EntityStore, item_key: str) -> Entity:
    return entities.create(require_item_definition(item_key))


def spawn_item(entities: EntityStore, item_key: str, position: Vec3) -> Entity:
    return entities.create(
        require_item_definition(item_key),
        (Transform(position), Pickup()),
    )


def place_item_as_pickup(item: Entity, position: Vec3) -> None:
    item.add(Transform(position))
    item.add(Pickup())
