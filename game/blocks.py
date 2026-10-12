"""Immutable block definitions shared by simulation and wire snapshots."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BlockDefinition:
    key: str
    solid: bool
    material_key: str


BLOCK_DEFINITIONS = {
    "air": BlockDefinition("air", solid=False, material_key="air"),
    "grass": BlockDefinition("grass", solid=True, material_key="grass"),
    "dirt": BlockDefinition("dirt", solid=True, material_key="dirt"),
    "stone": BlockDefinition("stone", solid=True, material_key="stone"),
    "wood": BlockDefinition("wood", solid=True, material_key="wood"),
    "leaves": BlockDefinition("leaves", solid=True, material_key="leaves"),
    "door": BlockDefinition("door", solid=True, material_key="door"),
}

AIR_BLOCK_KEY = "air"


def get_block_definition(key: str) -> BlockDefinition:
    try:
        return BLOCK_DEFINITIONS[key]
    except KeyError as error:
        raise KeyError(f"Unknown block definition {key!r}.") from error
