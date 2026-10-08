"""Coordinate entity."""

from dataclasses import dataclass
import math
from typing import Any, Dict, Optional


def _require_number(value: object, field_name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError("%s must be a finite int or float" % field_name)


@dataclass
class Coordinate:
    """Single engineering coordinate using Easting and Northing."""

    easting: float
    northing: float
    elevation: Optional[float] = None
    coordinate_system: Optional[str] = None

    def __post_init__(self) -> None:
        _require_number(self.easting, "easting")
        _require_number(self.northing, "northing")
        if self.elevation is not None:
            _require_number(self.elevation, "elevation")
        if self.coordinate_system is not None:
            if not isinstance(self.coordinate_system, str) or not self.coordinate_system.strip():
                raise ValueError("coordinate_system must be a non-empty string when provided")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "easting": self.easting,
            "northing": self.northing,
            "elevation": self.elevation,
            "coordinate_system": self.coordinate_system,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Coordinate":
        return cls(
            easting=data["easting"],
            northing=data["northing"],
            elevation=data.get("elevation"),
            coordinate_system=data.get("coordinate_system"),
        )
