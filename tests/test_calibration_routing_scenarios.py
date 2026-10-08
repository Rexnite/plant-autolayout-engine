"""Calibration, topology, display routing, and scenario regressions."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from shapely.geometry import LineString

from wtp_autolayout.constraints.spatial import proximity_results
from wtp_autolayout.geometry import GeometryEngine
from wtp_autolayout.geometry.flow_topology import flow_crossing_diagnostics, flow_crossings
from wtp_autolayout.geometry.routing import FlowRouter, RoutingStatus
from wtp_autolayout.models import (Boundary, Coordinate, EngineeringUnit, FlowEdge, FlowGraph,
                                   Layout, Placement, SpatialRelationship, SystemGroup)
from wtp_autolayout.models.layout import LayoutStatistics
from wtp_autolayout.profiles import get_plant_profile
from wtp_autolayout.scenarios import ScenarioResult, compare_scenarios
from wtp_autolayout.scoring import ScoringEngine
from wtp_autolayout.scoring.result import ScoringResult


ROOT = Path(__file__).resolve().parents[1]


def make_layout(positions, edges):
    boundary = Boundary("site", [Coordinate(0, 0), Coordinate(100, 0),
                                 Coordinate(100, 100), Coordinate(0, 100)])
    units = [EngineeringUnit(key, key, "process", "rectangle", width=6, length=6)
             for key in positions]
    placements = [Placement("p_" + key, key, Coordinate(*point))
                  for key, point in positions.items()]
    graph = FlowGraph("flows", list(positions),
                      [FlowEdge("e%s" % i, a, b, "other")
                       for i, (a, b) in enumerate(edges)])
    return Layout("test", boundary, units=units, placements=placements, flow_graph=graph)


class CalibrationRoutingScenarioTests(unittest.TestCase):
    def test_profile_configuration_and_weight_scaling(self):
        layout = make_layout({"A": (20, 20), "B": (40, 20)}, [("A", "B")])
        profile = get_plant_profile(layout.plant_type)
        self.assertEqual(profile.group_preferences["chemical"], "neutral")
        result = ScoringEngine(reward_weight_overrides={"pipe_efficiency": 70}).score_layout(layout)
        self.assertLess(result.weight_scale, 1)
        self.assertAlmostEqual(sum(item.effective_weight for item in result.objective_breakdown.values()), 35)
        self.assertIn("mean_straight_distance", result.objective_breakdown["pipe_efficiency"].raw_metric)
        self.assertEqual(ScoringResult.from_dict(result.to_dict()).to_dict(), result.to_dict())

    def test_profile_rejects_bad_weights(self):
        from wtp_autolayout.profiles.base import PlantProfile
        with self.assertRaises(ValueError):
            PlantProfile(get_plant_profile("wtp").plant_type, "Bad", (), {"pipe_efficiency": float("inf")})

    def test_crossing_types(self):
        positions = {"A": (20, 20), "B": (80, 80), "C": (20, 80), "D": (80, 20)}
        layout = make_layout(positions, [("A", "B"), ("C", "D")])
        event = flow_crossing_diagnostics(layout)[0]
        self.assertEqual(event.kind, "interior_crossing")
        self.assertEqual(event.coordinate, (50.0, 50.0))
        self.assertEqual(len(flow_crossings(layout)), 1)
        layout.flow_graph.edges = [FlowEdge("one", "A", "B", "other"), FlowEdge("two", "A", "D", "other")]
        self.assertFalse(flow_crossings(layout))
        layout.flow_graph.edges = [FlowEdge("one", "A", "B", "other"), FlowEdge("two", "C", "B", "other")]
        self.assertFalse(flow_crossings(layout))

    def test_parallel_collinear_endpoint_and_multiple(self):
        layout = make_layout({"A": (10, 50), "B": (70, 50), "C": (30, 50), "D": (90, 50)},
                             [("A", "B"), ("C", "D")])
        self.assertEqual(flow_crossing_diagnostics(layout)[0].kind, "collinear_overlap")
        layout.placements[2].centroid = Coordinate(70, 50)
        self.assertFalse(flow_crossings(layout))
        layout.placements[2].centroid = Coordinate(10, 70)
        layout.placements[3].centroid = Coordinate(90, 70)
        self.assertFalse(flow_crossings(layout))
        multi = make_layout({"A": (10, 10), "B": (90, 90), "C": (10, 90), "D": (90, 10),
                             "E": (50, 5), "F": (50, 95)},
                            [("A", "B"), ("C", "D"), ("E", "F")])
        self.assertEqual(len(flow_crossings(multi)), 3)

    def test_orthogonal_paths_crossing_diagnostic_is_topology_only(self):
        layout = make_layout({"A": (10, 10), "B": (90, 90), "C": (10, 90), "D": (90, 10)},
                             [("A", "B"), ("C", "D")])
        self.assertEqual(len(flow_crossings(layout)), 1)
        self.assertEqual(len(FlowRouter().route(layout)), 2)
        self.assertEqual(len(flow_crossings(layout)), 1)

    def test_router_avoids_obstacle_with_clearance(self):
        layout = make_layout({"A": (15, 50), "B": (85, 50), "C": (50, 50)}, [("A", "B")])
        route = FlowRouter(routing_clearance=3).route(layout)[0]
        obstacle = GeometryEngine().unit_to_geometry(layout.units[2], layout.placements[2]).buffer(3)
        self.assertEqual(route.status, RoutingStatus.SUCCESS)
        self.assertFalse(LineString(route.points).intersects(obstacle))
        self.assertGreater(route.length, route.straight_length)
        self.assertGreater(route.bends, 0)

    def test_router_fallback_and_metrics(self):
        layout = make_layout({"A": (15, 50), "B": (85, 50), "C": (50, 50)}, [("A", "B")])
        layout.units[2].width = 100
        layout.units[2].length = 100
        result = FlowRouter(routing_clearance=2).route_with_diagnostics(layout)
        self.assertIn(result.routes[0].status, (RoutingStatus.BLOCKED, RoutingStatus.FALLBACK))
        self.assertEqual(result.to_dict()["fallback_count"], 1)

    def test_group_preferences_and_proximity_diagnostics(self):
        layout = make_layout({"A": (20, 20), "B": (80, 20)}, [])
        layout.units[0].system_group = layout.units[1].system_group = "support"
        layout.system_groups = [SystemGroup("support", "Support", 20, "neutral")]
        from wtp_autolayout.scoring.objectives import EngineeringObjectiveCalculator
        calculator = EngineeringObjectiveCalculator()
        self.assertEqual(calculator.calculate_group_arrangement(layout), 0)
        layout.system_groups[0].preference = "strongly_clustered"
        self.assertEqual(calculator.calculate_group_arrangement(layout), 0)
        layout.placements[1].centroid = Coordinate(30, 20)
        self.assertGreater(calculator.calculate_group_arrangement(layout), 0)
        layout.proximity_relationships = [SpatialRelationship("gap", "A", "B", "min_distance", 5)]
        row = proximity_results(layout)[0]
        self.assertEqual(row["distance_basis"], "footprint_gap")
        self.assertEqual(row["source"], "user_entered")
        self.assertEqual(row["actual_distance"], 4)
        self.assertEqual(Layout.from_dict(layout.to_dict()).system_groups[0].preference, "strongly_clustered")

    def test_conflicting_hard_target_is_rejected(self):
        layout = make_layout({"A": (20, 20), "B": (40, 20)}, [])
        data = layout.to_dict()
        data["proximity_relationships"] = [
            SpatialRelationship("minimum", "A", "B", "min_distance", 20, "hard").to_dict(),
            SpatialRelationship("target", "A", "B", "target_distance", 10, "hard").to_dict(),
        ]
        with self.assertRaisesRegex(ValueError, "conflicting hard target"):
            Layout.from_dict(data)

    def test_scenario_roundtrip_and_comparison(self):
        layout = make_layout({"A": (20, 20), "B": (50, 20)}, [("A", "B")])
        score = ScoringEngine().score_layout(layout)
        layout.statistics = LayoutStatistics(metadata={"diagnostics": {
            "active_profile": "Water Treatment Plant",
            "optimization_settings": {"algorithm": "ranked", "seed": 42,
                                      "candidate_count": 5, "iterations": 10}}})
        run = SimpleNamespace(layout=layout,
              optimization_result=SimpleNamespace(best_score_result=score),
              timings={"total_runtime": 1.5}, exported_files={"pdf": "demo.pdf"},
              output_dir="scenario_a")
        input_data = {"optimization_settings": {"layout_mode": "balanced"}}
        first = ScenarioResult.from_run("A", input_data, run, 42, 5, 10, "ranked")
        second = ScenarioResult.from_dict({**first.to_dict(), "name": "B", "algorithm": "local_search"})
        self.assertEqual(ScenarioResult.from_dict(first.to_dict()).to_dict(), first.to_dict())
        self.assertEqual(first.optimization_settings["candidate_count"], 5)
        self.assertEqual(first.output_directory, "scenario_a")
        self.assertEqual(first.active_profile, "Water Treatment Plant")
        rows = compare_scenarios([first, second])
        self.assertEqual(len(rows), 2)
        self.assertNotIn("Best", rows[0])
        with self.assertRaises(ValueError):
            compare_scenarios([first])
        json.dumps(first.to_dict())


if __name__ == "__main__":
    unittest.main()
