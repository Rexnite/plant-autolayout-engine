"""Tests for Phase 5 scoring engine."""

import unittest

from wtp_autolayout.constraints import BoundaryContainmentConstraint, ConstraintEngine
from wtp_autolayout.models import (
    Boundary,
    Constraint,
    ConstraintClassification,
    ConstraintType,
    Coordinate,
    EngineeringUnit,
    FlowEdge,
    FlowGraph,
    FlowType,
    Layout,
    Placement,
    Severity,
    ShapeType,
    UnitCategory,
    Violation,
)
from wtp_autolayout.scoring import ScoringEngine, ScoringError, ScoringResult


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


def unit(unit_id: str = "U-A") -> EngineeringUnit:
    return EngineeringUnit(
        unit_id=unit_id,
        name="Unit",
        category=UnitCategory.PROCESS,
        shape_type=ShapeType.RECTANGLE,
        width=10.0,
        length=10.0,
    )


def layout(layout_id: str = "L-001") -> Layout:
    u = unit("U-A")
    return Layout(
        layout_id=layout_id,
        boundary=boundary(),
        units=[u],
        placements=[Placement("P-U-A", "U-A", Coordinate(20.0, 20.0))],
    )


def two_unit_flow_layout(layout_id: str, second_x: float, downstream_lower: bool = True) -> Layout:
    source = unit("flash_mixer")
    target = unit("clarifier")
    source.name = "Flash Mixer"
    target.name = "Clarifier"
    source.process_order = 1
    target.process_order = 2
    return Layout(
        layout_id=layout_id,
        boundary=boundary(),
        units=[source, target],
        placements=[
            Placement("P-flash", "flash_mixer", Coordinate(20.0, 20.0, elevation=105.0)),
            Placement(
                "P-clarifier",
                "clarifier",
                Coordinate(second_x, 20.0, elevation=103.0 if downstream_lower else 108.0),
            ),
        ],
        flow_graph=FlowGraph(
            graph_id="FG-001",
            unit_ids=["flash_mixer", "clarifier"],
            edges=[
                FlowEdge(
                    flow_id="F-001",
                    source_unit_id="flash_mixer",
                    target_unit_id="clarifier",
                    flow_type=FlowType.PROCESS_WATER,
                    gravity_preferred=True,
                )
            ],
        ),
    )


def violation(constraint_id: str, penalty: float, severity: Severity = Severity.HIGH) -> Violation:
    return Violation(
        violation_id="%s-1" % constraint_id,
        constraint_id=constraint_id,
        affected_units=["U-A"],
        penalty=penalty,
        severity=severity,
        description="Test violation",
        suggested_action="Fix it",
    )


def constraint_model(
    constraint_id: str,
    classification: ConstraintClassification,
) -> Constraint:
    return Constraint(
        constraint_id=constraint_id,
        name="Constraint %s" % constraint_id,
        constraint_type=ConstraintType.OTHER,
        classification=classification,
        severity=Severity.HIGH,
    )


class TestScoringEngine(unittest.TestCase):
    def test_scoring_zero_violations_returns_score_100(self) -> None:
        result = ScoringEngine().score_violations([])

        self.assertEqual(result.total_penalty, 0.0)
        self.assertEqual(result.score, 100.0)
        self.assertTrue(result.passed_hard_constraints)

    def test_hard_and_soft_penalties_are_separated(self) -> None:
        violations = [violation("C-001", 10.0), violation("C-009", 5.0)]

        result = ScoringEngine().score_violations(violations)

        self.assertEqual(result.hard_penalty, 10.0)
        self.assertEqual(result.soft_penalty, 5.0)
        self.assertEqual(result.hard_violation_count, 1)
        self.assertEqual(result.soft_violation_count, 1)
        self.assertFalse(result.passed_hard_constraints)

    def test_weights_change_final_total_penalty(self) -> None:
        violations = [violation("C-009", 5.0)]

        result = ScoringEngine(weight_overrides={"C-009": 3.0}).score_violations(violations)

        self.assertEqual(result.total_penalty, 15.0)
        self.assertEqual(result.score, 85.0)

    def test_score_never_below_zero(self) -> None:
        result = ScoringEngine().score_violations([violation("C-009", 500.0)])

        self.assertEqual(result.score, 0.0)

    def test_score_layout_evaluates_constraints_when_constraint_engine_supplied(self) -> None:
        engine = ConstraintEngine([BoundaryContainmentConstraint()])
        scoring = ScoringEngine(constraint_engine=engine)
        scored_layout = layout("L-OUTSIDE")
        scored_layout.placements = [Placement("P-U-A", "U-A", Coordinate(200.0, 20.0))]

        result = scoring.score_layout(scored_layout)

        self.assertEqual(result.violation_count, 1)
        self.assertEqual(result.violations[0].constraint_id, "C-001")

    def test_score_layout_does_not_mutate_layout_by_default(self) -> None:
        scored_layout = layout()
        scored_layout.violations = [violation("C-009", 5.0)]

        result = ScoringEngine().score_layout(scored_layout)

        self.assertEqual(result.total_penalty, 5.0)
        self.assertIsNone(scored_layout.optimization_score)
        self.assertIsNone(scored_layout.statistics)
        self.assertFalse(hasattr(scored_layout, "score"))

    def test_score_layout_mutates_layout_only_when_update_layout_true(self) -> None:
        scored_layout = layout()
        scored_layout.violations = [violation("C-009", 5.0)]

        result = ScoringEngine().score_layout(scored_layout, update_layout=True)

        self.assertEqual(scored_layout.optimization_score, result.score)
        self.assertFalse(hasattr(scored_layout, "score"))
        self.assertEqual(scored_layout.statistics.total_penalty, 5.0)
        self.assertEqual(scored_layout.statistics.number_of_violations, 1)
        self.assertEqual(scored_layout.violations, result.violations)

    def test_rank_layouts_sorts_best_score_first(self) -> None:
        good = layout("L-GOOD")
        bad = layout("L-BAD")
        good.violations = [violation("C-009", 5.0)]
        bad.violations = [violation("C-009", 20.0)]

        ranked = ScoringEngine().rank_layouts([bad, good])

        self.assertEqual(ranked[0][0].layout_id, "L-GOOD")
        self.assertGreater(ranked[0][1].score, ranked[1][1].score)

    def test_rank_layouts_update_layout_updates_optimization_score(self) -> None:
        scored_layout = layout("L-UPDATE")
        scored_layout.violations = [violation("C-009", 15.0)]

        ranked = ScoringEngine().rank_layouts([scored_layout], update_layout=True)

        self.assertEqual(scored_layout.optimization_score, ranked[0][1].score)
        self.assertFalse(hasattr(scored_layout, "score"))

    def test_penalty_by_constraint_is_populated(self) -> None:
        violations = [violation("C-009", 5.0), violation("C-009", 3.0)]

        result = ScoringEngine().score_violations(violations)

        self.assertEqual(result.penalty_by_constraint["C-009"], 8.0)

    def test_penalty_by_severity_is_populated(self) -> None:
        violations = [violation("C-009", 5.0, Severity.HIGH), violation("C-010", 2.0, Severity.MEDIUM)]

        result = ScoringEngine().score_violations(violations)

        self.assertEqual(result.penalty_by_severity["high"], 5.0)
        self.assertEqual(result.penalty_by_severity["medium"], 2.0)

    def test_classification_can_be_inferred_from_registered_constraints(self) -> None:
        constraints = [constraint_model("CUSTOM-HARD", ConstraintClassification.HARD)]
        result = ScoringEngine().score_violations([violation("CUSTOM-HARD", 7.0)], constraints=constraints)

        self.assertEqual(result.hard_penalty, 7.0)
        self.assertEqual(result.soft_penalty, 0.0)

    def test_scoring_result_to_dict_from_dict_round_trip(self) -> None:
        result = ScoringEngine().score_violations([violation("C-009", 5.0, Severity.HIGH)])

        restored = ScoringResult.from_dict(result.to_dict())

        self.assertEqual(restored.total_penalty, result.total_penalty)
        self.assertEqual(restored.score, result.score)
        self.assertEqual(restored.penalty_by_constraint, result.penalty_by_constraint)
        self.assertEqual(restored.penalty_by_severity, result.penalty_by_severity)
        self.assertEqual(restored.violations[0].violation_id, result.violations[0].violation_id)

    def test_negative_weight_override_raises_scoring_error(self) -> None:
        with self.assertRaises(ScoringError):
            ScoringEngine(weight_overrides={"C-009": -1.0})

    def test_negative_reward_weight_override_raises_scoring_error(self) -> None:
        with self.assertRaises(ScoringError):
            ScoringEngine(reward_weight_overrides={"pipe_efficiency": -1.0})

    def test_two_zero_violation_layouts_can_have_different_engineering_scores(self) -> None:
        efficient = two_unit_flow_layout("L-EFFICIENT", second_x=32.0)
        inefficient = two_unit_flow_layout("L-INEFFICIENT", second_x=90.0)

        scoring = ScoringEngine()
        efficient_result = scoring.score_layout(efficient)
        inefficient_result = scoring.score_layout(inefficient)

        self.assertEqual(efficient_result.violation_count, 0)
        self.assertEqual(inefficient_result.violation_count, 0)
        self.assertGreater(efficient_result.reward_total, inefficient_result.reward_total)
        self.assertGreater(efficient_result.score, inefficient_result.score)

    def test_gravity_reward_prefers_downstream_lower_elevation(self) -> None:
        good = two_unit_flow_layout("L-GRAVITY-GOOD", second_x=32.0, downstream_lower=True)
        bad = two_unit_flow_layout("L-GRAVITY-BAD", second_x=32.0, downstream_lower=False)

        scoring = ScoringEngine()
        good_result = scoring.score_layout(good)
        bad_result = scoring.score_layout(bad)

        self.assertGreater(good_result.reward_by_objective["gravity"], bad_result.reward_by_objective["gravity"])

    def test_expansion_reward_prefers_preserved_future_area(self) -> None:
        preserved = layout("L-EXPANSION-PRESERVED")
        occupied = layout("L-EXPANSION-OCCUPIED")
        preserved.placements = [Placement("P-U-A", "U-A", Coordinate(20.0, 20.0))]
        occupied.placements = [Placement("P-U-A", "U-A", Coordinate(78.0, 35.0))]

        scoring = ScoringEngine()
        preserved_result = scoring.score_layout(preserved)
        occupied_result = scoring.score_layout(occupied)

        self.assertGreater(
            preserved_result.reward_by_objective["expansion"],
            occupied_result.reward_by_objective["expansion"],
        )


if __name__ == "__main__":
    unittest.main()
