"""Multi-objective engineering reward calculations."""

from typing import Dict, Iterable, List, Optional, Tuple

from wtp_autolayout.geometry import GeometryEngine
from wtp_autolayout.profiles import get_plant_profile
from wtp_autolayout.models import Layout, Placement
from shapely.geometry import Polygon
from wtp_autolayout.constraints.spatial import proximity_results
from wtp_autolayout.constraints.site import access_results, group_relationship_results
from wtp_autolayout.geometry.site import zone_geometry
from wtp_autolayout.models import SiteZoneType
from shapely.ops import unary_union
from wtp_autolayout.geometry.flow_topology import flow_crossings


class EngineeringObjectiveCalculator:
    """Calculate positive engineering rewards for plant layouts."""

    def __init__(self, geometry_engine: Optional[GeometryEngine] = None):
        self.geometry_engine = geometry_engine or GeometryEngine()

    def calculate_pipe_efficiency(self, layout: Layout) -> float:
        """Reward shorter process transfer distances."""
        edges = self._flow_edges(layout)
        if not edges:
            return 0.0
        placements = self._placements(layout)
        distances = []
        weights = []
        boundary_scale = self._boundary_scale(layout)
        for edge in edges:
            source = placements.get(edge.source_unit_id)
            target = placements.get(edge.target_unit_id)
            if source is None or target is None:
                continue
            distance = self._centroid_distance(source, target)
            distances.append(distance)
            weights.append(max(edge.weight, 0.0) or 1.0)
        fraction = get_plant_profile(layout.plant_type).scoring_config.get("pipe_distance_fraction", 0.25)
        return self._short_distance_score(distances, weights, preferred_distance=boundary_scale * fraction)

    def calculate_gravity_reward(self, layout: Layout) -> float:
        """Reward gravity-preferred flows where source elevation is above target."""
        edges = [edge for edge in self._flow_edges(layout) if edge.gravity_preferred]
        if not edges:
            return 0.0
        placements = self._placements(layout)
        scored = 0
        reward = 0.0
        for edge in edges:
            source = placements.get(edge.source_unit_id)
            target = placements.get(edge.target_unit_id)
            if source is None or target is None:
                continue
            source_elevation = source.centroid.elevation
            target_elevation = target.centroid.elevation
            if source_elevation is None or target_elevation is None:
                continue
            scored += 1
            drop = source_elevation - target_elevation
            if drop >= 0:
                reward += min(1.0, 0.5 + drop / 10.0)
        if scored == 0:
            return 0.0
        return reward / float(scored)

    def calculate_cluster_reward(self, layout: Layout) -> float:
        """Reward preferred adjacency and related units being reasonably near."""
        profile = get_plant_profile(layout.plant_type)
        if not profile.use_wtp_knowledge:
            return 0.0
        units = {unit.unit_id: unit for unit in layout.units}
        placements = self._placements(layout)
        pairs: List[Tuple[str, str, float]] = []

        for edge in self._flow_edges(layout):
            if edge.source_unit_id in placements and edge.target_unit_id in placements:
                pairs.append((edge.source_unit_id, edge.target_unit_id, edge.weight or 1.0))

        unit_ids = list(placements)
        for index, unit_id_a in enumerate(unit_ids):
            for unit_id_b in unit_ids[index + 1 :]:
                unit_a = units.get(unit_id_a)
                unit_b = units.get(unit_id_b)
                if unit_a is None or unit_b is None:
                    continue
                relationship = profile.relationship(unit_a, unit_b)
                if relationship in ("preferred_adjacency", "same_cluster"):
                    pairs.append((unit_id_a, unit_id_b, 1.0))

        if not pairs:
            return 0.0

        scores = []
        weights = []
        for unit_id_a, unit_id_b, weight in pairs:
            unit_a = units.get(unit_id_a)
            unit_b = units.get(unit_id_b)
            relationship = profile.relationship(unit_a, unit_b) if unit_a and unit_b else None
            preferred = profile.preferred_distance(relationship)
            distance = self._centroid_distance(placements[unit_id_a], placements[unit_id_b])
            scores.append(max(0.0, 1.0 - distance / max(preferred * 2.0, 1.0)))
            weights.append(max(weight, 0.0) or 1.0)
        return self._weighted_average(scores, weights)

    def calculate_compactness_reward(self, layout: Layout) -> float:
        """Reward compact placement envelopes while preserving spacing elsewhere."""
        placements = list(layout.placements)
        if len(placements) < 2:
            return 0.0
        boundary_area = self._boundary_area(layout)
        if boundary_area <= 0:
            return 0.0
        minx = min(placement.centroid.easting for placement in placements)
        maxx = max(placement.centroid.easting for placement in placements)
        miny = min(placement.centroid.northing for placement in placements)
        maxy = max(placement.centroid.northing for placement in placements)
        envelope_area = max((maxx - minx) * (maxy - miny), 1.0)
        ratio = min(1.0, envelope_area / boundary_area)
        return max(0.0, 1.0 - ratio)

    def calculate_expansion_reward(self, layout: Layout) -> float:
        """Reward layouts that leave meaningful unused land for expansion."""
        boundary_area = self._boundary_area(layout)
        if boundary_area <= 0 or not layout.placements:
            return 0.0
        occupied_area = 0.0
        occupied_expansion_area = 0.0
        expansion_zone = self._expansion_zone(layout)
        placements = self._placements(layout)
        for unit in layout.units:
            placement = placements.get(unit.unit_id)
            if placement is None:
                continue
            try:
                clearance = self.geometry_engine.unit_to_clearance_geometry(unit, placement)
                occupied_area += clearance.area
                if expansion_zone is not None:
                    occupied_expansion_area += clearance.intersection(expansion_zone).area
            except Exception:
                continue
        free_ratio = max(0.0, min(1.0, 1.0 - occupied_area / boundary_area))
        target = get_plant_profile(layout.plant_type).scoring_config.get("expansion_free_target", 0.35)
        free_score = 1.0 if free_ratio >= target else free_ratio / target
        if expansion_zone is None or expansion_zone.area <= 0:
            return free_score
        reserved_score = max(0.0, min(1.0, 1.0 - occupied_expansion_area / expansion_zone.area))
        return free_score * 0.45 + reserved_score * 0.55

    def calculate_all(self, layout: Layout, selected=None) -> Dict[str, float]:
        """Return normalized objective rewards in the range 0..1."""
        methods = {"pipe_efficiency": self.calculate_pipe_efficiency,
                   "gravity": self.calculate_gravity_reward,
                   "cluster": self.calculate_cluster_reward,
                   "group_arrangement": self.calculate_group_arrangement,
                   "proximity": self.calculate_proximity_reward,
                   "flow_crossing": self.calculate_flow_crossing_reward,
                   "compactness": self.calculate_compactness_reward,
                   "expansion": self.calculate_expansion_reward,
                   "access": self.calculate_access_reward,
                   "group_relationship": self.calculate_group_relationship_reward}
        return {name: method(layout) if selected is None or name in selected else 0.0
                for name, method in methods.items()}

    def calculate_access_reward(self, layout: Layout) -> float:
        rows = [row for row in access_results(layout, self.geometry_engine)
                if row["required_maximum"] is not None]
        if not rows:
            return 0.0
        return sum(max(0.0, 1.0 - row["deviation"] / max(row["required_maximum"], 1.0))
                   for row in rows) / len(rows)

    def calculate_group_relationship_reward(self, layout: Layout) -> float:
        rows = [row for row in group_relationship_results(layout, self.geometry_engine)
                if row["requirement"] != "neutral"]
        if not rows:
            return 0.0
        return sum(max(0.0, 1.0 - row["deviation"] / max(row["required_distance"], 1.0))
                   for row in rows) / len(rows)

    def raw_metrics(self, layout: Layout, selected=None) -> Dict[str, object]:
        placements = self._placements(layout)
        distances = [self._centroid_distance(placements[edge.source_unit_id], placements[edge.target_unit_id])
                     for edge in self._flow_edges(layout)
                     if edge.source_unit_id in placements and edge.target_unit_id in placements]
        gravity = sum(1 for edge in self._flow_edges(layout) if edge.gravity_preferred)
        relations = proximity_results(layout, self.geometry_engine) if selected is None or "proximity" in selected else []
        return {"pipe_efficiency": {"mean_straight_distance": sum(distances) / len(distances) if distances else None,
                                     "edge_count": len(distances)},
                "gravity": {"preferred_edges": gravity},
                "cluster": {"placed_units": len(placements)},
                "group_arrangement": {"configured_groups": len(layout.system_groups)},
                "proximity": {"satisfied": sum(bool(row["passed"]) for row in relations), "total": len(relations)},
                "flow_crossing": {"count": len(flow_crossings(layout)) if selected is None or "flow_crossing" in selected else 0},
                "compactness": {"placed_units": len(placements)},
                "expansion": {"boundary_area": self._boundary_area(layout),
                              "explicit_zones": sum(zone.zone_type == SiteZoneType.EXPANSION for zone in layout.site_zones)},
                "access": {"required_units": sum(unit.access_required for unit in layout.units)},
                "group_relationship": {"rules": len(layout.group_relationships)}}

    @staticmethod
    def explanations() -> Dict[str, str]:
        return {"pipe_efficiency": "Shorter straight process transfers receive more credit.",
                "gravity": "Gravity-preferred links with sufficient elevation drop receive credit.",
                "cluster": "WTP process adjacency is rewarded where profile knowledge applies.",
                "group_arrangement": "Only groups configured for clustering receive proximity credit.",
                "proximity": "User-specified footprint-gap relationships contribute by satisfaction.",
                "flow_crossing": "Fewer straight-line topology crossings receive more credit; display routes do not change this.",
                "compactness": "A smaller placement envelope receives credit, subject to separate constraints.",
                "expansion": "Unused site area and any configured expansion zone receive credit.",
                "access": "Explicit unit access-distance requirements receive credit when met.",
                "group_relationship": "Explicit nearest-member group distance requirements receive credit when met."}

    def calculate_group_arrangement(self, layout: Layout) -> float:
        profile = get_plant_profile(layout.plant_type)
        groups = {group.group_id: group for group in layout.system_groups}
        by_group = {}
        for unit in layout.units:
            if unit.system_group:
                by_group.setdefault(unit.system_group, []).append(unit)
        placements = self._placements(layout)
        scores = []
        for group_id, units in by_group.items():
            preference = groups[group_id].preference if group_id in groups else profile.group_preferences.get(group_id, "loosely_clustered")
            if preference == "neutral":
                continue
            radius = groups[group_id].preferred_radius if group_id in groups else None
            preferred = radius or self._boundary_scale(layout) * 0.25
            for index, unit_a in enumerate(units):
                for unit_b in units[index + 1:]:
                    if unit_a.unit_id in placements and unit_b.unit_id in placements:
                        distance = self._centroid_distance(placements[unit_a.unit_id], placements[unit_b.unit_id])
                        scale = 1.0 if preference == "strongly_clustered" else 2.0
                        scores.append(max(0.0, 1.0 - distance / max(preferred * scale, 1.0)))
        return sum(scores) / len(scores) if scores else 0.0

    def calculate_proximity_reward(self, layout: Layout) -> float:
        rows = proximity_results(layout, self.geometry_engine)
        if not rows:
            return 0.0
        scale = self._boundary_scale(layout) * 0.25
        weights = [next(item.weight for item in layout.proximity_relationships if item.relationship_id == row["relationship_id"])
                   for row in rows]
        values = [max(0.0, 1.0 - row["deviation"] / max(row["required_distance"], scale, 1.0)) for row in rows]
        return self._weighted_average(values, weights)

    def calculate_flow_crossing_reward(self, layout: Layout) -> float:
        if layout.flow_graph is None or len(layout.flow_graph.edges) < 2:
            return 0.0
        return 1.0 / (1.0 + len(flow_crossings(layout)))

    def _flow_edges(self, layout: Layout):
        if layout.flow_graph is None:
            return []
        return list(layout.flow_graph.edges)

    def _placements(self, layout: Layout) -> Dict[str, Placement]:
        return {placement.unit_id: placement for placement in layout.placements}

    def _boundary_area(self, layout: Layout) -> float:
        try:
            return float(self.geometry_engine.boundary_to_polygon(layout.boundary).area)
        except Exception:
            return 0.0

    def _boundary_scale(self, layout: Layout) -> float:
        try:
            minx, miny, maxx, maxy = self.geometry_engine.boundary_to_polygon(layout.boundary).bounds
            return max(maxx - minx, maxy - miny, 1.0)
        except Exception:
            return 100.0

    def _expansion_zone(self, layout: Layout):
        explicit = [zone_geometry(zone) for zone in layout.site_zones
                    if zone.zone_type == SiteZoneType.EXPANSION]
        if explicit:
            return unary_union(explicit)
        zones = layout.metadata.get("expansion_zones") if isinstance(layout.metadata, dict) else None
        if zones:
            first_zone = zones[0]
            vertices = first_zone.get("vertices") if isinstance(first_zone, dict) else first_zone
            try:
                return Polygon([(point["easting"], point["northing"]) for point in vertices])
            except Exception:
                return None
        profile = get_plant_profile(layout.plant_type)
        if not profile.use_wtp_knowledge:
            return None
        try:
            minx, miny, maxx, maxy = self.geometry_engine.boundary_to_polygon(layout.boundary).bounds
        except Exception:
            return None
        width = maxx - minx
        height = maxy - miny
        config = profile.scoring_config
        return Polygon(
            [
                (minx + width * config["expansion_zone_x_min"], miny + height * config["expansion_zone_y_min"]),
                (maxx, miny + height * config["expansion_zone_y_min"]),
                (maxx, miny + height * config["expansion_zone_y_max"]),
                (minx + width * config["expansion_zone_x_min"], miny + height * config["expansion_zone_y_max"]),
            ]
        )

    def _short_distance_score(self, distances: Iterable[float], weights: Iterable[float], preferred_distance: float) -> float:
        scores = [max(0.0, 1.0 - distance / max(preferred_distance * 2.0, 1.0)) for distance in distances]
        return self._weighted_average(scores, list(weights))

    def _weighted_average(self, scores: List[float], weights: List[float]) -> float:
        if not scores:
            return 0.0
        total_weight = sum(weights) or float(len(scores))
        return sum(score * weight for score, weight in zip(scores, weights)) / total_weight

    def _centroid_distance(self, placement_a: Placement, placement_b: Placement) -> float:
        dx = placement_a.centroid.easting - placement_b.centroid.easting
        dy = placement_a.centroid.northing - placement_b.centroid.northing
        return (dx * dx + dy * dy) ** 0.5
