"""Entity storage and definition-to-instance construction."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Iterator, TypeVar


ComponentT = TypeVar("ComponentT")


@dataclass
class Entity:
    id: int
    def_key: str
    components: dict[type[object], object] = field(default_factory=dict)

    def add(self, component: object) -> None:
        self.components[type(component)] = component

    def remove(self, component_type: type[ComponentT]) -> ComponentT | None:
        component = self.components.pop(component_type, None)
        return component if isinstance(component, component_type) else None

    def get(self, component_type: type[ComponentT]) -> ComponentT | None:
        component = self.components.get(component_type)
        return component if isinstance(component, component_type) else None

    def require(self, component_type: type[ComponentT]) -> ComponentT:
        component = self.get(component_type)
        if component is None:
            raise KeyError(f"Entity {self.id} has no {component_type.__name__} component.")
        return component

    def has(self, *component_types: type[object]) -> bool:
        return all(component_type in self.components for component_type in component_types)


@dataclass(frozen=True)
class EntityDefinition:
    """A template whose mutable components are copied into each instance."""

    def_key: str
    components: tuple[object, ...]

    def __post_init__(self) -> None:
        component_types = [type(component) for component in self.components]
        if len(component_types) != len(set(component_types)):
            raise ValueError(f"Entity definition {self.def_key!r} repeats a component type.")

    def build(self, entity_id: int, overrides: tuple[object, ...] = ()) -> Entity:
        materialized = {type(component): deepcopy(component) for component in self.components}
        for component in overrides:
            materialized[type(component)] = deepcopy(component)
        return Entity(id=entity_id, def_key=self.def_key, components=materialized)


class EntityStore:
    """Owns entity identity and provides simple typed component queries."""

    def __init__(self, next_entity_id: int = 1) -> None:
        self.entities: dict[int, Entity] = {}
        self.next_entity_id = next_entity_id

    def create(self, definition: EntityDefinition, overrides: tuple[object, ...] = ()) -> Entity:
        entity = definition.build(self.next_entity_id, overrides)
        self.next_entity_id += 1
        self.entities[entity.id] = entity
        return entity

    def add(self, entity: Entity) -> None:
        if entity.id in self.entities:
            raise ValueError(f"Entity id {entity.id} already exists.")
        self.entities[entity.id] = entity
        self.next_entity_id = max(self.next_entity_id, entity.id + 1)

    def remove(self, entity_id: int) -> Entity | None:
        return self.entities.pop(entity_id, None)

    def remove_many(self, entity_ids: list[int] | set[int] | tuple[int, ...]) -> None:
        for entity_id in entity_ids:
            self.entities.pop(entity_id, None)

    def get(self, entity_id: int) -> Entity | None:
        return self.entities.get(entity_id)

    def require(self, entity_id: int) -> Entity:
        entity = self.get(entity_id)
        if entity is None:
            raise KeyError(f"Unknown entity id {entity_id}.")
        return entity

    def query(self, *component_types: type[object]) -> Iterator[Entity]:
        # Snapshot the collection so a system can safely gather structural changes
        # and apply them after its own traversal.
        return (
            entity
            for entity in tuple(self.entities.values())
            if entity.has(*component_types)
        )
