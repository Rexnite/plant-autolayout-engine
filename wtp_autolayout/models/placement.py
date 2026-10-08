"""Placement entity."""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, Optional

from .common import require_id, require_non_negative
from .coordinate import Coordinate


@dataclass
class Placement:
    """Computed or candidate spatial location for an engineering unit."""

    placement_id: str
    unit_id: str
    centroid: Coordinate
    rotation: float = 0.0
    geometry: Optional[Dict[str, Any]] = None
    bounding_geometry: Optional[Dict[str, Any]] = None
    occupied_area: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_id(self.placement_id, "placement_id")
        require_id(self.unit_id, "unit_id")
        if not isinstance(self.centroid, Coordinate):
            raise ValueError("Placement centroid must be a Coordinate object")
        if not isinstance(self.rotation, (int, float)) or isinstance(self.rotation, bool) or not math.isfinite(self.rotation):
            raise ValueError("rotation must be a finite number")
        require_non_negative(self.occupied_area, "occupied_area")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "placement_id": self.placement_id,
            "unit_id": self.unit_id,
            "centroid": self.centroid.to_dict(),
            "rotation": self.rotation,
            "geometry": self.geometry,
            "bounding_geometry": self.bounding_geometry,
            "occupied_area": self.occupied_area,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Placement":
        return cls(
            placement_id=data["placement_id"],
            unit_id=data["unit_id"],
            centroid=Coordinate.from_dict(data["centroid"]),
            rotation=data.get("rotation", 0.0),
            geometry=data.get("geometry"),
            bounding_geometry=data.get("bounding_geometry"),
            occupied_area=data.get("occupied_area"),
            metadata=data.get("metadata", {}),
        )
