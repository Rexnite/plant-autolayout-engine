"""Base constraint abstraction."""

from dataclasses import dataclass
from typing import List, Optional

from wtp_autolayout.models import (
    Constraint,
    ConstraintClassification,
    ConstraintType,
    Layout,
    Severity,
    Violation,
)


class ConstraintEvaluationContext:
    """Lightweight per-evaluation cache shared by constraints."""

    def __init__(self) -> None:
        self._geometry_results = {}

    def geometry_validation(self, layout: Layout, geometry_engine):
        cache_key = id(geometry_engine)
        if cache_key not in self._geometry_results:
            self._geometry_results[cache_key] = geometry_engine.validate_layout_geometry(layout)
        return self._geometry_results[cache_key]


@dataclass
class BaseConstraint:
    """Base class for Phase 4 engineering constraints."""

    constraint_id: str
    name: str
    constraint_type: ConstraintType
    classification: ConstraintClassification
    severity: Severity
    weight: float = 1.0
    enabled: bool = True
    description: str = ""

    def evaluate(self, layout: Layout) -> List[Violation]:
        return self.evaluate_with_context(layout, None)

    def evaluate_with_context(
        self,
        layout: Layout,
        context: Optional[ConstraintEvaluationContext] = None,
    ) -> List[Violation]:
        raise NotImplementedError

    def to_model(self) -> Constraint:
        return Constraint(
            constraint_id=self.constraint_id,
            name=self.name,
            constraint_type=self.constraint_type,
            classification=self.classification,
            severity=self.severity,
            weight=self.weight,
            enabled=self.enabled,
            description=self.description,
        )

    def _violation(
        self,
        suffix: str,
        affected_units: List[str],
        penalty: float,
        description: str,
        suggested_action: str,
        location=None,
    ) -> Violation:
        return Violation(
            violation_id="%s-%s" % (self.constraint_id, suffix),
            constraint_id=self.constraint_id,
            affected_units=affected_units,
            penalty=penalty * self.weight,
            severity=self.severity,
            description=description,
            suggested_action=suggested_action,
            location=location,
        )
