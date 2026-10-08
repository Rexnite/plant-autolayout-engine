"""JSON serialization helpers for nested dataclasses and enums."""

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Callable, TypeVar


T = TypeVar("T")


def to_serializable(value: Any) -> Any:
    """Convert supported model values into JSON-safe Python objects."""
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return to_serializable(asdict(value))
    if isinstance(value, list):
        return [to_serializable(item) for item in value]
    if isinstance(value, tuple):
        return [to_serializable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_serializable(item) for key, item in value.items()}
    return value


def to_json(value: Any, **json_kwargs: Any) -> str:
    """Serialize a model, enum, or nested structure to JSON."""
    return json.dumps(to_serializable(value), **json_kwargs)


def from_json(json_text: str, factory: Callable[[Any], T]) -> T:
    """Deserialize JSON and pass the decoded value to a model factory."""
    return factory(json.loads(json_text))
