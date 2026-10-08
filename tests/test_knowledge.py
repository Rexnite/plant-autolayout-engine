"""Tests for the WTP engineering knowledge base."""

import unittest

from wtp_autolayout.knowledge import (
    get_cluster,
    get_preferred_distance,
    get_relationship,
    get_separation_rule,
)


class TestEngineeringKnowledgeBase(unittest.TestCase):
    def test_get_cluster_identifies_hydraulic_unit(self) -> None:
        self.assertEqual(get_cluster("flash mixer"), "hydraulic")

    def test_get_cluster_identifies_sludge_unit(self) -> None:
        self.assertEqual(get_cluster("sludge thickener"), "sludge")

    def test_get_cluster_identifies_chemical_unit(self) -> None:
        self.assertEqual(get_cluster("chemical house"), "chemical")

    def test_get_cluster_identifies_clear_water_unit(self) -> None:
        self.assertEqual(get_cluster("clear water reservoir"), "clear_water")

    def test_get_relationship_returns_preferred_adjacency(self) -> None:
        self.assertEqual(get_relationship("flash mixer", "drop chamber"), "preferred_adjacency")

    def test_get_relationship_chemical_house_pipe_accessibility(self) -> None:
        self.assertEqual(get_relationship("chemical house", "flash mixer"), "pipe_accessibility")

    def test_get_preferred_distance_returns_positive_distance(self) -> None:
        self.assertGreater(get_preferred_distance("preferred_adjacency"), 0.0)

    def test_get_separation_rule_returns_sludge_admin_distance(self) -> None:
        self.assertEqual(get_separation_rule("sludge sump", "admin building"), 30.0)


if __name__ == "__main__":
    unittest.main()
