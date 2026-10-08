"""Tests for Phase 4 constraint engine."""

import unittest

from wtp_autolayout.constraints import (
    BoundaryContainmentConstraint,
    ChemicalSafetyConstraint,
    ConstraintEngine,
    GeometryValidityConstraint,
    GravityFlowConstraint,
    MinimumClearanceConstraint,
    OverlapConstraint,
    ProcessAdjacencyConstraint,
    ResidentialSeparationConstraint,
    SludgeIsolationConstraint,
    default_wtp_engine,
)
from wtp_autolayout.geometry.engine import LayoutGeometryValidationResult
from wtp_autolayout.models import (
    Boundary,
    Coordinate,
    EngineeringUnit,
    FlowEdge,
    FlowGraph,
    FlowType,
    Layout,
    Placement,
    ShapeType,
    UnitCategory,
)


def boundary() -> Boundary:
    return Boundary(
        boundary_id="B-001",
        vertices=[
            Coordinate(0.0, 0.0),
            Coordinate(300.0, 0.0),
            Coordinate(300.0, 300.0),
            Coordinate(0.0, 300.0),
        ],
    )


def unit(
    unit_id: str,
    category: UnitCategory = UnitCategory.PROCESS,
    name: str = "Unit",
    system_group: str = None,
    clearance: float = 0.0,
) -> EngineeringUnit:
    return EngineeringUnit(
        unit_id=unit_id,
        name=name,
        category=category,
        shape_type=ShapeType.RECTANGLE,
        width=10.0,
        length=10.0,
        required_clearance=clearance,
        system_group=system_group,
    )


def placement(unit_id: str, x: float, y: float, elevation=None) -> Placement:
    return Placement(
        placement_id="P-%s" % unit_id,
        unit_id=unit_id,
        centroid=Coordinate(x, y, elevation=elevation),
    )


class TestConstraintEngine(unittest.TestCase):
    def test_default_wtp_engine_registers_expected_constraints(self) -> None:
        engine = default_wtp_engine()
        ids = [constraint.constraint_id for constraint in engine.constraints]

        self.assertEqual(
            ids,
            ["C-004", "C-001", "C-002", "C-003", "C-009", "C-010", "C-011", "C-005", "C-006"],
        )

    def test_boundary_violation_becomes_violation(self) -> None:
        u = unit("U-A")
        layout = Layout(
            layout_id="L-BOUNDARY",
            boundary=boundary(),
            units=[u],
            placements=[placement("U-A", 400.0, 20.0)],
        )

        violations = BoundaryContainmentConstraint().evaluate(layout)

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].constraint_id, "C-001")
        self.assertEqual(violations[0].affected_units, ["U-A"])

    def test_overlap_violation_becomes_violation(self) -> None:
        unit_a = unit("U-A")
        unit_b = unit("U-B")
        layout = Layout(
            layout_id="L-OVERLAP",
            boundary=boundary(),
            units=[unit_a, unit_b],
            placements=[placement("U-A", 50.0, 50.0), placement("U-B", 55.0, 50.0)],
        )

        violations = OverlapConstraint().evaluate(layout)

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].constraint_id, "C-002")
        self.assertEqual(violations[0].affected_units, ["U-A", "U-B"])

    def test_clearance_violation_becomes_violation(self) -> None:
        unit_a = unit("U-A", clearance=10.0)
        unit_b = unit("U-B", clearance=10.0)
        layout = Layout(
            layout_id="L-CLEARANCE",
            boundary=boundary(),
            units=[unit_a, unit_b],
            placements=[placement("U-A", 50.0, 50.0), placement("U-B", 75.0, 50.0)],
        )

        violations = MinimumClearanceConstraint().evaluate(layout)

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].constraint_id, "C-003")

    def test_sludge_isolation_violation(self) -> None:
        sludge = unit("sludge_sump", UnitCategory.SLUDGE, "Sludge Sump")
        admin = unit("admin_building", UnitCategory.HUMAN_OCCUPANCY, "Administration Building")
        layout = Layout(
            layout_id="L-SLUDGE",
            boundary=boundary(),
            units=[sludge, admin],
            placements=[placement("sludge_sump", 50.0, 50.0), placement("admin_building", 60.0, 50.0)],
        )

        violations = SludgeIsolationConstraint(minimum_distance=30.0).evaluate(layout)

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].constraint_id, "C-009")
        self.assertGreater(violations[0].penalty, 0.0)

    def test_chemical_safety_violation(self) -> None:
        chemical = unit("chemical_house", UnitCategory.CHEMICAL, "Chemical House")
        admin = unit("admin_building", UnitCategory.HUMAN_OCCUPANCY, "Administration Building")
        layout = Layout(
            layout_id="L-CHEMICAL",
            boundary=boundary(),
            units=[chemical, admin],
            placements=[placement("chemical_house", 50.0, 50.0), placement("admin_building", 60.0, 50.0)],
        )

        violations = ChemicalSafetyConstraint(minimum_distance=25.0).evaluate(layout)

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].constraint_id, "C-010")

    def test_residential_separation_violation(self) -> None:
        admin = unit("admin_building", UnitCategory.HUMAN_OCCUPANCY, "Administration Building")
        chemical = unit("chemical_house", UnitCategory.CHEMICAL, "Chemical House")
        layout = Layout(
            layout_id="L-RESIDENTIAL",
            boundary=boundary(),
            units=[admin, chemical],
            placements=[placement("admin_building", 50.0, 50.0), placement("chemical_house", 60.0, 50.0)],
        )

        violations = ResidentialSeparationConstraint(minimum_distance=30.0).evaluate(layout)

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].constraint_id, "C-011")

    def test_process_adjacency_violation(self) -> None:
        unit_a = unit("U-A")
        unit_b = unit("U-B")
        layout = Layout(
            layout_id="L-PROCESS",
            boundary=boundary(),
            units=[unit_a, unit_b],
            placements=[placement("U-A", 20.0, 20.0), placement("U-B", 180.0, 20.0)],
            flow_graph=FlowGraph(
                graph_id="G-001",
                unit_ids=["U-A", "U-B"],
                edges=[FlowEdge("F-001", "U-A", "U-B", FlowType.PROCESS_WATER)],
            ),
        )

        violations = ProcessAdjacencyConstraint(max_preferred_distance=100.0).evaluate(layout)

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].constraint_id, "C-005")
        self.assertAlmostEqual(violations[0].penalty, 60.0)

    def test_gravity_flow_violation_when_source_is_lower_than_target(self) -> None:
        unit_a = unit("U-A")
        unit_b = unit("U-B")
        layout = Layout(
            layout_id="L-GRAVITY",
            boundary=boundary(),
            units=[unit_a, unit_b],
            placements=[placement("U-A", 20.0, 20.0, elevation=100.0), placement("U-B", 50.0, 20.0, elevation=105.0)],
            flow_graph=FlowGraph(
                graph_id="G-001",
                unit_ids=["U-A", "U-B"],
                edges=[FlowEdge("F-001", "U-A", "U-B", FlowType.PROCESS_WATER, gravity_preferred=True)],
            ),
        )

        violations = GravityFlowConstraint().evaluate(layout)

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].constraint_id, "C-006")
        self.assertAlmostEqual(violations[0].penalty, 5.0)

    def test_gravity_flow_ignored_when_elevation_missing(self) -> None:
        unit_a = unit("U-A")
        unit_b = unit("U-B")
        layout = Layout(
            layout_id="L-GRAVITY-MISSING",
            boundary=boundary(),
            units=[unit_a, unit_b],
            placements=[placement("U-A", 20.0, 20.0), placement("U-B", 50.0, 20.0, elevation=105.0)],
            flow_graph=FlowGraph(
                graph_id="G-001",
                unit_ids=["U-A", "U-B"],
                edges=[FlowEdge("F-001", "U-A", "U-B", FlowType.PROCESS_WATER, gravity_preferred=True)],
            ),
        )

        violations = GravityFlowConstraint().evaluate(layout)

        self.assertEqual(violations, [])

    def test_disabled_constraint_does_not_evaluate(self) -> None:
        constraint = BoundaryContainmentConstraint(enabled=False)
        engine = ConstraintEngine([constraint])
        u = unit("U-A")
        layout = Layout(
            layout_id="L-DISABLED",
            boundary=boundary(),
            units=[u],
            placements=[placement("U-A", 400.0, 20.0)],
        )

        self.assertEqual(engine.evaluate(layout), [])

    def test_evaluate_all_includes_disabled_constraint_results(self) -> None:
        constraint = BoundaryContainmentConstraint(enabled=False)
        engine = ConstraintEngine([constraint])
        u = unit("U-A")
        layout = Layout(
            layout_id="L-ALL",
            boundary=boundary(),
            units=[u],
            placements=[placement("U-A", 400.0, 20.0)],
        )

        violations = engine.evaluate_all(layout)

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].constraint_id, "C-001")

    def test_evaluate_enabled_only_evaluates_enabled_constraints(self) -> None:
        disabled = BoundaryContainmentConstraint(enabled=False)
        enabled = OverlapConstraint(enabled=True)
        engine = ConstraintEngine([disabled, enabled])
        unit_a = unit("U-A")
        unit_b = unit("U-B")
        layout = Layout(
            layout_id="L-ENABLED",
            boundary=boundary(),
            units=[unit_a, unit_b],
            placements=[placement("U-A", 400.0, 20.0), placement("U-B", 400.0, 20.0)],
        )

        violations = engine.evaluate_enabled(layout)

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].constraint_id, "C-002")

    def test_evaluate_and_evaluate_enabled_skip_disabled_constraints(self) -> None:
        disabled = BoundaryContainmentConstraint(enabled=False)
        engine = ConstraintEngine([disabled])
        u = unit("U-A")
        layout = Layout(
            layout_id="L-SKIP",
            boundary=boundary(),
            units=[u],
            placements=[placement("U-A", 400.0, 20.0)],
        )

        self.assertEqual(engine.evaluate(layout), [])
        self.assertEqual(engine.evaluate_enabled(layout), [])

    def test_geometry_validation_is_cached_during_engine_evaluation(self) -> None:
        class CountingGeometryEngine:
            def __init__(self) -> None:
                self.calls = 0

            def validate_layout_geometry(self, layout):
                self.calls += 1
                return LayoutGeometryValidationResult(
                    inside_boundary_violations=["U-A"],
                    overlap_violations=[("U-A", "U-B")],
                    clearance_violations=[("U-A", "U-B")],
                    invalid_geometry_errors=["synthetic invalid geometry"],
                )

        geometry_engine = CountingGeometryEngine()
        engine = ConstraintEngine(
            [
                GeometryValidityConstraint(geometry_engine=geometry_engine),
                BoundaryContainmentConstraint(geometry_engine=geometry_engine),
                OverlapConstraint(geometry_engine=geometry_engine),
                MinimumClearanceConstraint(geometry_engine=geometry_engine),
            ]
        )
        unit_a = unit("U-A")
        unit_b = unit("U-B")
        layout = Layout(
            layout_id="L-CACHED",
            boundary=boundary(),
            units=[unit_a, unit_b],
            placements=[placement("U-A", 20.0, 20.0), placement("U-B", 30.0, 20.0)],
        )

        violations = engine.evaluate(layout)

        self.assertEqual(geometry_engine.calls, 1)
        self.assertEqual(len(violations), 4)


if __name__ == "__main__":
    unittest.main()
