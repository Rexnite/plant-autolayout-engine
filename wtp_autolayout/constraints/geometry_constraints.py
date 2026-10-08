"""Constraints backed by the Phase 3 geometry engine."""

from typing import List, Optional

from wtp_autolayout.geometry import GeometryEngine
from wtp_autolayout.models import ConstraintClassification, ConstraintType, Layout, Severity, Violation

from .base import BaseConstraint, ConstraintEvaluationContext


class GeometryConstraint(BaseConstraint):
    """Base class for constraints that consume GeometryEngine validation."""

    def __init__(self, geometry_engine=None, **kwargs):
        super().__init__(**kwargs)
        self.geometry_engine = geometry_engine or GeometryEngine()

    def _geometry_validation(self, layout: Layout, context: Optional[ConstraintEvaluationContext]):
        if context is None:
            return self.geometry_engine.validate_layout_geometry(layout)
        return context.geometry_validation(layout, self.geometry_engine)


class BoundaryContainmentConstraint(GeometryConstraint):
    def __init__(self, geometry_engine=None, enabled: bool = True):
        super().__init__(
            constraint_id="C-001",
            name="Boundary Containment",
            constraint_type=ConstraintType.BOUNDARY,
            classification=ConstraintClassification.HARD,
            severity=Severity.CRITICAL,
            weight=1.0,
            enabled=enabled,
            description="Every placed unit must remain inside the project boundary.",
            geometry_engine=geometry_engine,
        )

    def evaluate_with_context(self, layout: Layout, context: Optional[ConstraintEvaluationContext] = None) -> List[Violation]:
        result = self._geometry_validation(layout, context)
        violations = []
        for index, unit_id in enumerate(result.inside_boundary_violations, start=1):
            violations.append(
                self._violation(
                    suffix=str(index),
                    affected_units=[unit_id],
                    penalty=1_000_000.0,
                    description="Unit %s is outside the project boundary." % unit_id,
                    suggested_action="Move the unit fully inside the available boundary.",
                )
            )
        return violations


class OverlapConstraint(GeometryConstraint):
    def __init__(self, geometry_engine=None, enabled: bool = True):
        super().__init__(
            constraint_id="C-002",
            name="Engineering Unit Overlap",
            constraint_type=ConstraintType.OVERLAP,
            classification=ConstraintClassification.HARD,
            severity=Severity.CRITICAL,
            weight=1.0,
            enabled=enabled,
            description="Placed unit footprints must not overlap.",
            geometry_engine=geometry_engine,
        )

    def evaluate_with_context(self, layout: Layout, context: Optional[ConstraintEvaluationContext] = None) -> List[Violation]:
        result = self._geometry_validation(layout, context)
        violations = []
        for index, (unit_a, unit_b) in enumerate(result.overlap_violations, start=1):
            violations.append(
                self._violation(
                    suffix=str(index),
                    affected_units=[unit_a, unit_b],
                    penalty=1_000_000.0,
                    description="Units %s and %s overlap." % (unit_a, unit_b),
                    suggested_action="Reposition one or both units to eliminate footprint overlap.",
                )
            )
        return violations


class MinimumClearanceConstraint(GeometryConstraint):
    def __init__(self, geometry_engine=None, enabled: bool = True):
        super().__init__(
            constraint_id="C-003",
            name="Minimum Engineering Clearance",
            constraint_type=ConstraintType.SPACING,
            classification=ConstraintClassification.HARD,
            severity=Severity.CRITICAL,
            weight=1.0,
            enabled=enabled,
            description="Placed units must respect required clearance buffers.",
            geometry_engine=geometry_engine,
        )

    def evaluate_with_context(self, layout: Layout, context: Optional[ConstraintEvaluationContext] = None) -> List[Violation]:
        result = self._geometry_validation(layout, context)
        violations = []
        for index, (unit_a, unit_b) in enumerate(result.clearance_violations, start=1):
            violations.append(
                self._violation(
                    suffix=str(index),
                    affected_units=[unit_a, unit_b],
                    penalty=1_000_000.0,
                    description="Units %s and %s violate required clearance." % (unit_a, unit_b),
                    suggested_action="Increase spacing between the units.",
                )
            )
        return violations


class GeometryValidityConstraint(GeometryConstraint):
    def __init__(self, geometry_engine=None, enabled: bool = True):
        super().__init__(
            constraint_id="C-004",
            name="Engineering Geometry Validity",
            constraint_type=ConstraintType.GEOMETRY,
            classification=ConstraintClassification.HARD,
            severity=Severity.CRITICAL,
            weight=1.0,
            enabled=enabled,
            description="Boundary, placements and generated footprints must be valid geometries.",
            geometry_engine=geometry_engine,
        )

    def evaluate_with_context(self, layout: Layout, context: Optional[ConstraintEvaluationContext] = None) -> List[Violation]:
        result = self._geometry_validation(layout, context)
        violations = []
        for index, error in enumerate(result.invalid_geometry_errors, start=1):
            violations.append(
                self._violation(
                    suffix=str(index),
                    affected_units=[],
                    penalty=1_000_000.0,
                    description=error,
                    suggested_action="Correct the invalid boundary, unit, or placement input.",
                )
            )
        return violations
