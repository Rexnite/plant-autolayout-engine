"""Core Shapely-backed geometry engine."""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from wtp_autolayout.models import Boundary, EngineeringUnit, Layout, Placement

from .clearance import clearance_geometry
from .errors import GeometryError
from .shapes import boundary_to_polygon as make_boundary_polygon
from .shapes import unit_to_geometry as make_unit_geometry


@dataclass
class LayoutGeometryValidationResult:
    """Pure geometry validation details for a candidate layout."""

    inside_boundary_violations: List[str] = field(default_factory=list)
    overlap_violations: List[Tuple[str, str]] = field(default_factory=list)
    clearance_violations: List[Tuple[str, str]] = field(default_factory=list)
    invalid_geometry_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "inside_boundary_violations": list(self.inside_boundary_violations),
            "overlap_violations": [list(pair) for pair in self.overlap_violations],
            "clearance_violations": [list(pair) for pair in self.clearance_violations],
            "invalid_geometry_errors": list(self.invalid_geometry_errors),
        }


class GeometryEngine:
    """Geometry utilities for Phase 3 validation."""

    def boundary_to_polygon(self, boundary: Boundary):
        return make_boundary_polygon(boundary)

    def unit_to_geometry(self, unit: EngineeringUnit, placement: Placement):
        return make_unit_geometry(unit, placement)

    def unit_to_clearance_geometry(self, unit: EngineeringUnit, placement: Placement):
        return clearance_geometry(unit, self.unit_to_geometry(unit, placement))

    def is_inside_boundary(self, unit_geometry, boundary_geometry) -> bool:
        return boundary_geometry.covers(unit_geometry)

    def overlaps(self, geometry_a, geometry_b) -> bool:
        if geometry_a.equals(geometry_b):
            return True
        intersection = geometry_a.intersection(geometry_b)
        return (not intersection.is_empty) and intersection.area > 0

    def distance(self, geometry_a, geometry_b) -> float:
        return float(geometry_a.distance(geometry_b))

    def clearance_violation(
        self,
        unit_a: EngineeringUnit,
        placement_a: Placement,
        unit_b: EngineeringUnit,
        placement_b: Placement,
    ) -> bool:
        geometry_a = self.unit_to_geometry(unit_a, placement_a)
        geometry_b = self.unit_to_geometry(unit_b, placement_b)
        clearance_a = clearance_geometry(unit_a, geometry_a)
        clearance_b = clearance_geometry(unit_b, geometry_b)
        clearance_intersection = clearance_a.intersection(clearance_b)
        if (not clearance_intersection.is_empty) and clearance_intersection.area > 0:
            return True
        footprint_b_in_clearance_a = clearance_a.intersection(geometry_b)
        if (not footprint_b_in_clearance_a.is_empty) and footprint_b_in_clearance_a.area > 0:
            return True
        footprint_a_in_clearance_b = clearance_b.intersection(geometry_a)
        return (not footprint_a_in_clearance_b.is_empty) and footprint_a_in_clearance_b.area > 0

    def validate_layout_geometry(self, layout: Layout) -> LayoutGeometryValidationResult:
        result = LayoutGeometryValidationResult()

        try:
            boundary_geometry = self.boundary_to_polygon(layout.boundary)
        except GeometryError as error:
            result.invalid_geometry_errors.append("boundary: %s" % error)
            return result

        units_by_id = {unit.unit_id: unit for unit in layout.units}
        geometries: Dict[str, object] = {}
        clearances: Dict[str, object] = {}
        placements_by_unit_id: Dict[str, Placement] = {}

        for placement in layout.placements:
            if placement.unit_id in placements_by_unit_id:
                result.invalid_geometry_errors.append(
                    "duplicate placement for unit_id %s: %s and %s"
                    % (
                        placement.unit_id,
                        placements_by_unit_id[placement.unit_id].placement_id,
                        placement.placement_id,
                    )
                )
                continue
            placements_by_unit_id[placement.unit_id] = placement
            unit = units_by_id.get(placement.unit_id)
            if unit is None:
                result.invalid_geometry_errors.append("placement %s references missing unit %s" % (placement.placement_id, placement.unit_id))
                continue
            try:
                geometry = self.unit_to_geometry(unit, placement)
            except GeometryError as error:
                result.invalid_geometry_errors.append("%s: %s" % (unit.unit_id, error))
                continue
            geometries[unit.unit_id] = geometry
            try:
                clearances[unit.unit_id] = clearance_geometry(unit, geometry)
            except GeometryError as error:
                result.invalid_geometry_errors.append("%s clearance: %s" % (unit.unit_id, error))
            if not self.is_inside_boundary(geometry, boundary_geometry):
                result.inside_boundary_violations.append(unit.unit_id)

        for unit_id in units_by_id:
            if unit_id not in placements_by_unit_id:
                result.invalid_geometry_errors.append("missing placement for unit_id %s" % unit_id)

        unit_ids = list(geometries.keys())
        for index, unit_id_a in enumerate(unit_ids):
            for unit_id_b in unit_ids[index + 1 :]:
                geometry_a = geometries[unit_id_a]
                geometry_b = geometries[unit_id_b]
                envelope_a = clearances.get(unit_id_a, geometry_a).bounds
                envelope_b = clearances.get(unit_id_b, geometry_b).bounds
                if (envelope_a[2] < envelope_b[0] or envelope_b[2] < envelope_a[0] or
                        envelope_a[3] < envelope_b[1] or envelope_b[3] < envelope_a[1]):
                    continue
                if self.overlaps(geometry_a, geometry_b):
                    result.overlap_violations.append((unit_id_a, unit_id_b))
                if unit_id_a in clearances and unit_id_b in clearances:
                    clearance_a = clearances[unit_id_a]
                    clearance_b = clearances[unit_id_b]
                    if (clearance_a.intersection(clearance_b).area > 0 or
                            clearance_a.intersection(geometry_b).area > 0 or
                            clearance_b.intersection(geometry_a).area > 0):
                        result.clearance_violations.append((unit_id_a, unit_id_b))

        return result
