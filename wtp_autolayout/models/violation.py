"""Violation entity."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .common import enum_from_value, require_id, require_non_negative
from .enums import Severity


@dataclass
class Violation:
    """Traceable engineering constraint violation."""

    violation_id: str
    constraint_id: str
    affected_units: List[str]
    penalty: float
    severity: Severity
    description: str = ""
    suggested_action: Optional[str] = None
    location: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_id(self.violation_id, "violation_id")
        require_id(self.constraint_id, "constraint_id")
        self.severity = enum_from_value(Severity, self.severity)
        require_non_negative(self.penalty, "penalty")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "violation_id": self.violation_id,
            "constraint_id": self.constraint_id,
            "affected_units": list(self.affected_units),
            "penalty": self.penalty,
            "severity": self.severity.value,
            "description": self.description,
            "suggested_action": self.suggested_action,
            "location": self.location,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Violation":
        return cls(
            violation_id=data["violation_id"],
            constraint_id=data["constraint_id"],
            affected_units=list(data.get("affected_units", [])),
            penalty=data["penalty"],
            severity=enum_from_value(Severity, data["severity"]),
            description=data.get("description", ""),
            suggested_action=data.get("suggested_action"),
            location=data.get("location"),
            metadata=data.get("metadata", {}),
        )
