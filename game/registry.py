"""Loud string-keyed behaviour lookup without storing callables on entities."""

from collections.abc import Callable
from typing import TypeVar


RoutineT = TypeVar("RoutineT", bound=Callable)


class BehaviorRegistry:
    def __init__(self, registry_name: str) -> None:
        self.registry_name = registry_name
        self._routines: dict[str, Callable] = {}

    def register(self, key: str, routine: RoutineT) -> RoutineT:
        if not key:
            raise ValueError("Behaviour keys cannot be empty.")
        if key in self._routines:
            raise ValueError(f"Duplicate {self.registry_name} behaviour key {key!r}.")
        self._routines[key] = routine
        return routine

    def lookup(self, key: str) -> Callable:
        try:
            return self._routines[key]
        except KeyError as error:
            raise KeyError(f"Unknown {self.registry_name} behaviour key {key!r}.") from error

    def has(self, key: str) -> bool:
        return key in self._routines
