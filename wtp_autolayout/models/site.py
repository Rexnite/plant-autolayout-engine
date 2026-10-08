"""Typed, fixed site features and preliminary access corridors."""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, List

from .common import enum_from_value, require_id
from .coordinate import Coordinate
from .enums import ConstraintClassification


class SiteZoneType(str, Enum):
    EXCLUSION = "exclusion"
    RESTRICTED = "restricted"
    RESERVED = "reserved"
    EXPANSION = "expansion"


class CorridorType(str, Enum):
    ACCESS = "access"
    ROAD = "road"
    UTILITY = "utility"
    ROUTING = "routing"


def _coordinates(values, minimum):
    if len(values) < minimum or any(not isinstance(value, Coordinate) for value in values):
        raise ValueError("site geometry requires at least %s Coordinate objects" % minimum)


def _non_negative(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("%s must be finite and non-negative" % name)


@dataclass
class SiteZone:
    zone_id: str
    name: str
    vertices: List[Coordinate]
    zone_type: SiteZoneType
    classification: ConstraintClassification = ConstraintClassification.HARD
    clearance: float = 0.0
    weight: float = 1.0
    description: str = ""
    provenance: str = "user_entered"

    def __post_init__(self):
        require_id(self.zone_id, "zone_id")
        require_id(self.name, "name")
        _coordinates(self.vertices, 3)
        self.zone_type = enum_from_value(SiteZoneType, self.zone_type)
        self.classification = enum_from_value(ConstraintClassification, self.classification)
        _non_negative(self.clearance, "clearance")
        _non_negative(self.weight, "weight")

    def to_dict(self):
        return {"zone_id": self.zone_id, "name": self.name,
                "vertices": [item.to_dict() for item in self.vertices],
                "zone_type": self.zone_type.value, "classification": self.classification.value,
                "clearance": self.clearance, "weight": self.weight,
                "description": self.description, "provenance": self.provenance}

    @classmethod
    def from_dict(cls, data):
        return cls(data["zone_id"], data.get("name") or data["zone_id"],
                   [Coordinate.from_dict(item) for item in data["vertices"]],
                   data["zone_type"], data.get("classification") or "hard",
                   data.get("clearance") or 0.0, data.get("weight") if data.get("weight") is not None else 1.0,
                   data.get("description", ""), data.get("provenance", "user_entered"))


@dataclass
class ExistingStructure:
    structure_id: str
    name: str
    vertices: List[Coordinate]
    clearance: float = 0.0
    description: str = ""
    provenance: str = "user_entered"

    def __post_init__(self):
        require_id(self.structure_id, "structure_id")
        require_id(self.name, "name")
        _coordinates(self.vertices, 3)
        _non_negative(self.clearance, "clearance")

    def to_dict(self):
        return {"structure_id": self.structure_id, "name": self.name,
                "vertices": [item.to_dict() for item in self.vertices],
                "clearance": self.clearance, "description": self.description,
                "provenance": self.provenance}

    @classmethod
    def from_dict(cls, data):
        return cls(data["structure_id"], data.get("name") or data["structure_id"],
                   [Coordinate.from_dict(item) for item in data["vertices"]],
                   data.get("clearance") or 0.0, data.get("description", ""),
                   data.get("provenance", "user_entered"))


@dataclass
class Corridor:
    corridor_id: str
    name: str
    path: List[Coordinate]
    corridor_type: CorridorType
    width: float = 0.0
    classification: ConstraintClassification = ConstraintClassification.SOFT
    setback: float = 0.0
    description: str = ""
    provenance: str = "user_entered"

    def __post_init__(self):
        require_id(self.corridor_id, "corridor_id")
        require_id(self.name, "name")
        _coordinates(self.path, 2)
        self.corridor_type = enum_from_value(CorridorType, self.corridor_type)
        self.classification = enum_from_value(ConstraintClassification, self.classification)
        _non_negative(self.width, "width")
        _non_negative(self.setback, "setback")

    def to_dict(self):
        return {"corridor_id": self.corridor_id, "name": self.name,
                "path": [item.to_dict() for item in self.path],
                "corridor_type": self.corridor_type.value, "width": self.width,
                "classification": self.classification.value, "setback": self.setback,
                "description": self.description, "provenance": self.provenance}

    @classmethod
    def from_dict(cls, data):
        return cls(data["corridor_id"], data.get("name") or data["corridor_id"],
                   [Coordinate.from_dict(item) for item in data["path"]],
                   data["corridor_type"], data.get("width") or 0.0,
                   data.get("classification") or "soft", data.get("setback") or 0.0,
                   data.get("description", ""), data.get("provenance", "user_entered"))
