"""Software failure-mode checks; synthetic fixtures are not plant designs."""

import math
import tempfile
import unittest
from pathlib import Path

from shapely.geometry import box

from scripts.synthetic_projects import synthetic_project
from wtp_autolayout.candidates import CandidateGenerationError, CandidateGenerator
from wtp_autolayout.export import JSONExporter
from wtp_autolayout.geometry import GeometryEngine
from wtp_autolayout.geometry.routing import FlowRouter, RoutingStatus
from wtp_autolayout.models import Coordinate, FlowEdge, Placement, Violation, Severity
from wtp_autolayout.optimization import OptimizationError, Optimizer
from wtp_autolayout.optimization.annealing import refine_simulated_annealing
from wtp_autolayout.parsers.errors import ParserError
from wtp_autolayout.parsers.json_parser import parse_project_data
from wtp_autolayout.profiles import get_plant_profile
from wtp_autolayout.scoring import ScoringEngine
from wtp_autolayout.scoring.errors import ScoringError


def _rect(x0, y0, x1, y1):
    return [{"easting": x, "northing": y} for x, y in
            ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]


class FailureModesTests(unittest.TestCase):
    def test_infeasible_site_and_unit_cases(self):
        cases = {}
        tiny = synthetic_project(10)
        tiny["boundary"] = _rect(0, 0, 1, 1)
        cases["impossible site boundary"] = tiny
        crowded = synthetic_project(25)
        crowded["boundary"] = _rect(0, 0, 30, 30)
        cases["too many units"] = crowded
        oversized = synthetic_project(10)
        oversized["units"][1]["width"] = 1000
        cases["oversized unit"] = oversized
        isolated = synthetic_project(10)
        side = isolated["boundary"][2]["easting"]
        isolated["site_zones"][0]["vertices"] = _rect(0, 0, side, side)
        cases["unit trapped by exclusion"] = isolated
        for label, project in cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(CandidateGenerationError, "unit U-|unit U-000") as raised:
                    CandidateGenerator(random_seed=42, max_attempts_per_unit=8).generate(parse_project_data(project))
                message = str(raised.exception)
                self.assertIn("Diagnostic guidance", message)
                self.assertIn("site area", message)

    def test_impossible_hard_pairwise_and_access_rules(self):
        for rule, distance in (("min_distance", 10000), ("max_distance", 0)):
            project = synthetic_project(10)
            project["proximity_relationships"] = [{
                "relationship_id": "hard_pair", "unit_id_a": "U-000", "unit_id_b": "U-001",
                "relationship_type": rule, "distance": distance, "classification": "hard"}]
            with self.subTest(rule=rule), self.assertRaises(CandidateGenerationError):
                CandidateGenerator(random_seed=42, max_attempts_per_unit=8).generate(parse_project_data(project))
        project = synthetic_project(10)
        project["units"][0].update({"access_required": True, "max_access_distance": 0,
                                     "access_classification": "hard"})
        side = project["boundary"][2]["easting"]
        project["corridors"][0]["path"] = [{"easting": side * 2, "northing": 0},
                                               {"easting": side * 2, "northing": side}]
        with self.assertRaisesRegex(CandidateGenerationError, "access="):
            CandidateGenerator(random_seed=42, max_attempts_per_unit=8).generate(parse_project_data(project))

    def test_parser_failure_modes(self):
        cases = {}
        duplicate = synthetic_project(10)
        duplicate["units"][1]["unit_id"] = duplicate["units"][0]["unit_id"]
        cases["duplicate IDs"] = duplicate
        malformed = synthetic_project(10)
        malformed["boundary"] = malformed["boundary"][:2]
        cases["malformed boundary"] = malformed
        self_intersecting = synthetic_project(10)
        self_intersecting["boundary"] = [dict(vertex, vertex_order=index) for index, vertex in
                                         enumerate(_rect(0, 0, 30, 30)[::2] + _rect(0, 0, 30, 30)[1::2])]
        cases["self-intersecting boundary"] = self_intersecting
        zero_width = synthetic_project(10)
        zero_width["units"][1]["width"] = 0
        cases["zero dimension"] = zero_width
        negative_width = synthetic_project(10)
        negative_width["units"][1]["width"] = -1
        cases["negative dimension"] = negative_width
        missing = synthetic_project(10)
        del missing["units"][0]["name"]
        cases["missing field"] = missing
        group = synthetic_project(10)
        group["units"][0]["system_group"] = "unknown"
        cases["invalid group reference"] = group
        corridor = synthetic_project(10)
        corridor["corridors"][0]["path"] = [{"easting": 1, "northing": 1}]
        cases["invalid corridor geometry"] = corridor
        disconnected = synthetic_project(10)
        disconnected["flow_edges"][0]["target_unit_id"] = "missing"
        cases["disconnected flow reference"] = disconnected
        contradictory_pair = synthetic_project(10)
        contradictory_pair["proximity_relationships"] = [
            {"relationship_id": "min", "unit_id_a": "U-000", "unit_id_b": "U-001",
             "relationship_type": "min_distance", "distance": 30, "classification": "hard"},
            {"relationship_id": "max", "unit_id_a": "U-000", "unit_id_b": "U-001",
             "relationship_type": "max_distance", "distance": 10, "classification": "hard"}]
        cases["contradictory proximity rules"] = contradictory_pair
        contradictory_group = synthetic_project(10)
        contradictory_group["group_relationships"] = [
            {"relationship_id": "gmin", "group_id_a": "sludge", "group_id_b": "support",
             "relationship_type": "min_distance", "distance": 30, "classification": "hard"},
            {"relationship_id": "gmax", "group_id_a": "sludge", "group_id_b": "support",
             "relationship_type": "max_distance", "distance": 10, "classification": "hard"}]
        cases["contradictory group rules"] = contradictory_group
        for label, project in cases.items():
            with self.subTest(label=label), self.assertRaises(ParserError):
                parse_project_data(project)

    def test_unroutable_barrier_falls_back_without_hanging(self):
        project = synthetic_project(10)
        side = project["boundary"][2]["easting"]
        project["site_zones"][0]["vertices"] = _rect(side / 2 - 3, 0, side / 2 + 3, side)
        project["flow_edges"] = project["flow_edges"][:1]
        layout = parse_project_data(project)
        layout.placements = [Placement("left", "U-000", Coordinate(30, side / 2)),
                             Placement("right", "U-001", Coordinate(side - 30, side / 2))]
        result = FlowRouter(max_grid_lines=12).route_with_diagnostics(layout)
        self.assertEqual(len(result.routes), 1)
        self.assertIn(result.routes[0].status, (RoutingStatus.BLOCKED, RoutingStatus.FALLBACK))
        self.assertEqual(result.to_dict()["fallback_count"], 1)

    def test_shared_flow_endpoint_is_bounded(self):
        layout = parse_project_data(synthetic_project(10))
        layout = CandidateGenerator(random_seed=42).generate(layout)
        flow_type = layout.flow_graph.edges[0].flow_type
        layout.flow_graph.edges = [FlowEdge("star-%s" % index, "U-000", "U-%03d" % index,
                                            flow_type) for index in range(1, 10)]
        result = FlowRouter(max_grid_lines=16).route_with_diagnostics(layout)
        self.assertEqual(len(result.routes), 9)
        self.assertTrue(all(math.isfinite(route.length) for route in result.routes))

    def test_optimizer_infeasible_and_edge_settings(self):
        project = synthetic_project(10)
        project["boundary"] = _rect(0, 0, 1, 1)
        layout = parse_project_data(project)
        generator = CandidateGenerator(random_seed=42, max_attempts_per_unit=5)
        scoring = ScoringEngine(constraint_engine=get_plant_profile(layout.plant_type).constraint_engine())
        optimizer = Optimizer(generator, scoring, initial_candidate_count=1, max_iterations=0,
                              random_seed=42)
        with self.assertRaisesRegex(OptimizationError, "Candidate generation failed"):
            optimizer.optimize(layout)
        feasible = parse_project_data(synthetic_project(10))
        for algorithm in ("ranked", "local_search", "simulated_annealing"):
            with self.subTest(algorithm=algorithm):
                result = optimizer.optimize(feasible, algorithm=algorithm)
                self.assertIsNotNone(result.best_layout)
                self.assertTrue(math.isfinite(result.best_score_result.score))
                self.assertEqual(result.iterations, 0)

    def test_export_unwritable_parent_fails_cleanly(self):
        layout = parse_project_data(synthetic_project(10))
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / "not_a_directory"
            blocker.write_text("block", encoding="utf-8")
            with self.assertRaises(OSError):
                JSONExporter().export_layout(layout, blocker / "layout.json")


class NumericalRobustnessTests(unittest.TestCase):
    def test_nonfinite_numbers_rejected_before_geometry(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    Coordinate(value, 0)
                with self.assertRaises(ValueError):
                    Placement("P", "U", Coordinate(0, 0), rotation=value)
                with self.assertRaises(ValueError):
                    Violation("V", "C", [], value, Severity.HIGH)
                project = synthetic_project(10)
                project["units"][1]["width"] = value
                with self.assertRaises(ParserError):
                    parse_project_data(project)

    def test_small_and_large_finite_coordinates(self):
        for x in (0.0, 1e-9, 1e12 + 0.1):
            with self.subTest(x=x):
                self.assertEqual(Coordinate(x, -0.0).easting, x)
        self.assertFalse(GeometryEngine().overlaps(
            box(0, 0, 1, 1), box(1 + 1e-9, 0, 2, 1)))

    def test_router_and_annealing_reject_nonfinite_settings(self):
        with self.assertRaises(ValueError):
            FlowRouter(routing_clearance=float("nan"))
        with self.assertRaises(ValueError):
            FlowRouter(max_grid_lines=100000)
        with self.assertRaises(OptimizationError):
            refine_simulated_annealing(None, None, None, None, 0,
                                       initial_temperature=float("nan"))

    def test_weighted_penalty_overflow_is_reported(self):
        violation = Violation("V", "C", [], 1e308, Severity.HIGH)
        with self.assertRaisesRegex(ScoringError, "overflow"):
            ScoringEngine(weight_overrides={"C": 1e308}).score_violations([violation])


if __name__ == "__main__":
    unittest.main()
