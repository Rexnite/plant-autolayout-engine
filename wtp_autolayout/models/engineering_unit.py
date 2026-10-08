"""Engineering unit entity."""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, Optional

from .common import enum_from_value, require_id, require_non_negative, require_positive
from .enums import ConstraintClassification, HazardLevel, ShapeType, UnitCategory


@dataclass
class EngineeringUnit:
    """Physical treatment plant structure or facility."""

    unit_id: str
    name: str
    category: UnitCategory
    shape_type: ShapeType
    width: Optional[float] = None
    length: Optional[float] = None
    diameter: Optional[float] = None
    area: Optional[float] = None
    required_clearance: float = 0.0
    preferred_orientation: Optional[float] = None
    hazard_level: HazardLevel = HazardLevel.LOW
    system_group: Optional[str] = None
    elevation_requirement: Optional[float] = None
    process_order: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    access_required: bool = False
    max_access_distance: Optional[float] = None
    access_classification: ConstraintClassification = ConstraintClassification.SOFT
    maintenance_clearance: float = 0.0

    def __post_init__(self) -> None:
        require_id(self.unit_id, "unit_id")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name is required")

        self.category = enum_from_value(UnitCategory, self.category)
        self.shape_type = enum_from_value(ShapeType, self.shape_type)
        self.hazard_level = enum_from_value(HazardLevel, self.hazard_level)

        require_positive(self.width, "width")
        require_positive(self.length, "length")
        require_positive(self.diameter, "diameter")
        require_non_negative(self.required_clearance, "required_clearance")
        require_non_negative(self.area, "area")
        if not isinstance(self.access_required, bool):
            raise ValueError("access_required must be a boolean")
        for key in ("max_access_distance", "maintenance_clearance"):
            value = getattr(self, key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or
                                      not math.isfinite(value) or value < 0):
                raise ValueError("%s must be a finite non-negative number" % key)
        self.access_classification = enum_from_value(ConstraintClassification, self.access_classification)

        if self.shape_type in (ShapeType.RECTANGLE, ShapeType.SQUARE):
            if self.width is None or self.length is None:
                raise ValueError("%s units require width and length" % self.shape_type.value)
            if self.diameter is not None:
                raise ValueError("%s units must not define diameter" % self.shape_type.value)
            if self.shape_type == ShapeType.SQUARE and self.width != self.length:
                raise ValueError("square units require equal width and length")
        elif self.shape_type == ShapeType.CIRCLE:
            if self.diameter is None:
                raise ValueError("circle units require diameter")
            if self.width is not None or self.length is not None:
                raise ValueError("circle units must not define width or length")
        elif self.shape_type == ShapeType.POLYGON:
            if self.width is not None or self.length is not None or self.diameter is not None:
                raise ValueError("polygon units must not define width, length, or diameter")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "name": self.name,
            "category": self.category.value,
            "shape_type": self.shape_type.value,
            "width": self.width,
            "length": self.length,
            "diameter": self.diameter,
            "area": self.area,
            "required_clearance": self.required_clearance,
            "preferred_orientation": self.preferred_orientation,
            "hazard_level": self.hazard_level.value,
            "system_group": self.system_group,
            "elevation_requirement": self.elevation_requirement,
            "process_order": self.process_order,
            "metadata": self.metadata,
            "access_required": self.access_required,
            "max_access_distance": self.max_access_distance,
            "access_classification": self.access_classification.value,
            "maintenance_clearance": self.maintenance_clearance,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EngineeringUnit":
        return cls(
            unit_id=data["unit_id"],
            name=data["name"],
            category=enum_from_value(UnitCategory, data["category"]),
            shape_type=enum_from_value(ShapeType, data["shape_type"]),
            width=data.get("width"),
            length=data.get("length"),
            diameter=data.get("diameter"),
            area=data.get("area"),
            required_clearance=data.get("required_clearance", 0.0),
            preferred_orientation=data.get("preferred_orientation"),
            hazard_level=enum_from_value(HazardLevel, data.get("hazard_level", HazardLevel.LOW.value)),
            system_group=data.get("system_group"),
            elevation_requirement=data.get("elevation_requirement"),
            process_order=data.get("process_order"),
            metadata=data.get("metadata", {}),
            access_required=data.get("access_required", False),
            max_access_distance=data.get("max_access_distance"),
            access_classification=data.get("access_classification", "soft"),
            maintenance_clearance=data.get("maintenance_clearance", 0.0),
        )
