"""JSON input parser for WTP project data."""

import json
import copy
from pathlib import Path
from typing import Any, Dict, List, Mapping

from wtp_autolayout.models import (
    Boundary,
    Constraint,
    Coordinate,
    Drain,
    EngineeringUnit,
    FlowEdge,
    FlowGraph,
    Layout,
    LayoutMode,
    Placement,
    Road,
    Severity,
    SiteZone,
    ExistingStructure,
    Corridor,
    GroupRelationship,
)

from .errors import ParserError
from .sample_schema import REQUIRED_JSON_SECTIONS
from .validation import (
    handle_model_error,
    parse_bool,
    parse_enum,
    parse_int,
    parse_metadata,
    parse_number,
    parse_string,
    require_sections,
    require_value,
    rows_from_section,
)
from wtp_autolayout.models import (
    ConstraintClassification,
    ConstraintType,
    FlowType,
    HazardLevel,
    ShapeType,
    UnitCategory,
    PlantType,
    SystemGroup,
    SpatialRelationship,
)
from .boundary_ordering import order_boundary


def _parse_site_entities(data, section, model_type, geometry_key=None):
    entities = []
    for index, row in enumerate(rows_from_section(data.get(section, []), section), start=1):
        context = "%s row %s" % (section, index)
        values = dict(row)
        if geometry_key and isinstance(values.get(geometry_key), str):
            try:
                values[geometry_key] = json.loads(values[geometry_key])
            except json.JSONDecodeError as error:
                raise ParserError("%s invalid %s JSON: %s" % (context, geometry_key, error))
        try:
            entity = model_type.from_dict(values)
            if geometry_key:
                from wtp_autolayout.geometry.site import corridor_geometry, structure_geometry, zone_geometry
                if model_type is SiteZone:
                    zone_geometry(entity)
                elif model_type is ExistingStructure:
                    structure_geometry(entity)
                else:
                    corridor_geometry(entity)
            entities.append(entity)
        except (TypeError, ValueError, KeyError) as error:
            raise ParserError("%s invalid: %s" % (context, error))
    return entities


def parse_json_file(path: str) -> Layout:
    """Read a JSON file and return a populated Layout."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise ParserError("Unable to read JSON input file: %s" % error)
    return parse_json_text(text)


def parse_json_text(json_text: str) -> Layout:
    """Parse JSON text and return a populated Layout."""
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as error:
        raise ParserError("Invalid JSON input: %s" % error)
    if not isinstance(data, dict):
        raise ParserError("JSON input must be an object")
    return parse_project_data(data)


def parse_project_data(data: Mapping[str, Any]) -> Layout:
    """Convert decoded project input into the Phase 1 data model."""
    data = _expand_engineering_rules(data)
    require_sections(data, REQUIRED_JSON_SECTIONS)
    boundary = _parse_boundary(data["boundary"])
    units = _parse_units(rows_from_section(data["units"], "units"))
    unit_ids = [unit.unit_id for unit in units]
    placements = _parse_placements(rows_from_section(data.get("placements", []), "placements"), set(unit_ids))
    flow_edges = _parse_flow_edges(rows_from_section(data["flow_edges"], "flow_edges"), set(unit_ids))
    constraints = _parse_constraints(rows_from_section(data.get("constraints", []), "constraints"))
    roads = _parse_roads(rows_from_section(data.get("roads", []), "roads"))
    drains = _parse_drains(rows_from_section(data.get("drains", []), "drains"))
    site_zones = _parse_site_entities(data, "site_zones", SiteZone, "vertices")
    existing_structures = _parse_site_entities(data, "existing_structures", ExistingStructure, "vertices")
    corridors = _parse_site_entities(data, "corridors", Corridor, "path")
    group_relationships = _parse_site_entities(data, "group_relationships", GroupRelationship)
    try:
        plant_type = parse_enum(PlantType, data.get("plant_type", "wtp"), "project", "plant_type")
        groups = [SystemGroup.from_dict(row) for row in rows_from_section(data.get("system_groups", []), "system_groups")]
        relationships = [SpatialRelationship.from_dict(row) for row in rows_from_section(
            data.get("proximity_relationships", []), "proximity_relationships")]
    except (ValueError, KeyError, TypeError) as error:
        raise ParserError("Invalid project groups or relationships: %s" % error)

    metadata = parse_metadata(data.get("metadata", {}), "metadata")
    if data.get("engineering_rules"):
        metadata["engineering_rules"] = copy.deepcopy(data["engineering_rules"])
    optimization_settings = data.get("optimization_settings")
    layout_mode = None
    if optimization_settings:
        if isinstance(optimization_settings, Mapping):
            optimization_settings = dict(optimization_settings)
            weights = optimization_settings.get("objective_weights")
            if isinstance(weights, str):
                try:
                    weights = json.loads(weights)
                except json.JSONDecodeError as error:
                    raise ParserError("optimization_settings objective_weights must be JSON object: %s" % error)
                optimization_settings["objective_weights"] = weights
            if weights is not None and not isinstance(weights, dict):
                raise ParserError("optimization_settings objective_weights must be an object")
        metadata["optimization_settings"] = optimization_settings
        if isinstance(optimization_settings, Mapping) and optimization_settings.get("layout_mode"):
            layout_mode = parse_enum(
                LayoutMode,
                optimization_settings.get("layout_mode"),
                "optimization_settings",
                "layout_mode",
            )

    try:
        return Layout(
            layout_id=str(data.get("layout_id") or metadata.get("project_id") or "parsed_layout"),
            boundary=boundary,
            units=units,
            placements=placements,
            flow_graph=FlowGraph(graph_id=str(data.get("flow_graph_id") or "parsed_flow_graph"), unit_ids=unit_ids, edges=flow_edges),
            roads=roads,
            drains=drains,
            constraints=constraints,
            layout_mode=layout_mode,
            metadata=metadata,
            plant_type=plant_type,
            system_groups=groups,
            proximity_relationships=relationships,
            site_zones=site_zones,
            existing_structures=existing_structures,
            corridors=corridors,
            group_relationships=group_relationships,
        )
    except ValueError as error:
        raise handle_model_error("layout", error)


def _expand_engineering_rules(data):
    rules = data.get("engineering_rules", [])
    if not rules:
        return data
    result = copy.deepcopy(dict(data))
    ids = set()
    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, Mapping):
            raise ParserError("engineering_rules row %s must be an object" % index)
        rule_id = rule.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id.strip() or rule_id in ids:
            raise ParserError("engineering_rules row %s requires a unique rule_id" % index)
        ids.add(rule_id)
        scope = rule.get("scope")
        subject_a = rule.get("subject_a")
        subject_b = rule.get("subject_b")
        kind = rule.get("rule_type")
        classification = rule.get("classification") or "soft"
        distance = rule.get("distance")
        weight = rule.get("weight") if rule.get("weight") is not None else 1.0
        if scope == "unit_pair":
            result.setdefault("proximity_relationships", []).append({
                "relationship_id": rule_id, "unit_id_a": subject_a, "unit_id_b": subject_b,
                "relationship_type": kind, "distance": distance,
                "classification": classification, "weight": weight})
        elif scope == "group_pair":
            result.setdefault("group_relationships", []).append({
                "relationship_id": rule_id, "group_id_a": subject_a, "group_id_b": subject_b,
                "relationship_type": kind, "distance": distance or 0.0,
                "classification": classification, "weight": weight})
        elif scope == "unit_access" and kind == "max_distance":
            unit = next((item for item in result.get("units", []) if item.get("unit_id") == subject_a), None)
            if unit is None:
                raise ParserError("engineering rule %s references unknown unit %s" % (rule_id, subject_a))
            unit.update({"access_required": True, "max_access_distance": distance,
                         "access_classification": classification})
        elif scope == "zone_occupancy" and kind == "avoid":
            zone = next((item for item in result.get("site_zones", []) if item.get("zone_id") == subject_a), None)
            if zone is None:
                raise ParserError("engineering rule %s references unknown zone %s" % (rule_id, subject_a))
            zone.update({"classification": classification, "weight": weight,
                         "provenance": "user_entered"})
        else:
            raise ParserError("engineering rule %s has unsupported scope or rule_type" % rule_id)
    return result


def _parse_boundary(section: Any) -> Boundary:
    rows = rows_from_section(section, "boundary")
    orders = [parse_int(row, "vertex_order", "boundary") for row in rows]
    has_order = any(value is not None for value in orders)
    if has_order:
        if any(value is None for value in orders) or len(set(orders)) != len(orders):
            raise ParserError("Boundary vertex_order must be present and unique for every row")
        ordered_rows = [row for _, row in sorted(zip(orders, rows), key=lambda item: item[0])]
    else:
        ordered_rows = rows
    vertices: List[Coordinate] = []
    boundary_id = None
    coordinate_system = None
    for index, row in enumerate(ordered_rows, start=1):
        context = "boundary row %s" % index
        boundary_id = boundary_id or parse_string(row, "boundary_id", context) or "B-001"
        coordinate_system = coordinate_system or parse_string(row, "coordinate_system", context)
        try:
            vertices.append(
                Coordinate(
                    easting=parse_number(row, "easting", context, required=True),
                    northing=parse_number(row, "northing", context, required=True),
                    elevation=parse_number(row, "elevation", context),
                    coordinate_system=coordinate_system,
                )
            )
        except ValueError as error:
            raise handle_model_error(context, error)
    try:
        return Boundary(boundary_id=boundary_id, vertices=order_boundary(vertices, ordered=has_order))
    except ValueError as error:
        raise handle_model_error("boundary", error)


def _parse_units(rows: List[Mapping[str, Any]]) -> List[EngineeringUnit]:
    units = []
    seen = set()
    for index, row in enumerate(rows, start=1):
        context = "units row %s" % index
        unit_id = parse_string(row, "unit_id", context, required=True)
        if unit_id in seen:
            raise ParserError("%s duplicate unit_id: %s" % (context, unit_id))
        seen.add(unit_id)
        try:
            units.append(
                EngineeringUnit(
                    unit_id=unit_id,
                    name=parse_string(row, "name", context, required=True),
                    category=parse_enum(UnitCategory, require_value(row, "category", context), context, "category"),
                    shape_type=parse_enum(ShapeType, require_value(row, "shape_type", context), context, "shape_type"),
                    width=parse_number(row, "width", context),
                    length=parse_number(row, "length", context),
                    diameter=parse_number(row, "diameter", context),
                    required_clearance=parse_number(row, "required_clearance", context) or 0.0,
                    hazard_level=parse_enum(HazardLevel, row.get("hazard_level", "low"), context, "hazard_level"),
                    system_group=parse_string(row, "system_group", context),
                    process_order=parse_int(row, "process_order", context),
                    metadata=parse_metadata(row.get("metadata"), context),
                    access_required=parse_bool(row, "access_required", context, default=False),
                    max_access_distance=parse_number(row, "max_access_distance", context),
                    access_classification=parse_enum(ConstraintClassification,
                        row.get("access_classification") or "soft", context, "access_classification"),
                    maintenance_clearance=parse_number(row, "maintenance_clearance", context) or 0.0,
                )
            )
        except ValueError as error:
            raise handle_model_error(context, error)
    return units


def _parse_placements(rows: List[Mapping[str, Any]], unit_ids: set) -> List[Placement]:
    placements = []
    for index, row in enumerate(rows, start=1):
        context = "placements row %s" % index
        unit_id = parse_string(row, "unit_id", context, required=True)
        if unit_id not in unit_ids:
            raise ParserError("%s references unknown unit_id: %s" % (context, unit_id))
        try:
            placements.append(
                Placement(
                    placement_id=parse_string(row, "placement_id", context, required=True),
                    unit_id=unit_id,
                    centroid=Coordinate(
                        easting=parse_number(row, "easting", context, required=True),
                        northing=parse_number(row, "northing", context, required=True),
                        elevation=parse_number(row, "elevation", context),
                    ),
                    rotation=parse_number(row, "rotation", context) or 0.0,
                    metadata=parse_metadata(row.get("metadata"), context),
                )
            )
        except ValueError as error:
            raise handle_model_error(context, error)
    return placements


def _parse_flow_edges(rows: List[Mapping[str, Any]], unit_ids: set) -> List[FlowEdge]:
    edges = []
    for index, row in enumerate(rows, start=1):
        context = "flow_edges row %s" % index
        source = parse_string(row, "source_unit_id", context, required=True)
        target = parse_string(row, "target_unit_id", context, required=True)
        if source not in unit_ids:
            raise ParserError("%s references unknown source_unit_id: %s" % (context, source))
        if target not in unit_ids:
            raise ParserError("%s references unknown target_unit_id: %s" % (context, target))
        try:
            edges.append(
                FlowEdge(
                    flow_id=parse_string(row, "edge_id", context, required=True),
                    source_unit_id=source,
                    target_unit_id=target,
                    flow_type=parse_enum(FlowType, require_value(row, "flow_type", context), context, "flow_type"),
                    gravity_preferred=parse_bool(row, "gravity_required", context, default=False),
                    weight=parse_number(row, "weight", context) or 1.0,
                    metadata=parse_metadata(row.get("metadata"), context),
                )
            )
        except ValueError as error:
            raise handle_model_error(context, error)
    return edges


def _parse_constraints(rows: List[Mapping[str, Any]]) -> List[Constraint]:
    constraints = []
    for index, row in enumerate(rows, start=1):
        context = "constraints row %s" % index
        try:
            constraints.append(
                Constraint(
                    constraint_id=parse_string(row, "constraint_id", context, required=True),
                    name=parse_string(row, "name", context, required=True),
                    constraint_type=parse_enum(ConstraintType, require_value(row, "constraint_type", context), context, "constraint_type"),
                    classification=parse_enum(ConstraintClassification, require_value(row, "classification", context), context, "classification"),
                    severity=parse_enum(Severity, require_value(row, "severity", context), context, "severity"),
                    weight=parse_number(row, "weight", context) or 1.0,
                    enabled=parse_bool(row, "enabled", context, default=True),
                    description=parse_string(row, "description", context) or "",
                )
            )
        except ValueError as error:
            raise handle_model_error(context, error)
    return constraints


def _parse_coordinate_path(value: Any, context: str) -> List[Coordinate]:
    if not value:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise ParserError("%s path must be JSON coordinate list: %s" % (context, error))
    if not isinstance(value, list):
        raise ParserError("%s path must be a list" % context)
    path = []
    for index, item in enumerate(value, start=1):
        item_context = "%s path point %s" % (context, index)
        if not isinstance(item, dict):
            raise ParserError("%s must be an object" % item_context)
        try:
            path.append(
                Coordinate(
                    easting=parse_number(item, "easting", item_context, required=True),
                    northing=parse_number(item, "northing", item_context, required=True),
                    elevation=parse_number(item, "elevation", item_context),
                )
            )
        except ValueError as error:
            raise handle_model_error(item_context, error)
    return path


def _parse_roads(rows: List[Mapping[str, Any]]) -> List[Road]:
    roads = []
    for index, row in enumerate(rows, start=1):
        context = "roads row %s" % index
        try:
            roads.append(
                Road(
                    road_id=parse_string(row, "road_id", context, required=True),
                    path=_parse_coordinate_path(row.get("path"), context),
                    width=parse_number(row, "width", context),
                    road_type=parse_string(row, "road_type", context),
                    metadata=parse_metadata(row.get("metadata"), context),
                )
            )
        except ValueError as error:
            raise handle_model_error(context, error)
    return roads


def _parse_drains(rows: List[Mapping[str, Any]]) -> List[Drain]:
    drains = []
    for index, row in enumerate(rows, start=1):
        context = "drains row %s" % index
        try:
            drains.append(
                Drain(
                    drain_id=parse_string(row, "drain_id", context, required=True),
                    path=_parse_coordinate_path(row.get("path"), context),
                    flow_direction=parse_string(row, "flow_direction", context),
                    design_capacity=parse_number(row, "design_capacity", context),
                    metadata=parse_metadata(row.get("metadata"), context),
                )
            )
        except ValueError as error:
            raise handle_model_error(context, error)
    return drains
