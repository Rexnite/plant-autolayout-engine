"""User-defined pairwise footprint distance checks."""

from typing import Dict, List

from wtp_autolayout.geometry import GeometryEngine
from wtp_autolayout.models import ConstraintClassification, Layout, Severity, SpatialRelationshipType, Violation


def proximity_results(layout: Layout, geometry_engine=None) -> List[Dict[str, object]]:
    engine = geometry_engine or GeometryEngine()
    units = {unit.unit_id: unit for unit in layout.units}
    placements = {placement.unit_id: placement for placement in layout.placements}
    results = []
    geometries = {}
    for item in layout.proximity_relationships:
        if item.unit_id_a not in placements or item.unit_id_b not in placements:
            continue
        for unit_id in (item.unit_id_a, item.unit_id_b):
            if unit_id not in geometries:
                geometries[unit_id] = engine.unit_to_geometry(units[unit_id], placements[unit_id])
        a = geometries[item.unit_id_a]
        b = geometries[item.unit_id_b]
        actual = engine.distance(a, b)
        if item.relationship_type == SpatialRelationshipType.MIN_DISTANCE:
            deviation = max(0.0, item.distance - actual)
        elif item.relationship_type in (SpatialRelationshipType.MAX_DISTANCE, SpatialRelationshipType.PREFERRED_NEAR):
            deviation = max(0.0, actual - item.distance)
        else:
            deviation = abs(actual - item.distance)
        results.append({"relationship_id": item.relationship_id, "unit_id_a": item.unit_id_a,
                        "unit_id_b": item.unit_id_b, "requirement": item.relationship_type.value,
                        "actual_distance": actual, "required_distance": item.distance,
                        "classification": item.classification.value, "passed": deviation <= 1e-6,
                        "deviation": deviation, "penalty": deviation * item.weight,
                        "source": "user_entered", "distance_basis": "footprint_gap",
                        "satisfied": deviation <= 1e-6, "weight": item.weight})
    return results


def proximity_violations(layout: Layout, geometry_engine=None) -> List[Violation]:
    violations = []
    for result in proximity_results(layout, geometry_engine):
        if result["passed"]:
            continue
        hard = result["classification"] == ConstraintClassification.HARD.value
        violations.append(Violation(
            violation_id="proximity-%s" % result["relationship_id"],
            constraint_id="proximity:%s" % result["relationship_id"],
            affected_units=[result["unit_id_a"], result["unit_id_b"]],
            penalty=(100.0 if hard else 0.0) + result["penalty"],
            severity=Severity.HIGH if hard else Severity.LOW,
            description="%s requires %s %.2f; actual footprint distance %.2f" % (
                result["relationship_id"], result["requirement"], result["required_distance"], result["actual_distance"]),
            suggested_action="Adjust the pairwise separation.",
            metadata={"classification": result["classification"], "actual_distance": result["actual_distance"],
                      "required_distance": result["required_distance"], "deviation": result["deviation"]},
        ))
    return violations
