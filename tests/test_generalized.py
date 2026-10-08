"""General plant architecture and explicit engineering input regressions."""

import copy
import json
import unittest
from pathlib import Path

from wtp_autolayout.constraints.engine import default_core_engine
from wtp_autolayout.constraints.spatial import proximity_results
from wtp_autolayout.geometry.flow_topology import flow_crossings
from wtp_autolayout.geometry.routing import FlowRouter
from wtp_autolayout.geometry import GeometryEngine
from wtp_autolayout.models import (ConstraintClassification, Coordinate, Layout, Placement,
                                   PlantType, SpatialRelationship, SystemGroup)
from wtp_autolayout.parsers import parse_json_file
from wtp_autolayout.parsers import parse_excel_file
from wtp_autolayout.parsers.errors import ParserError
from wtp_autolayout.parsers.json_parser import parse_project_data
from wtp_autolayout.profiles import get_plant_profile
from wtp_autolayout.scoring import ScoringEngine
from wtp_autolayout.scoring.objectives import EngineeringObjectiveCalculator
from wtp_autolayout.candidates import CandidateGenerator
from wtp_autolayout.optimization import Optimizer
from wtp_autolayout.export import JSONExporter
from wtp_autolayout.visualization import PlotlyLayoutRenderer
import tempfile


ROOT = Path(__file__).resolve().parents[1]


class GeneralizedEngineTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "sample_data" / "sample_petrochemical_input.json").read_text())

    def test_plant_profile_and_round_trip(self):
        layout = parse_project_data(self.data)
        self.assertEqual(layout.plant_type, PlantType.PETROCHEMICAL)
        self.assertFalse(get_plant_profile(layout.plant_type).use_wtp_constraints)
        self.assertGreater(len(get_plant_profile(layout.plant_type).default_units()), 0)
        self.assertEqual(Layout.from_dict(layout.to_dict()).system_groups[0].group_id, "feed")
        self.assertEqual(len(Layout.from_dict(layout.to_dict()).proximity_relationships), 2)
        self.assertIsNone(EngineeringObjectiveCalculator()._expansion_zone(layout))
        bad = copy.deepcopy(self.data)
        bad["plant_type"] = "unknown"
        with self.assertRaises(ParserError):
            parse_project_data(bad)

    def test_legacy_wtp_defaults(self):
        layout = parse_json_file(str(ROOT / "sample_data" / "sample_wtp_input.json"))
        self.assertEqual(layout.plant_type, PlantType.WTP)
        self.assertGreater(len(layout.units), 0)

    def test_boundary_auto_order_closure_and_invalid_order(self):
        layout = parse_project_data(self.data)
        self.assertEqual(len(layout.boundary.vertices), 4)
        self.assertGreater(layout.boundary.vertices[0].easting, -1)
        bad = copy.deepcopy(self.data)
        bad["boundary"] = [
            {"easting": 0, "northing": 0, "vertex_order": 1},
            {"easting": 10, "northing": 10, "vertex_order": 2},
            {"easting": 0, "northing": 10, "vertex_order": 3},
            {"easting": 10, "northing": 0, "vertex_order": 4},
        ]
        with self.assertRaisesRegex(ParserError, "Invalid boundary"):
            parse_project_data(bad)

    def test_ambiguous_concave_boundary_requires_order(self):
        bad = copy.deepcopy(self.data)
        bad["boundary"].append({"easting": 100, "northing": 80})
        with self.assertRaisesRegex(ParserError, "ambiguous"):
            parse_project_data(bad)

    def test_unknown_group_and_relationship_validation(self):
        bad = copy.deepcopy(self.data)
        bad["units"][0]["system_group"] = "missing"
        with self.assertRaises(ParserError):
            parse_project_data(bad)
        with self.assertRaises(ValueError):
            SpatialRelationship("x", "a", "a", "min_distance", 1)
        with self.assertRaises(ValueError):
            SpatialRelationship("x", "a", "b", "max_distance", -1)
        bad = copy.deepcopy(self.data)
        bad["proximity_relationships"] = [
            {"relationship_id": "min", "unit_id_a": "feed_pump", "unit_id_b": "process_skid",
             "relationship_type": "min_distance", "distance": 40},
            {"relationship_id": "max", "unit_id_a": "feed_pump", "unit_id_b": "process_skid",
             "relationship_type": "max_distance", "distance": 20},
        ]
        with self.assertRaisesRegex(ParserError, "conflicting"):
            parse_project_data(bad)

    def test_proximity_hard_and_soft(self):
        layout = parse_project_data(self.data)
        layout.placements = [Placement("A", "product_tank", Coordinate(100, 70)),
                             Placement("B", "utility_building", Coordinate(120, 70))]
        rows = proximity_results(layout)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["passed"])
        scoring = ScoringEngine(constraint_engine=default_core_engine()).score_layout(layout)
        self.assertFalse(scoring.passed_hard_constraints)
        self.assertGreater(scoring.hard_penalty, 0)
        layout.proximity_relationships[1].classification = ConstraintClassification.SOFT
        scoring = ScoringEngine(constraint_engine=default_core_engine()).score_layout(layout)
        self.assertGreater(scoring.soft_penalty, 0)

    def test_soft_near_target_and_max(self):
        layout = parse_project_data(self.data)
        layout.proximity_relationships = [
            SpatialRelationship("near", "feed_pump", "process_skid", "preferred_near", 10),
            SpatialRelationship("target", "feed_pump", "process_skid", "target_distance", 25),
            SpatialRelationship("max", "feed_pump", "process_skid", "max_distance", 20),
        ]
        layout.placements = [Placement("A", "feed_pump", Coordinate(20, 20)),
                             Placement("B", "process_skid", Coordinate(80, 20))]
        self.assertEqual(len(proximity_results(layout)), 3)
        self.assertTrue(all(not item["passed"] for item in proximity_results(layout)))

    def test_flow_crossing_and_shared_endpoint(self):
        layout = parse_project_data(self.data)
        layout.flow_graph.edges = layout.flow_graph.edges[:2]
        layout.placements = [Placement("A", "feed_pump", Coordinate(20, 20)),
                             Placement("B", "process_skid", Coordinate(80, 80)),
                             Placement("C", "product_tank", Coordinate(20, 80))]
        self.assertEqual(flow_crossings(layout), [])
        # Two independent diagonal connections cross at an interior point.
        from wtp_autolayout.models import FlowEdge, FlowType
        layout.flow_graph.edges = [FlowEdge("X", "feed_pump", "process_skid", FlowType.OTHER),
                                   FlowEdge("Y", "product_tank", "utility_building", FlowType.OTHER)]
        layout.placements.append(Placement("D", "utility_building", Coordinate(80, 20)))
        self.assertEqual(flow_crossings(layout), [("X", "Y")])

    def test_crossing_changes_score_and_route_has_length(self):
        layout = parse_project_data(self.data)
        layout.placements = [Placement("A", "feed_pump", Coordinate(30, 30)),
                             Placement("B", "process_skid", Coordinate(100, 40)),
                             Placement("C", "product_tank", Coordinate(170, 60)),
                             Placement("D", "utility_building", Coordinate(210, 120))]
        routes = FlowRouter().route(layout)
        self.assertEqual(len(routes), 2)
        self.assertTrue(all(route.length > 0 for route in routes))
        self.assertGreater(ScoringEngine(default_core_engine()).score_layout(layout).reward_total, 0)

    def test_json_excel_ui_adapter_and_exports(self):
        import app
        for name in ("sample_general_wtp_input", "sample_petrochemical_input"):
            json_layout = parse_json_file(str(ROOT / "sample_data" / (name + ".json")))
            excel_layout = parse_excel_file(str(ROOT / "sample_data" / (name + ".xlsx")))
            self.assertEqual(json_layout.plant_type, excel_layout.plant_type)
            self.assertEqual(len(json_layout.units), len(excel_layout.units))
            self.assertEqual(parse_project_data(app._layout_to_input(excel_layout)).plant_type, excel_layout.plant_type)
            self.assertGreater(app._boundary_preview(app._layout_to_input(excel_layout)["boundary"]).area, 0)
        with tempfile.TemporaryDirectory() as directory:
            layout = parse_project_data(self.data)
            layout = CandidateGenerator(random_seed=12).generate(layout)
            target = Path(directory) / "nested" / "layout.json"
            JSONExporter().export_layout(layout, target)
            self.assertTrue(target.exists())
            html = Path(directory) / "layout.html"
            PlotlyLayoutRenderer().export_html(layout, html)
            self.assertTrue(html.exists())

    def test_candidate_preserves_groups_and_hard_proximity(self):
        layout = parse_project_data(self.data)
        candidate = CandidateGenerator(random_seed=42, max_attempts_per_unit=2000).generate(layout)
        self.assertEqual(candidate.system_groups, layout.system_groups)
        self.assertEqual(candidate.plant_type, PlantType.PETROCHEMICAL)
        hard = [row for row in proximity_results(candidate) if row["classification"] == "hard"]
        self.assertTrue(all(row["passed"] for row in hard))

    def test_candidate_respects_exclusion_zone(self):
        layout = parse_project_data(self.data)
        layout.metadata["exclusion_zones"] = [[
            {"easting": 0, "northing": 0}, {"easting": 100, "northing": 0},
            {"easting": 100, "northing": 180}, {"easting": 0, "northing": 180},
        ]]
        candidate = CandidateGenerator(random_seed=42, max_attempts_per_unit=2000).generate(layout)
        self.assertTrue(all(placement.centroid.easting > 90 for placement in candidate.placements))

    def test_grouped_units_are_sampled_nearby(self):
        layout = parse_project_data(self.data)
        layout.units[1].system_group = "feed"
        layout.proximity_relationships = []
        candidate = CandidateGenerator(random_seed=42).generate(layout)
        points = {item.unit_id: item.centroid for item in candidate.placements}
        a, b = points["feed_pump"], points["process_skid"]
        distance = ((a.easting - b.easting) ** 2 + (a.northing - b.northing) ** 2) ** 0.5
        self.assertLess(distance, 100)

    def test_router_avoids_unrelated_unit_when_clear_polyline_exists(self):
        from shapely.geometry import LineString
        layout = parse_project_data(self.data)
        layout.flow_graph.edges = layout.flow_graph.edges[:1]
        layout.placements = [Placement("A", "feed_pump", Coordinate(20, 20)),
                             Placement("B", "process_skid", Coordinate(100, 100)),
                             Placement("C", "product_tank", Coordinate(100, 20))]
        route = FlowRouter().route(layout)[0]
        obstacle = GeometryEngine().unit_to_geometry(layout.units[2], layout.placements[2])
        self.assertFalse(route.fallback)
        self.assertFalse(LineString(route.points).intersects(obstacle))

    def test_feasible_candidates_rank_by_proximity_and_crossings(self):
        from wtp_autolayout.models import FlowEdge, FlowType
        base = parse_project_data(self.data)
        base.proximity_relationships = [SpatialRelationship(
            "near", "feed_pump", "process_skid", "max_distance", 80)]
        base.flow_graph.edges = [FlowEdge("X", "feed_pump", "process_skid", FlowType.OTHER),
                                 FlowEdge("Y", "product_tank", "utility_building", FlowType.OTHER)]
        good = copy.deepcopy(base)
        good.placements = [Placement("A", "feed_pump", Coordinate(30, 30)),
                           Placement("B", "process_skid", Coordinate(90, 30)),
                           Placement("C", "product_tank", Coordinate(30, 130)),
                           Placement("D", "utility_building", Coordinate(190, 130))]
        bad = copy.deepcopy(base)
        bad.placements = [Placement("A", "feed_pump", Coordinate(30, 30)),
                          Placement("B", "process_skid", Coordinate(210, 140)),
                          Placement("C", "product_tank", Coordinate(30, 140)),
                          Placement("D", "utility_building", Coordinate(210, 30))]
        self.assertEqual(len(flow_crossings(good)), 0)
        self.assertEqual(len(flow_crossings(bad)), 1)
        scoring = ScoringEngine(default_core_engine())
        self.assertTrue(scoring.score_layout(good).passed_hard_constraints)
        self.assertTrue(scoring.score_layout(bad).passed_hard_constraints)
        self.assertGreater(scoring.score_layout(good).score, scoring.score_layout(bad).score)

        class FixedCandidates:
            def generate_many(self, _layout, count, mode=None, score_generated=False):
                return [bad, good]

        result = Optimizer(FixedCandidates(), scoring, initial_candidate_count=2).generate_ranked_candidates(base, 2)
        self.assertEqual(result.best_layout.placements[1].centroid.easting, 90)


if __name__ == "__main__":
    unittest.main()
