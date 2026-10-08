"""Infrastructure entities for roads and drains."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .common import require_id, require_non_negative, require_positive
from .coordinate import Coordinate


@dataclass
class Road:
    """Internal access road or corridor."""

    road_id: str
    path: List[Coordinate] = field(default_factory=list)
    width: Optional[float] = None
    road_type: Optional[str] = None
    connected_units: List[str] = field(default_factory=list)
    maintenance_priority: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_id(self.road_id, "road_id")
        for point in self.path:
            if not isinstance(point, Coordinate):
                raise ValueError("Road path must contain Coordinate objects")
        require_positive(self.width, "width")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "road_id": self.road_id,
            "path": [point.to_dict() for point in self.path],
            "width": self.width,
            "road_type": self.road_type,
            "connected_units": list(self.connected_units),
            "maintenance_priority": self.maintenance_priority,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Road":
        return cls(
            road_id=data["road_id"],
            path=[Coordinate.from_dict(item) for item in data.get("path", [])],
            width=data.get("width"),
            road_type=data.get("road_type"),
            connected_units=list(data.get("connected_units", [])),
            maintenance_priority=data.get("maintenance_priority"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Drain:
    """Drainage path used by later drainage-aware layout phases."""

    drain_id: str
    path: List[Coordinate] = field(default_factory=list)
    flow_direction: Optional[str] = None
    start_point: Optional[Coordinate] = None
    end_point: Optional[Coordinate] = None
    design_capacity: Optional[float] = None
    ground_elevation: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_id(self.drain_id, "drain_id")
        for point in self.path:
            if not isinstance(point, Coordinate):
                raise ValueError("Drain path must contain Coordinate objects")
        if self.start_point is not None and not isinstance(self.start_point, Coordinate):
            raise ValueError("Drain start_point must be a Coordinate object")
        if self.end_point is not None and not isinstance(self.end_point, Coordinate):
            raise ValueError("Drain end_point must be a Coordinate object")
        require_non_negative(self.design_capacity, "design_capacity")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drain_id": self.drain_id,
            "path": [point.to_dict() for point in self.path],
            "flow_direction": self.flow_direction,
            "start_point": self.start_point.to_dict() if self.start_point else None,
            "end_point": self.end_point.to_dict() if self.end_point else None,
            "design_capacity": self.design_capacity,
            "ground_elevation": self.ground_elevation,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Drain":
        return cls(
            drain_id=data["drain_id"],
            path=[Coordinate.from_dict(item) for item in data.get("path", [])],
            flow_direction=data.get("flow_direction"),
            start_point=Coordinate.from_dict(data["start_point"]) if data.get("start_point") else None,
            end_point=Coordinate.from_dict(data["end_point"]) if data.get("end_point") else None,
            design_capacity=data.get("design_capacity"),
            ground_elevation=data.get("ground_elevation"),
            metadata=data.get("metadata", {}),
        )
