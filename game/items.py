"""Item definitions and inventory-facing helpers."""

from .models import ItemDefinition


ITEM_DEFINITIONS = {
    "pistol": ItemDefinition(
        key="pistol",
        name="Pistol",
        kind="weapon",
        equippable=True,
        damage=20,
        projectile_speed=11.0,
        projectile_lifetime=0.7,
    ),
    "rifle": ItemDefinition(
        key="rifle",
        name="Rifle",
        kind="weapon",
        equippable=True,
        damage=35,
        projectile_speed=24.0,
        projectile_lifetime=1.25,
    ),
    "health_up": ItemDefinition(
        key="health_up",
        name="Health Up",
        kind="consumable",
        healing=25,
    )
}


def get_item_definition(definition_key: str) -> ItemDefinition:
    return ITEM_DEFINITIONS[definition_key]


def is_equippable(definition_key: str) -> bool:
    return get_item_definition(definition_key).equippable
