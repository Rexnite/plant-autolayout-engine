"""Tests for Phase 7 optimization engine."""

import copy
import unittest

from wtp_autolayout.candidates import CandidateGenerator
from wtp_autolayout.models import (
    Boundary,
    Coordinate,
    EngineeringUnit,
    FlowEdge,
    FlowGraph,
    FlowType,
    Layout,
    LayoutMode,
    OptimizationStatus,
    Placement,
    Severity,
    ShapeType,
    UnitCategory,
    Violation,
)
from wtp_autolayout.optimization import OptimizationError, OptimizationRunResult, Optimizer
from wtp_autolayout.scoring import ScoringEngine


def boundary(width: float = 240.0, height: float = 160.0) -> Boundary:
    return Boundary(
        boundary_id="B-001",
        vertices=[
            Coordinate(0.0, 0.0),
            Coordinate(width, 0.0),
            Coordinate(width, height),
            Coordinate(0.0, height),
        ],
    )


def unit(unit_id: str, order=None) -> EngineeringUnit:
    return EngineeringUnit(
        unit_id=unit_id,
        name=unit_id,
        category=UnitCategory.PROCESS,
        shape_type=ShapeType.RECTANGLE,
        width=10.0,
        length=12.0,
        required_clearance=2.0,
        process_order=order,
    )


def sample_layout() -> Layout:
    return Layout(
        layout_id="L-OPT",
        boundary=boundary(),
        units=[unit("u1", order=1), unit("u2", order=2), unit("u3", order=3)],
    )


def flow_layout(layout_id: str, second_x: float, third_x: float = 50.0) -> Layout:
    base = Layout(
        layout_id=layout_id,
        boundary=boundary(width=300.0, height=180.0),
        units=[unit("flash_mixer", order=1), unit("drop_chamber", order=2), unit("clarifier", order=3)],
        placements=[
            Placement("P-flash", "flash_mixer", Coordinate(30.0, 80.0, elevation=105.0)),
            Placement("P-drop", "drop_chamber", Coordinate(second_x, 80.0, elevation=104.0)),
            Placement("P-clarifier", "clarifier", Coordinate(third_x, 80.0, elevation=103.0)),
        ],
        flow_graph=FlowGraph(
            graph_id="FG-OPT",
            unit_ids=["flash_mixer", "drop_chamber", "clarifier"],
            edges=[
                FlowEdge("F-1", "flash_mixer", "drop_chamber", FlowType.PROCESS_WATER, gravity_preferred=True),
                FlowEdge("F-2", "drop_chamber", "clarifier", FlowType.PROCESS_WATER, gravity_preferred=True),
            ],
        ),
    )
    base.units[0].name = "Flash Mixer"
    base.units[1].name = "Drop Chamber"
    base.units[2].name = "Clarifier"
    return base


def optimizer(seed: int = 1, max_iterations: int = 5, initial_candidate_count: int = 3) -> Optimizer:
    return Optimizer(
        candidate_generator=CandidateGenerator(random_seed=seed),
        scoring_engine=ScoringEngine(),
        random_seed=seed,
        initial_candidate_count=initial_candidate_count,
        max_iterations=max_iterations,
    )


def hard_violation() -> Violation:
    return Violation(
        violation_id="C-001-1",
        constraint_id="C-001",
        affected_units=["u1"],
        penalty=20.0,
        severity=Severity.CRITICAL,
        description="Hard failure",
        suggested_action="Fix boundary",
    )


class FakeCandidateGenerator:
    def __init__(self, layouts):
        self.layouts = layouts

    def generate_many(self, layout, count=5, mode=None, score_generated=False, replace_existing=False):
        return [copy.deepcopy(item) for item in self.layouts[:count]]


class TestOptimizer(unittest.TestCase):
    def test_generate_ranked_candidates_returns_ranked_candidates(self) -> None:
        result = optimizer(seed=1).generate_ranked_candidates(sample_layout(), count=3)

        self.assertIsInstance(result, OptimizationRunResult)
        self.assertEqual(len(result.candidate_results), 3)
        self.assertEqual([candidate.rank for candidate in result.candidate_results], [1, 2, 3])
        self.assertEqual(result.algorithm, "ranked")

    def test_optimize_does_not_mutate_input_layout(self) -> None:
        base = sample_layout()
        before = base.to_dict()

        optimizer(seed=2).optimize(base, algorithm="local_search")

        self.assertEqual(base.to_dict(), before)

    def test_local_search_returns_optimization_run_result(self) -> None:
        result = optimizer(seed=3).optimize(sample_layout(), algorithm="local_search")

        self.assertIsInstance(result, OptimizationRunResult)
        self.assertEqual(result.algorithm, "local_search")
        self.assertIsNotNone(result.best_layout)

    def test_simulated_annealing_returns_optimization_run_result(self) -> None:
        result = optimizer(seed=4).optimize(sample_layout(), algorithm="simulated_annealing")

        self.assertIsInstance(result, OptimizationRunResult)
        self.assertEqual(result.algorithm, "simulated_annealing")
        self.assertIsNotNone(result.best_layout)

    def test_best_layout_has_scoring_result(self) -> None:
        result = optimizer(seed=5).generate_ranked_candidates(sample_layout(), count=2)

        self.assertIsNotNone(result.best_layout)
        self.assertIsNotNone(result.best_score_result)
        self.assertEqual(result.best_score_result.score, result.candidate_results[0].scoring_result.score)

    def test_candidates_are_sorted_by_score(self) -> None:
        good = sample_layout()
        bad = sample_layout()
        bad.layout_id = "L-BAD"
        bad.violations = [hard_violation()]
        fake = FakeCandidateGenerator([bad, good])
        result = Optimizer(fake, ScoringEngine(), initial_candidate_count=2).generate_ranked_candidates(sample_layout(), count=2)

        scores = [candidate.scoring_result.score for candidate in result.candidate_results]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(result.best_layout.layout_id, "L-OPT")

    def test_fixed_random_seed_gives_reproducible_best_score_for_ranked_candidates(self) -> None:
        first = optimizer(seed=7).generate_ranked_candidates(sample_layout(), count=3)
        second = optimizer(seed=7).generate_ranked_candidates(sample_layout(), count=3)

        self.assertEqual(first.best_score_result.score, second.best_score_result.score)

    def test_impossible_layout_raises_optimization_error(self) -> None:
        impossible = Layout(
            layout_id="L-IMPOSSIBLE",
            boundary=boundary(width=20.0, height=20.0),
            units=[
                EngineeringUnit(
                    unit_id="huge",
                    name="Huge",
                    category=UnitCategory.PROCESS,
                    shape_type=ShapeType.RECTANGLE,
                    width=100.0,
                    length=100.0,
                )
            ],
        )

        with self.assertRaises(OptimizationError):
            optimizer(seed=8, initial_candidate_count=1).generate_ranked_candidates(impossible, count=1)

    def test_hard_constraint_invalid_candidate_is_not_best_when_feasible_exists(self) -> None:
        feasible = sample_layout()
        invalid = sample_layout()
        invalid.layout_id = "L-INVALID"
        invalid.violations = [hard_violation()]
        fake = FakeCandidateGenerator([invalid, feasible])

        result = Optimizer(fake, ScoringEngine(), initial_candidate_count=2).optimize(
            sample_layout(),
            algorithm="ranked",
        )

        self.assertEqual(result.best_layout.layout_id, feasible.layout_id)
        self.assertTrue(result.best_score_result.passed_hard_constraints)

    def test_metadata_includes_algorithm_and_mode(self) -> None:
        result = optimizer(seed=9).optimize(sample_layout(), mode=LayoutMode.FIT, algorithm="local_search")

        self.assertEqual(result.metadata["algorithm"], "local_search")
        self.assertEqual(result.metadata["mode"], "fit")
        self.assertIn(result.status, (OptimizationStatus.SUCCESSFUL, OptimizationStatus.PARTIAL))

    def test_optimizer_prefers_shorter_process_routes(self) -> None:
        short_route = flow_layout("L-SHORT", second_x=42.0, third_x=54.0)
        long_route = flow_layout("L-LONG", second_x=150.0, third_x=260.0)
        fake = FakeCandidateGenerator([long_route, short_route])

        result = Optimizer(fake, ScoringEngine(), initial_candidate_count=2).optimize(
            sample_layout(),
            algorithm="ranked",
        )

        self.assertEqual(result.best_layout.layout_id, "L-SHORT")
        self.assertGreater(result.candidate_results[0].scoring_result.score, result.candidate_results[1].scoring_result.score)

    def test_optimizer_prefers_cluster_layouts_beyond_zero_violations(self) -> None:
        clustered = flow_layout("L-CLUSTERED", second_x=42.0, third_x=54.0)
        scattered = flow_layout("L-SCATTERED", second_x=90.0, third_x=170.0)
        fake = FakeCandidateGenerator([scattered, clustered])

        result = Optimizer(fake, ScoringEngine(), initial_candidate_count=2).generate_ranked_candidates(
            sample_layout(),
            count=2,
        )

        self.assertEqual(result.best_layout.layout_id, "L-CLUSTERED")
        self.assertEqual(result.best_score_result.violation_count, 0)


if __name__ == "__main__":
    unittest.main()
