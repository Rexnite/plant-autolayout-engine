"""Tests for Phase 6 candidate generation."""

import unittest

from wtp_autolayout.candidates import CandidateGenerationError, CandidateGenerator
from wtp_autolayout.geometry import GeometryEngine
from wtp_autolayout.models import (
    Boundary,
    Coordinate,
    EngineeringUnit,
    Layout,
    LayoutMode,
    Placement,
    ShapeType,
    UnitCategory,
)
from wtp_autolayout.scoring import ScoringEngine


def boundary(width: float = 220.0, height: float = 160.0) -> Boundary:
    return Boundary(
        boundary_id="B-001",
        vertices=[
            Coordinate(0.0, 0.0),
            Coordinate(width, 0.0),
            Coordinate(width, height),
            Coordinate(0.0, height),
        ],
    )


def unit(unit_id: str, order=None, clearance: float = 2.0) -> EngineeringUnit:
    return EngineeringUnit(
        unit_id=unit_id,
        name=unit_id,
        category=UnitCategory.PROCESS,
        shape_type=ShapeType.RECTANGLE,
        width=10.0,
        length=12.0,
        required_clearance=clearance,
        process_order=order,
    )


def sample_layout() -> Layout:
    return Layout(
        layout_id="L-SAMPLE",
        boundary=boundary(),
        units=[
            unit("raw_water_inlet", order=1),
            unit("cascade_aerator", order=2),
            unit("flash_mixer", order=3),
            unit("clarifier", order=4),
        ],
    )


class TestCandidateGenerator(unittest.TestCase):
    def setUp(self) -> None:
        self.geometry_engine = GeometryEngine()

    def assert_candidate_geometry_valid(self, layout: Layout) -> None:
        boundary_geometry = self.geometry_engine.boundary_to_polygon(layout.boundary)
        units_by_id = {unit.unit_id: unit for unit in layout.units}
        placements_by_id = {placement.unit_id: placement for placement in layout.placements}
        geometries = {}

        for unit_obj in layout.units:
            placement = placements_by_id[unit_obj.unit_id]
            geometry = self.geometry_engine.unit_to_geometry(unit_obj, placement)
            self.assertTrue(self.geometry_engine.is_inside_boundary(geometry, boundary_geometry))
            geometries[unit_obj.unit_id] = geometry

        ids = list(geometries)
        for index, unit_id_a in enumerate(ids):
            for unit_id_b in ids[index + 1 :]:
                self.assertFalse(self.geometry_engine.overlaps(geometries[unit_id_a], geometries[unit_id_b]))
                self.assertFalse(
                    self.geometry_engine.clearance_violation(
                        units_by_id[unit_id_a],
                        placements_by_id[unit_id_a],
                        units_by_id[unit_id_b],
                        placements_by_id[unit_id_b],
                    )
                )

    def test_generate_returns_layout_with_placements_for_all_units(self) -> None:
        generated = CandidateGenerator(random_seed=1).generate(sample_layout())

        self.assertIsInstance(generated, Layout)
        self.assertEqual(len(generated.placements), len(generated.units))
        self.assertEqual({p.unit_id for p in generated.placements}, {u.unit_id for u in generated.units})

    def test_generated_placements_are_inside_boundary(self) -> None:
        generated = CandidateGenerator(random_seed=2).generate(sample_layout())

        self.assert_candidate_geometry_valid(generated)

    def test_generated_placements_do_not_overlap(self) -> None:
        generated = CandidateGenerator(random_seed=3).generate(sample_layout())

        self.assert_candidate_geometry_valid(generated)

    def test_generated_placements_do_not_violate_clearance(self) -> None:
        generated = CandidateGenerator(random_seed=4).generate(sample_layout())

        self.assert_candidate_geometry_valid(generated)

    def test_existing_placements_are_preserved_when_replace_existing_false(self) -> None:
        base = sample_layout()
        base.placements = [Placement("P-EXISTING", "raw_water_inlet", Coordinate(30.0, 30.0), rotation=90.0)]

        generated = CandidateGenerator(random_seed=5).generate(base, replace_existing=False)
        preserved = [p for p in generated.placements if p.unit_id == "raw_water_inlet"][0]

        self.assertEqual(preserved.placement_id, "P-EXISTING")
        self.assertEqual(preserved.centroid.easting, 30.0)
        self.assertEqual(preserved.rotation, 90.0)

    def test_existing_placements_are_replaced_when_replace_existing_true(self) -> None:
        base = sample_layout()
        base.placements = [Placement("P-EXISTING", "raw_water_inlet", Coordinate(30.0, 30.0), rotation=90.0)]

        generated = CandidateGenerator(random_seed=5).generate(base, replace_existing=True)
        replaced = [p for p in generated.placements if p.unit_id == "raw_water_inlet"][0]

        self.assertNotEqual(replaced.placement_id, "P-EXISTING")

    def test_generate_many_returns_requested_count(self) -> None:
        candidates = CandidateGenerator(random_seed=6).generate_many(sample_layout(), count=3)

        self.assertEqual(len(candidates), 3)
        self.assertEqual(len({candidate.layout_id for candidate in candidates}), 3)

    def test_fixed_random_seed_produces_reproducible_placements(self) -> None:
        first = CandidateGenerator(random_seed=7).generate(sample_layout())
        second = CandidateGenerator(random_seed=7).generate(sample_layout())

        first_signature = [(p.unit_id, round(p.centroid.easting, 4), round(p.centroid.northing, 4), p.rotation) for p in first.placements]
        second_signature = [(p.unit_id, round(p.centroid.easting, 4), round(p.centroid.northing, 4), p.rotation) for p in second.placements]
        self.assertEqual(first_signature, second_signature)

    def test_impossible_layout_raises_candidate_generation_error(self) -> None:
        impossible = Layout(
            layout_id="L-IMPOSSIBLE",
            boundary=boundary(width=20.0, height=20.0),
            units=[
                EngineeringUnit(
                    unit_id="huge_unit",
                    name="Huge Unit",
                    category=UnitCategory.PROCESS,
                    shape_type=ShapeType.RECTANGLE,
                    width=100.0,
                    length=100.0,
                )
            ],
        )

        with self.assertRaises(CandidateGenerationError):
            CandidateGenerator(random_seed=8, max_attempts_per_unit=20).generate(impossible)

    def test_balanced_mode_roughly_respects_process_order_eastward_bias(self) -> None:
        base = Layout(
            layout_id="L-BALANCED",
            boundary=boundary(width=400.0, height=120.0),
            units=[unit("u1", order=1, clearance=0.0), unit("u2", order=2, clearance=0.0), unit("u3", order=3, clearance=0.0)],
        )

        generated = CandidateGenerator(random_seed=9).generate(base, mode=LayoutMode.BALANCED)
        x_by_unit = {placement.unit_id: placement.centroid.easting for placement in generated.placements}

        self.assertLess(x_by_unit["u1"], x_by_unit["u3"])

    def test_score_generated_updates_optimization_score_when_scoring_engine_supplied(self) -> None:
        generated = CandidateGenerator(
            random_seed=10,
            scoring_engine=ScoringEngine(),
        ).generate(sample_layout(), score_generated=True)

        self.assertIsNotNone(generated.optimization_score)
        self.assertGreaterEqual(generated.optimization_score, 0.0)
        self.assertLessEqual(generated.optimization_score, 100.0)

    def test_empty_layout_units_raises_candidate_generation_error(self) -> None:
        empty = Layout(layout_id="L-EMPTY", boundary=boundary(), units=[])

        with self.assertRaises(CandidateGenerationError):
            CandidateGenerator(random_seed=11).generate(empty)

    def test_duplicate_unit_id_raises_candidate_generation_error(self) -> None:
        duplicate = Layout(
            layout_id="L-DUPLICATE",
            boundary=boundary(),
            units=[unit("duplicate"), unit("duplicate")],
        )

        with self.assertRaises(CandidateGenerationError):
            CandidateGenerator(random_seed=12).generate(duplicate)

    def test_existing_placement_for_unknown_unit_id_raises_candidate_generation_error(self) -> None:
        base = sample_layout()
        base.placements = [Placement("P-UNKNOWN", "unknown_unit", Coordinate(30.0, 30.0))]

        with self.assertRaises(CandidateGenerationError):
            CandidateGenerator(random_seed=13).generate(base)

    def test_duplicate_existing_placements_for_same_unit_id_raise_candidate_generation_error(self) -> None:
        base = sample_layout()
        base.placements = [
            Placement("P-ONE", "raw_water_inlet", Coordinate(30.0, 30.0)),
            Placement("P-TWO", "raw_water_inlet", Coordinate(40.0, 40.0)),
        ]

        with self.assertRaises(CandidateGenerationError):
            CandidateGenerator(random_seed=14).generate(base)

    def test_hydraulic_units_generated_near_each_other(self) -> None:
        generated = CandidateGenerator(random_seed=21, max_attempts_per_unit=1000).generate(cluster_layout())
        placements = {placement.unit_id: placement for placement in generated.placements}

        distance = self._distance(placements["flash_mixer"], placements["clarifier"])

        self.assertLess(distance, 90.0)

    def test_sludge_units_remain_grouped(self) -> None:
        generated = CandidateGenerator(random_seed=22, max_attempts_per_unit=1000).generate(cluster_layout())
        placements = {placement.unit_id: placement for placement in generated.placements}

        distance = self._distance(placements["sludge_sump"], placements["sludge_thickener"])

        self.assertLess(distance, 90.0)

    def test_chemical_house_has_acceptable_connection_distance_without_forced_adjacency(self) -> None:
        generated = CandidateGenerator(random_seed=23, max_attempts_per_unit=1000).generate(cluster_layout())
        placements = {placement.unit_id: placement for placement in generated.placements}

        distance = self._distance(placements["chemical_house"], placements["flash_mixer"])

        self.assertLess(distance, 150.0)
        self.assertGreater(distance, 15.0)

    def _distance(self, placement_a: Placement, placement_b: Placement) -> float:
        dx = placement_a.centroid.easting - placement_b.centroid.easting
        dy = placement_a.centroid.northing - placement_b.centroid.northing
        return (dx * dx + dy * dy) ** 0.5


def cluster_layout() -> Layout:
    return Layout(
        layout_id="L-CLUSTER",
        boundary=boundary(width=300.0, height=220.0),
        units=[
            unit("flash_mixer", order=1, clearance=1.0),
            unit("clarifier", order=2, clearance=1.0),
            unit("sludge_sump", clearance=1.0),
            unit("sludge_thickener", clearance=1.0),
            unit("chemical_house", clearance=1.0),
        ],
    )


if __name__ == "__main__":
    unittest.main()
