"""Tests for Phase 3 geometry engine."""

import json
import unittest
from pathlib import Path

from wtp_autolayout.geometry import GeometryEngine, GeometryError
from wtp_autolayout.models import (
    Boundary,
    Coordinate,
    EngineeringUnit,
    Layout,
    Placement,
    ShapeType,
    UnitCategory,
)
from wtp_autolayout.parsers import parse_json_text


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_JSON = ROOT / "sample_data" / "sample_wtp_input.json"


def boundary() -> Boundary:
    return Boundary(
        boundary_id="B-001",
        vertices=[
            Coordinate(0.0, 0.0),
            Coordinate(100.0, 0.0),
            Coordinate(100.0, 100.0),
            Coordinate(0.0, 100.0),
        ],
    )


def rectangle_unit(unit_id: str = "U-RECT", clearance: float = 0.0) -> EngineeringUnit:
    return EngineeringUnit(
        unit_id=unit_id,
        name="Rectangle Unit",
        category=UnitCategory.PROCESS,
        shape_type=ShapeType.RECTANGLE,
        width=10.0,
        length=20.0,
        required_clearance=clearance,
    )


def circle_unit(unit_id: str = "U-CIRCLE", clearance: float = 0.0) -> EngineeringUnit:
    return EngineeringUnit(
        unit_id=unit_id,
        name="Circle Unit",
        category=UnitCategory.PROCESS,
        shape_type=ShapeType.CIRCLE,
        diameter=10.0,
        required_clearance=clearance,
    )


class TestGeometryEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = GeometryEngine()

    def test_boundary_polygon_creation(self) -> None:
        polygon = self.engine.boundary_to_polygon(boundary())

        self.assertTrue(polygon.is_valid)
        self.assertAlmostEqual(polygon.area, 10000.0)

    def test_rectangle_geometry_creation(self) -> None:
        unit = rectangle_unit()
        placement = Placement("P-RECT", unit.unit_id, Coordinate(50.0, 50.0))

        geometry = self.engine.unit_to_geometry(unit, placement)

        self.assertTrue(geometry.is_valid)
        self.assertAlmostEqual(geometry.area, 200.0)
        self.assertEqual(geometry.bounds, (40.0, 45.0, 60.0, 55.0))

    def test_circle_geometry_creation(self) -> None:
        unit = circle_unit()
        placement = Placement("P-CIRCLE", unit.unit_id, Coordinate(50.0, 50.0))

        geometry = self.engine.unit_to_geometry(unit, placement)

        self.assertTrue(geometry.is_valid)
        self.assertAlmostEqual(geometry.area, 78.4137, places=3)

    def test_rotated_rectangle_geometry_creation(self) -> None:
        unit = rectangle_unit()
        placement = Placement("P-ROT", unit.unit_id, Coordinate(50.0, 50.0), rotation=45.0)

        geometry = self.engine.unit_to_geometry(unit, placement)

        self.assertTrue(geometry.is_valid)
        self.assertAlmostEqual(geometry.area, 200.0)
        self.assertNotEqual(tuple(round(value, 6) for value in geometry.bounds), (40.0, 45.0, 60.0, 55.0))

    def test_unit_inside_boundary_true(self) -> None:
        unit = rectangle_unit()
        placement = Placement("P-RECT", unit.unit_id, Coordinate(50.0, 50.0))

        self.assertTrue(
            self.engine.is_inside_boundary(
                self.engine.unit_to_geometry(unit, placement),
                self.engine.boundary_to_polygon(boundary()),
            )
        )

    def test_unit_outside_boundary_false(self) -> None:
        unit = rectangle_unit()
        placement = Placement("P-RECT", unit.unit_id, Coordinate(150.0, 50.0))

        self.assertFalse(
            self.engine.is_inside_boundary(
                self.engine.unit_to_geometry(unit, placement),
                self.engine.boundary_to_polygon(boundary()),
            )
        )

    def test_overlap_detection(self) -> None:
        unit_a = rectangle_unit("U-A")
        unit_b = rectangle_unit("U-B")
        geometry_a = self.engine.unit_to_geometry(unit_a, Placement("P-A", "U-A", Coordinate(50.0, 50.0)))
        geometry_b = self.engine.unit_to_geometry(unit_b, Placement("P-B", "U-B", Coordinate(55.0, 50.0)))

        self.assertTrue(self.engine.overlaps(geometry_a, geometry_b))

    def test_touching_unit_boundaries_are_not_overlap(self) -> None:
        unit_a = rectangle_unit("U-A")
        unit_b = rectangle_unit("U-B")
        geometry_a = self.engine.unit_to_geometry(unit_a, Placement("P-A", "U-A", Coordinate(20.0, 20.0)))
        geometry_b = self.engine.unit_to_geometry(unit_b, Placement("P-B", "U-B", Coordinate(40.0, 20.0)))

        self.assertFalse(self.engine.overlaps(geometry_a, geometry_b))

    def test_identical_geometries_are_overlap(self) -> None:
        unit_a = rectangle_unit("U-A")
        unit_b = rectangle_unit("U-B")
        geometry_a = self.engine.unit_to_geometry(unit_a, Placement("P-A", "U-A", Coordinate(20.0, 20.0)))
        geometry_b = self.engine.unit_to_geometry(unit_b, Placement("P-B", "U-B", Coordinate(20.0, 20.0)))

        self.assertTrue(self.engine.overlaps(geometry_a, geometry_b))

    def test_distance_between_units(self) -> None:
        unit_a = rectangle_unit("U-A")
        unit_b = rectangle_unit("U-B")
        geometry_a = self.engine.unit_to_geometry(unit_a, Placement("P-A", "U-A", Coordinate(20.0, 20.0)))
        geometry_b = self.engine.unit_to_geometry(unit_b, Placement("P-B", "U-B", Coordinate(60.0, 20.0)))

        self.assertAlmostEqual(self.engine.distance(geometry_a, geometry_b), 20.0)

    def test_clearance_violation_true_and_false(self) -> None:
        unit_a = rectangle_unit("U-A", clearance=5.0)
        unit_b = rectangle_unit("U-B", clearance=5.0)
        placement_a = Placement("P-A", "U-A", Coordinate(20.0, 20.0))
        near_placement_b = Placement("P-B", "U-B", Coordinate(45.0, 20.0))
        far_placement_b = Placement("P-B", "U-B", Coordinate(60.0, 20.0))

        self.assertTrue(self.engine.clearance_violation(unit_a, placement_a, unit_b, near_placement_b))
        self.assertFalse(self.engine.clearance_violation(unit_a, placement_a, unit_b, far_placement_b))

    def test_touching_clearance_boundaries_are_not_clearance_violation(self) -> None:
        unit_a = rectangle_unit("U-A", clearance=5.0)
        unit_b = rectangle_unit("U-B", clearance=5.0)
        placement_a = Placement("P-A", "U-A", Coordinate(20.0, 20.0))
        touching_clearance_b = Placement("P-B", "U-B", Coordinate(50.0, 20.0))

        self.assertFalse(self.engine.clearance_violation(unit_a, placement_a, unit_b, touching_clearance_b))

    def test_footprint_entering_another_units_clearance_is_violation(self) -> None:
        unit_a = rectangle_unit("U-A", clearance=5.0)
        unit_b = rectangle_unit("U-B", clearance=0.0)
        placement_a = Placement("P-A", "U-A", Coordinate(20.0, 20.0))
        placement_b = Placement("P-B", "U-B", Coordinate(43.0, 20.0))

        self.assertTrue(self.engine.clearance_violation(unit_a, placement_a, unit_b, placement_b))

    def test_duplicate_placement_for_same_unit_id_is_reported(self) -> None:
        unit = rectangle_unit("U-A")
        layout = Layout(
            layout_id="L-DUP",
            boundary=boundary(),
            units=[unit],
            placements=[
                Placement("P-A1", "U-A", Coordinate(20.0, 20.0)),
                Placement("P-A2", "U-A", Coordinate(50.0, 50.0)),
            ],
        )

        result = self.engine.validate_layout_geometry(layout)

        self.assertTrue(any("duplicate placement for unit_id U-A" in error for error in result.invalid_geometry_errors))

    def test_missing_placement_for_unit_is_reported(self) -> None:
        unit_a = rectangle_unit("U-A")
        unit_b = rectangle_unit("U-B")
        layout = Layout(
            layout_id="L-MISSING",
            boundary=boundary(),
            units=[unit_a, unit_b],
            placements=[Placement("P-A", "U-A", Coordinate(20.0, 20.0))],
        )

        result = self.engine.validate_layout_geometry(layout)

        self.assertIn("missing placement for unit_id U-B", result.invalid_geometry_errors)

    def test_validate_layout_geometry_detects_overlap(self) -> None:
        unit_a = rectangle_unit("U-A")
        unit_b = rectangle_unit("U-B")
        layout = Layout(
            layout_id="L-OVERLAP",
            boundary=boundary(),
            units=[unit_a, unit_b],
            placements=[
                Placement("P-A", "U-A", Coordinate(50.0, 50.0)),
                Placement("P-B", "U-B", Coordinate(55.0, 50.0)),
            ],
        )

        result = self.engine.validate_layout_geometry(layout)

        self.assertEqual(result.overlap_violations, [("U-A", "U-B")])

    def test_validate_layout_geometry_detects_outside_boundary(self) -> None:
        unit = rectangle_unit("U-A")
        layout = Layout(
            layout_id="L-OUTSIDE",
            boundary=boundary(),
            units=[unit],
            placements=[Placement("P-A", "U-A", Coordinate(150.0, 50.0))],
        )

        result = self.engine.validate_layout_geometry(layout)

        self.assertEqual(result.inside_boundary_violations, ["U-A"])

    def test_validate_layout_geometry_works_with_sample_json_and_test_placements(self) -> None:
        data = json.loads(SAMPLE_JSON.read_text(encoding="utf-8"))
        data["placements"] = [
            {"placement_id": "P-001", "unit_id": "raw_water_inlet", "easting": 20.0, "northing": 20.0},
            {"placement_id": "P-002", "unit_id": "cascade_aerator", "easting": 45.0, "northing": 20.0},
            {"placement_id": "P-003", "unit_id": "flash_mixer", "easting": 70.0, "northing": 20.0},
            {"placement_id": "P-004", "unit_id": "clarifier", "easting": 100.0, "northing": 50.0},
            {"placement_id": "P-005", "unit_id": "rapid_sand_filter", "easting": 145.0, "northing": 55.0},
            {"placement_id": "P-006", "unit_id": "clear_water_reservoir", "easting": 150.0, "northing": 115.0},
            {"placement_id": "P-007", "unit_id": "chemical_house", "easting": 65.0, "northing": 55.0},
            {"placement_id": "P-008", "unit_id": "sludge_sump", "easting": 90.0, "northing": 105.0},
            {"placement_id": "P-009", "unit_id": "sludge_thickener", "easting": 120.0, "northing": 105.0},
            {"placement_id": "P-010", "unit_id": "admin_building", "easting": 35.0, "northing": 105.0},
        ]
        layout = parse_json_text(json.dumps(data))

        result = self.engine.validate_layout_geometry(layout)

        self.assertEqual(result.invalid_geometry_errors, [])
        self.assertIsInstance(result.to_dict(), dict)


if __name__ == "__main__":
    unittest.main()
