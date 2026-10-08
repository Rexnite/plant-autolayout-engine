"""Human-readable schema constants for Phase 2 parser inputs."""

REQUIRED_JSON_SECTIONS = ("boundary", "units", "flow_edges")

REQUIRED_EXCEL_SHEETS = ("Boundary", "Units", "Flow")
OPTIONAL_EXCEL_SHEETS = ("Project", "Groups", "Proximity", "Constraints", "Roads", "Drains", "OptimizationSettings", "Metadata")

BOUNDARY_COLUMNS = ("easting", "northing")
UNIT_COLUMNS = ("unit_id", "name", "category", "shape_type")
FLOW_COLUMNS = ("edge_id", "source_unit_id", "target_unit_id", "flow_type")
CONSTRAINT_COLUMNS = ("constraint_id", "name", "constraint_type", "classification", "severity")

JSON_SCHEMA_EXAMPLE = {
    "boundary": [
        {
            "boundary_id": "B-001",
            "coordinate_system": "local",
            "easting": 0.0,
            "northing": 0.0,
            "vertex_order": 1,
        }
    ],
    "units": [
        {
            "unit_id": "clarifier",
            "name": "Clarifier",
            "category": "process",
            "shape_type": "circle",
            "diameter": 28.0,
            "required_clearance": 5.0,
            "hazard_level": "low",
        }
    ],
    "flow_edges": [
        {
            "edge_id": "F-001",
            "source_unit_id": "raw_water_inlet",
            "target_unit_id": "clarifier",
            "flow_type": "process_water",
            "gravity_required": True,
            "weight": 1.0,
        }
    ],
}
