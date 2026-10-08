"""Boundary entity."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .common import require_id
from .coordinate import Coordinate


@dataclass
class Boundary:
    """Project land boundary represented by ordered vertices."""

    boundary_id: str
    vertices: List[Coordinate]
    area: Optional[float] = None
    perimeter: Optional[float] = None
    bounding_box: Optional[Dict[str, Any]] = None
    centroid: Optional[Coordinate] = None
    elevation_model: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_id(self.boundary_id, "boundary_id")
        if len(self.vertices) < 3:
            raise ValueError("Boundary requires at least 3 coordinates")
        for vertex in self.vertices:
            if not isinstance(vertex, Coordinate):
                raise ValueError("Boundary vertices must be Coordinate objects")
        if self.centroid is not None and not isinstance(self.centroid, Coordinate):
            raise ValueError("Boundary centroid must be a Coordinate object")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "boundary_id": self.boundary_id,
            "vertices": [vertex.to_dict() for vertex in self.vertices],
            "area": self.area,
            "perimeter": self.perimeter,
            "bounding_box": self.bounding_box,
            "centroid": self.centroid.to_dict() if self.centroid else None,
            "elevation_model": self.elevation_model,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Boundary":
        return cls(
            boundary_id=data["boundary_id"],
            vertices=[Coordinate.from_dict(item) for item in data.get("vertices", [])],
            area=data.get("area"),
            perimeter=data.get("perimeter"),
            bounding_box=data.get("bounding_box"),
            centroid=Coordinate.from_dict(data["centroid"]) if data.get("centroid") else None,
            elevation_model=data.get("elevation_model"),
            metadata=data.get("metadata", {}),
        )
