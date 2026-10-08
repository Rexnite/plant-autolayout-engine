"""Geometry engine for WTP AutoLayout Phase 3."""

from .engine import GeometryEngine, LayoutGeometryValidationResult
from .errors import GeometryError
from .shapes import boundary_to_polygon, unit_to_geometry

__all__ = [
    "GeometryEngine",
    "GeometryError",
    "LayoutGeometryValidationResult",
    "boundary_to_polygon",
    "unit_to_geometry",
]
