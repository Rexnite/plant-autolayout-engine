"""Constraint engine orchestration."""

from typing import Iterable, List

from wtp_autolayout.geometry import GeometryEngine
from wtp_autolayout.models import Layout, Violation

from .base import BaseConstraint, ConstraintEvaluationContext
from .spatial import proximity_violations
from .site import site_violations
from wtp_autolayout.geometry.flow_topology import flow_crossings
from wtp_autolayout.models import Severity
from .engineering_constraints import (
    ChemicalSafetyConstraint,
    GravityFlowConstraint,
    ProcessAdjacencyConstraint,
    ResidentialSeparationConstraint,
    SludgeIsolationConstraint,
)
from .geometry_constraints import (
    BoundaryContainmentConstraint,
    GeometryValidityConstraint,
    MinimumClearanceConstraint,
    OverlapConstraint,
)


class ConstraintEngine:
    """Registry and evaluator for Phase 4 constraints."""

    def __init__(self, constraints: Iterable[BaseConstraint] = ()):
        self.constraints: List[BaseConstraint] = []
        for constraint in constraints:
            self.register_constraint(constraint)

    def register_constraint(self, constraint: BaseConstraint) -> None:
        self.constraints.append(constraint)

    def evaluate(self, layout: Layout) -> List[Violation]:
        return self.evaluate_enabled(layout)

    def evaluate_enabled(self, layout: Layout) -> List[Violation]:
        return self._evaluate(layout, include_disabled=False)

    def evaluate_all(self, layout: Layout) -> List[Violation]:
        return self._evaluate(layout, include_disabled=True)

    def _evaluate(self, layout: Layout, include_disabled: bool) -> List[Violation]:
        context = ConstraintEvaluationContext()
        violations: List[Violation] = []
        for constraint in self.constraints:
            if not include_disabled and not constraint.enabled:
                continue
            violations.extend(constraint.evaluate_with_context(layout, context))
        violations.extend(proximity_violations(layout))
        violations.extend(site_violations(layout))
        for first, second in flow_crossings(layout):
            violations.append(Violation(
                violation_id="flow-crossing-%s-%s" % (first, second), constraint_id="flow_crossing",
                affected_units=[], penalty=3.0, severity=Severity.LOW,
                description="Process flows %s and %s cross" % (first, second),
                suggested_action="Adjust unit placement to reduce route crossings.",
                metadata={"classification": "soft", "flow_edges": [first, second]},
            ))
        return violations

    @classmethod
    def default_wtp_engine(cls) -> "ConstraintEngine":
        return default_wtp_engine()


def default_wtp_engine() -> ConstraintEngine:
    """Create the default WTP constraint engine for Phase 4."""
    geometry_engine = GeometryEngine()
    return ConstraintEngine(
        [
            GeometryValidityConstraint(geometry_engine=geometry_engine),
            BoundaryContainmentConstraint(geometry_engine=geometry_engine),
            OverlapConstraint(geometry_engine=geometry_engine),
            MinimumClearanceConstraint(geometry_engine=geometry_engine),
            SludgeIsolationConstraint(),
            ChemicalSafetyConstraint(),
            ResidentialSeparationConstraint(),
            ProcessAdjacencyConstraint(),
            GravityFlowConstraint(),
        ]
    )


def default_core_engine() -> ConstraintEngine:
    """Plant-independent geometry and process connectivity checks."""
    geometry_engine = GeometryEngine()
    return ConstraintEngine([
        GeometryValidityConstraint(geometry_engine=geometry_engine),
        BoundaryContainmentConstraint(geometry_engine=geometry_engine),
        OverlapConstraint(geometry_engine=geometry_engine),
        MinimumClearanceConstraint(geometry_engine=geometry_engine),
        ProcessAdjacencyConstraint(),
    ])
