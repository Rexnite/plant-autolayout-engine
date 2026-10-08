"""Generic site occupancy, access, and inter-group diagnostics."""

from wtp_autolayout.geometry import GeometryEngine
from wtp_autolayout.geometry.site import (access_geometries, hard_site_obstacles,
                                          corridor_geometry, structure_geometry, zone_geometry)
from wtp_autolayout.models import ConstraintClassification, GroupRelationshipType, Severity, Violation


def _footprints(layout, engine):
    units = {unit.unit_id: unit for unit in layout.units}
    return {placement.unit_id: engine.unit_to_geometry(units[placement.unit_id], placement)
            for placement in layout.placements if placement.unit_id in units}


def site_results(layout, geometry_engine=None):
    if not (layout.site_zones or layout.existing_structures or layout.corridors or
            layout.metadata.get("exclusion_zones")):
        return []
    engine = geometry_engine or GeometryEngine()
    footprints = _footprints(layout, engine)
    units = {unit.unit_id: unit for unit in layout.units}
    features = [(zone.zone_id, zone_geometry(zone).buffer(zone.clearance), zone.classification.value,
                 zone.weight, zone.zone_type.value, zone.provenance) for zone in layout.site_zones]
    features += [(structure.structure_id, structure_geometry(structure).buffer(structure.clearance),
                  "hard", 1.0, "existing_structure", structure.provenance)
                 for structure in layout.existing_structures]
    features += [(corridor.corridor_id, corridor_geometry(corridor).buffer(corridor.setback),
                  "hard", 1.0, "corridor", corridor.provenance)
                 for corridor in layout.corridors if corridor.classification == ConstraintClassification.HARD]
    # Legacy metadata exclusions remain hard no-build features.
    features += [(name, shape, "hard", 1.0, "exclusion", "legacy_metadata")
                 for name, shape in hard_site_obstacles(layout) if name.startswith("legacy_exclusion_")]
    rows = []
    for unit_id, footprint in footprints.items():
        clearance = max(units[unit_id].required_clearance, units[unit_id].maintenance_clearance)
        occupied = footprint.buffer(clearance) if clearance else footprint
        for feature_id, feature, classification, weight, kind, source in features:
            area = occupied.intersection(feature).area
            if area <= 1e-8:
                continue
            rows.append({"unit_id": unit_id, "feature_id": feature_id, "feature_type": kind,
                         "classification": classification, "occupied_area": area,
                         "clearance": clearance, "penalty": area * weight,
                         "provenance": source, "satisfied": False})
    return rows


def access_results(layout, geometry_engine=None):
    if not any(unit.access_required for unit in layout.units):
        return []
    engine = geometry_engine or GeometryEngine()
    footprints = _footprints(layout, engine)
    paths = access_geometries(layout)
    rows = []
    for unit in layout.units:
        if not unit.access_required or unit.unit_id not in footprints:
            continue
        nearest = min(((name, footprints[unit.unit_id].distance(shape)) for name, shape in paths),
                      key=lambda item: item[1], default=(None, None))
        maximum = unit.max_access_distance
        satisfied = maximum is None or (nearest[1] is not None and nearest[1] <= maximum + 1e-6)
        deviation = 0.0 if satisfied else (nearest[1] - maximum if nearest[1] is not None else maximum or 1.0)
        rows.append({"unit_id": unit.unit_id, "access_required": True,
                     "nearest_corridor": nearest[0], "actual_distance": nearest[1],
                     "required_maximum": maximum, "classification": unit.access_classification.value,
                     "satisfied": satisfied, "deviation": deviation, "penalty": deviation,
                     "provenance": "user_entered"})
    return rows


def group_relationship_results(layout, geometry_engine=None):
    if not layout.group_relationships:
        return []
    engine = geometry_engine or GeometryEngine()
    footprints = _footprints(layout, engine)
    members = {}
    for unit in layout.units:
        if unit.system_group and unit.unit_id in footprints:
            members.setdefault(unit.system_group, []).append((unit.unit_id, footprints[unit.unit_id]))
    rows = []
    for item in layout.group_relationships:
        pairs = [(a, b, shape_a.distance(shape_b))
                 for a, shape_a in members.get(item.group_id_a, [])
                 for b, shape_b in members.get(item.group_id_b, [])]
        if not pairs:
            continue
        unit_a, unit_b, actual = min(pairs, key=lambda entry: entry[2])
        if item.relationship_type == GroupRelationshipType.MIN_DISTANCE:
            deviation = max(0.0, item.distance - actual)
        elif item.relationship_type in (GroupRelationshipType.MAX_DISTANCE, GroupRelationshipType.PREFERRED_NEAR):
            deviation = max(0.0, actual - item.distance)
        elif item.relationship_type == GroupRelationshipType.NEUTRAL:
            deviation = 0.0
        else:
            deviation = abs(actual - item.distance)
        rows.append({"relationship_id": item.relationship_id,
                     "group_id_a": item.group_id_a, "group_id_b": item.group_id_b,
                     "nearest_unit_a": unit_a, "nearest_unit_b": unit_b,
                     "requirement": item.relationship_type.value,
                     "required_distance": item.distance, "actual_distance": actual,
                     "deviation": deviation, "classification": item.classification.value,
                     "satisfied": deviation <= 1e-6, "penalty": deviation * item.weight,
                     "distance_basis": "nearest_member_footprint_gap", "provenance": "user_entered"})
    return rows


def site_violations(layout):
    violations = []
    for row in site_results(layout):
        hard = row["classification"] == "hard"
        violations.append(Violation(
            violation_id="site-%s-%s" % (row["feature_id"], row["unit_id"]),
            constraint_id="site:%s" % row["feature_id"],
            affected_units=[row["unit_id"]], penalty=(100.0 if hard else 0.0) + row["penalty"],
            severity=Severity.HIGH if hard else Severity.LOW,
            description="Unit %s occupies %.2f area of %s" % (row["unit_id"], row["occupied_area"], row["feature_id"]),
            suggested_action="Move the unit clear of the fixed site feature.",
            metadata={"classification": row["classification"], **row}))
    for row in access_results(layout):
        if row["satisfied"]:
            continue
        hard = row["classification"] == "hard"
        violations.append(Violation(
            violation_id="access-%s" % row["unit_id"], constraint_id="access:%s" % row["unit_id"],
            affected_units=[row["unit_id"]], penalty=(100.0 if hard else 0.0) + row["penalty"],
            severity=Severity.HIGH if hard else Severity.LOW,
            description="Unit %s requires access within %.2f; actual %s" % (
                row["unit_id"], row["required_maximum"], row["actual_distance"]),
            suggested_action="Move the unit closer to an access/road corridor.",
            metadata={"classification": row["classification"], **row}))
    for row in group_relationship_results(layout):
        if row["satisfied"]:
            continue
        hard = row["classification"] == "hard"
        violations.append(Violation(
            violation_id="group-%s" % row["relationship_id"],
            constraint_id="group:%s" % row["relationship_id"],
            affected_units=[row["nearest_unit_a"], row["nearest_unit_b"]],
            penalty=(100.0 if hard else 0.0) + row["penalty"],
            severity=Severity.HIGH if hard else Severity.LOW,
            description="Groups %s/%s require %s %.2f; nearest footprint gap %.2f" % (
                row["group_id_a"], row["group_id_b"], row["requirement"],
                row["required_distance"], row["actual_distance"]),
            suggested_action="Adjust group placements or the explicit rule.",
            metadata={"classification": row["classification"], **row}))
    return violations
