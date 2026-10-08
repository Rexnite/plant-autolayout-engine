"""Constraint entity."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .common import enum_from_value, require_id, require_non_negative
from .enums import ConstraintClassification, ConstraintType, Severity


@dataclass
class Constraint:
    """Engineering rule that can be evaluated by later engine phases."""

    constraint_id: str
    name: str
    constraint_type: ConstraintType
    classification: ConstraintClassification
    severity: Severity
    description: str = ""
    evaluation_reference: Optional[str] = None
    penalty_reference: Optional[str] = None
    weight: float = 1.0
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_id(self.constraint_id, "constraint_id")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name is required")
        self.constraint_type = enum_from_value(ConstraintType, self.constraint_type)
        self.classification = enum_from_value(ConstraintClassification, self.classification)
        self.severity = enum_from_value(Severity, self.severity)
        require_non_negative(self.weight, "weight")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "name": self.name,
            "constraint_type": self.constraint_type.value,
            "classification": self.classification.value,
            "severity": self.severity.value,
            "description": self.description,
            "evaluation_reference": self.evaluation_reference,
            "penalty_reference": self.penalty_reference,
            "weight": self.weight,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Constraint":
        return cls(
            constraint_id=data["constraint_id"],
            name=data["name"],
            constraint_type=enum_from_value(ConstraintType, data["constraint_type"]),
            classification=enum_from_value(ConstraintClassification, data["classification"]),
            severity=enum_from_value(Severity, data["severity"]),
            description=data.get("description", ""),
            evaluation_reference=data.get("evaluation_reference"),
            penalty_reference=data.get("penalty_reference"),
            weight=data.get("weight", 1.0),
            enabled=data.get("enabled", True),
            metadata=data.get("metadata", {}),
        )
