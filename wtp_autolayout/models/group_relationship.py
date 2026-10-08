"""Explicit group-to-group nearest-member footprint rules."""

from dataclasses import dataclass
from enum import Enum
import math

from .common import enum_from_value, require_id
from .enums import ConstraintClassification


class GroupRelationshipType(str, Enum):
    PREFERRED_NEAR = "preferred_near"
    MIN_DISTANCE = "min_distance"
    MAX_DISTANCE = "max_distance"
    NEUTRAL = "neutral"


@dataclass
class GroupRelationship:
    relationship_id: str
    group_id_a: str
    group_id_b: str
    relationship_type: GroupRelationshipType
    distance: float = 0.0
    classification: ConstraintClassification = ConstraintClassification.SOFT
    weight: float = 1.0

    def __post_init__(self):
        require_id(self.relationship_id, "relationship_id")
        require_id(self.group_id_a, "group_id_a")
        require_id(self.group_id_b, "group_id_b")
        if self.group_id_a == self.group_id_b:
            raise ValueError("group relationship requires distinct groups")
        self.relationship_type = enum_from_value(GroupRelationshipType, self.relationship_type)
        self.classification = enum_from_value(ConstraintClassification, self.classification)
        if self.relationship_type == GroupRelationshipType.PREFERRED_NEAR and self.classification == ConstraintClassification.HARD:
            raise ValueError("preferred_near must be soft")
        for name in ("distance", "weight"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("%s must be finite and non-negative" % name)

    def to_dict(self):
        return {"relationship_id": self.relationship_id, "group_id_a": self.group_id_a,
                "group_id_b": self.group_id_b, "relationship_type": self.relationship_type.value,
                "distance": self.distance, "classification": self.classification.value,
                "weight": self.weight}

    @classmethod
    def from_dict(cls, data):
        return cls(data["relationship_id"], data["group_id_a"], data["group_id_b"],
                   data["relationship_type"], data.get("distance") if data.get("distance") is not None else 0.0,
                   data.get("classification") or "soft",
                   data.get("weight") if data.get("weight") is not None else 1.0)
