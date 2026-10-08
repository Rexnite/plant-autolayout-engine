"""Explicit footprint-to-footprint distance requirements."""

import math
from dataclasses import dataclass
from typing import Any, Dict

from .common import enum_from_value, require_id
from .enums import ConstraintClassification, SpatialRelationshipType


@dataclass
class SpatialRelationship:
    relationship_id: str
    unit_id_a: str
    unit_id_b: str
    relationship_type: SpatialRelationshipType
    distance: float
    classification: ConstraintClassification = ConstraintClassification.SOFT
    weight: float = 1.0

    def __post_init__(self) -> None:
        require_id(self.relationship_id, "relationship_id")
        require_id(self.unit_id_a, "unit_id_a")
        require_id(self.unit_id_b, "unit_id_b")
        if self.unit_id_a == self.unit_id_b:
            raise ValueError("spatial relationship requires two different units")
        self.relationship_type = enum_from_value(SpatialRelationshipType, self.relationship_type)
        self.classification = enum_from_value(ConstraintClassification, self.classification)
        for key in ("distance", "weight"):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("%s must be a finite non-negative number" % key)
        if self.relationship_type == SpatialRelationshipType.PREFERRED_NEAR and self.classification == ConstraintClassification.HARD:
            raise ValueError("preferred_near is a soft preference")

    def to_dict(self) -> Dict[str, Any]:
        return {"relationship_id": self.relationship_id, "unit_id_a": self.unit_id_a,
                "unit_id_b": self.unit_id_b, "relationship_type": self.relationship_type.value,
                "distance": self.distance, "classification": self.classification.value, "weight": self.weight}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpatialRelationship":
        return cls(data["relationship_id"], data["unit_id_a"], data["unit_id_b"],
                   data["relationship_type"], data["distance"], data.get("classification", "soft"),
                   data.get("weight", 1.0))
