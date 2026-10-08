"""Constraint engine for WTP AutoLayout Phase 4."""

from .base import BaseConstraint
from .engine import ConstraintEngine, default_wtp_engine
from .errors import ConstraintError
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

__all__ = [
    "BaseConstraint",
    "BoundaryContainmentConstraint",
    "ChemicalSafetyConstraint",
    "ConstraintEngine",
    "ConstraintError",
    "GeometryValidityConstraint",
    "GravityFlowConstraint",
    "MinimumClearanceConstraint",
    "OverlapConstraint",
    "ProcessAdjacencyConstraint",
    "ResidentialSeparationConstraint",
    "SludgeIsolationConstraint",
    "default_wtp_engine",
]
