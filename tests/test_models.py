"""Tests for Phase 1 engineering data models."""

import json
import unittest

from wtp_autolayout.models import (
    Boundary,
    Coordinate,
    EngineeringUnit,
    FlowEdge,
    FlowGraph,
    FlowType,
    HazardLevel,
    Layout,
    LayoutMode,
    OptimizationResult,
    OptimizationStatus,
    Placement,
    ShapeType,
    UnitCategory,
)
from wtp_autolayout.utils.serialization import from_json, to_json


def sample_boundary() -> Boundary:
    return Boundary(
        boundary_id="B-001",
        vertices=[
            Coordinate(0.0, 0.0),
            Coordinate(100.0, 0.0),
            Coordinate(100.0, 100.0),
            Coordinate(0.0, 100.0),
        ],
    )


class TestModels(unittest.TestCase):
    def test_coordinate_creation(self) -> None:
        coordinate = Coordinate(easting=305435.0, northing=2353890.0, elevation=141.0)

        self.assertEqual(coordinate.easting, 305435.0)
        self.assertEqual(coordinate.northing, 2353890.0)
        self.assertEqual(coordinate.elevation, 141.0)

    def test_boundary_creation(self) -> None:
        boundary = sample_boundary()

        self.assertEqual(boundary.boundary_id, "B-001")
        self.assertEqual(len(boundary.vertices), 4)

    def test_rectangle_unit_creation(self) -> None:
        unit = EngineeringUnit(
            unit_id="U-FILTER-001",
            name="Rapid Gravity Sand Filter",
            category=UnitCategory.PROCESS,
            shape_type=ShapeType.RECTANGLE,
            width=25.0,
            length=60.0,
            required_clearance=5.0,
            hazard_level=HazardLevel.LOW,
        )

        self.assertEqual(unit.shape_type, ShapeType.RECTANGLE)
        self.assertEqual(unit.width, 25.0)

    def test_circle_unit_creation(self) -> None:
        unit = EngineeringUnit(
            unit_id="U-CLARIFIER-001",
            name="Clariflocculator",
            category=UnitCategory.PROCESS,
            shape_type=ShapeType.CIRCLE,
            diameter=28.0,
        )

        self.assertEqual(unit.shape_type, ShapeType.CIRCLE)
        self.assertEqual(unit.diameter, 28.0)

    def test_invalid_dimensions_fail(self) -> None:
        with self.assertRaises(ValueError):
            EngineeringUnit(
                unit_id="U-BAD-001",
                name="Invalid Unit",
                category=UnitCategory.PROCESS,
                shape_type=ShapeType.RECTANGLE,
                width=-1.0,
                length=10.0,
            )

        with self.assertRaises(ValueError):
            EngineeringUnit(
                unit_id="U-BAD-002",
                name="Invalid Circle",
                category=UnitCategory.PROCESS,
                shape_type=ShapeType.CIRCLE,
                width=10.0,
                length=10.0,
            )

    def test_flow_edge_rejects_same_source_and_target(self) -> None:
        with self.assertRaises(ValueError):
            FlowEdge(
                flow_id="F-001",
                source_unit_id="U-001",
                target_unit_id="U-001",
                flow_type=FlowType.PROCESS_WATER,
            )

    def test_layout_serializes_to_json(self) -> None:
        unit = EngineeringUnit(
            unit_id="U-CLARIFIER-001",
            name="Clariflocculator",
            category=UnitCategory.PROCESS,
            shape_type=ShapeType.CIRCLE,
            diameter=28.0,
            system_group="clarification",
        )
        layout = Layout(
            layout_id="L-001",
            boundary=sample_boundary(),
            units=[unit],
            placements=[
                Placement(
                    placement_id="P-001",
                    unit_id="U-CLARIFIER-001",
                    centroid=Coordinate(50.0, 50.0),
                    occupied_area=615.75,
                )
            ],
            flow_graph=FlowGraph(
                graph_id="G-001",
                unit_ids=["U-INLET-001", "U-CLARIFIER-001"],
                edges=[
                    FlowEdge(
                        flow_id="F-001",
                        source_unit_id="U-INLET-001",
                        target_unit_id="U-CLARIFIER-001",
                        flow_type=FlowType.PROCESS_WATER,
                        weight=2.0,
                    )
                ],
            ),
            optimization_score=12.5,
            layout_mode=LayoutMode.BALANCED,
        )

        json_text = to_json(layout, sort_keys=True)
        decoded = json.loads(json_text)

        self.assertEqual(decoded["layout_id"], "L-001")
        self.assertEqual(decoded["units"][0]["unit_id"], "U-CLARIFIER-001")
        self.assertEqual(decoded["units"][0]["shape_type"], "circle")
        self.assertEqual(decoded["flow_graph"]["edges"][0]["flow_type"], "process_water")
        self.assertEqual(decoded["layout_mode"], "balanced")

        restored = from_json(json_text, Layout.from_dict)
        self.assertEqual(restored.layout_id, layout.layout_id)
        self.assertEqual(restored.units[0].unit_id, "U-CLARIFIER-001")
        self.assertEqual(restored.units[0].shape_type, ShapeType.CIRCLE)
        self.assertEqual(restored.flow_graph.edges[0].flow_type, FlowType.PROCESS_WATER)

    def test_coordinate_rejects_invalid_easting_and_northing(self) -> None:
        with self.assertRaises(ValueError):
            Coordinate(easting="305435", northing=2353890.0)

        with self.assertRaises(ValueError):
            Coordinate(easting=305435.0, northing=None)

        with self.assertRaises(ValueError):
            Coordinate(easting=305435.0, northing=2353890.0, coordinate_system="")

    def test_boundary_rejects_non_coordinate_vertices(self) -> None:
        with self.assertRaises(ValueError):
            Boundary(
                boundary_id="B-BAD-001",
                vertices=[
                    Coordinate(0.0, 0.0),
                    Coordinate(100.0, 0.0),
                    {"easting": 100.0, "northing": 100.0},
                ],
            )

    def test_flow_graph_rejects_missing_unit_reference_when_unit_ids_provided(self) -> None:
        with self.assertRaises(ValueError):
            FlowGraph(
                graph_id="G-BAD-001",
                unit_ids=["U-001", "U-002"],
                edges=[
                    FlowEdge(
                        flow_id="F-BAD-001",
                        source_unit_id="U-001",
                        target_unit_id="U-MISSING",
                        flow_type=FlowType.PROCESS_WATER,
                    )
                ],
            )

    def test_placement_rejects_invalid_centroid_type(self) -> None:
        with self.assertRaises(ValueError):
            Placement(
                placement_id="P-BAD-001",
                unit_id="U-001",
                centroid={"easting": 50.0, "northing": 50.0},
            )

    def test_optimization_result_can_contain_layout(self) -> None:
        layout = Layout(layout_id="L-001", boundary=sample_boundary(), optimization_score=10.0)
        result = OptimizationResult(
            result_id="R-001",
            algorithm="phase1-placeholder",
            runtime=0.0,
            iterations=0,
            status=OptimizationStatus.SUCCESSFUL,
            best_layout=layout,
            candidate_layouts=[layout],
            candidate_count=1,
            final_score=10.0,
        )

        self.assertIs(result.best_layout, layout)
        self.assertEqual(result.to_dict()["best_layout"]["layout_id"], "L-001")


if __name__ == "__main__":
    unittest.main()
