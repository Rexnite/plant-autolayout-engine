"""Shared helpers for model validation and enum coercion."""

from enum import Enum
import math
from typing import Optional, Type, TypeVar


EnumT = TypeVar("EnumT", bound=Enum)


def require_id(value: str, field_name: str = "id") -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s is required" % field_name)


def require_positive(value: Optional[float], field_name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or
                              not math.isfinite(value) or value <= 0):
        raise ValueError("%s must be finite and positive when provided" % field_name)


def require_non_negative(value: Optional[float], field_name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or
                              not math.isfinite(value) or value < 0):
        raise ValueError("%s must be finite and non-negative" % field_name)


def require_non_negative_int(value: Optional[int], field_name: str) -> None:
    if value is not None and value < 0:
        raise ValueError("%s must be non-negative" % field_name)


def enum_from_value(enum_cls: Type[EnumT], value: object) -> EnumT:
    if isinstance(value, enum_cls):
        return value
    return enum_cls(value)
