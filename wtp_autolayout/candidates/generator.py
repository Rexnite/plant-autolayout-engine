"""Initial candidate layout generator."""

import copy
import math
import random
from typing import Dict, Iterable, List, Optional, Tuple

from wtp_autolayout.geometry.site import hard_site_obstacles, access_geometries, zone_geometry
from wtp_autolayout.constraints.site import group_relationship_results

from wtp_autolayout.geometry import GeometryEngine, GeometryError
from wtp_autolayout.profiles import get_plant_profile
from wtp_autolayout.models import ConstraintClassification, SpatialRelationship, SpatialRelationshipType
from wtp_autolayout.models import (
    Coordinate,
    EngineeringUnit,
    Layout,
    LayoutMode,
    Placement,
    ShapeType,
)

from .errors import CandidateGenerationError
from .strategies import ROTATIONS, choose_point


class CandidateGenerator:
    """Generate initial feasible placement candidates for all layout units."""

    def __init__(
        self,
        geometry_engine: Optional[GeometryEngine] = None,
        scoring_engine=None,
        random_seed: Optional[int] = None,
        max_attempts_per_unit: int = 500,
    ):
        if max_attempts_per_unit <= 0:
            raise CandidateGenerationError("max_attempts_per_unit must be positive")
        self.geometry_engine = geometry_engine or GeometryEngine()
        self.scoring_engine = scoring_engine
        self.random_seed = random_seed
        self.max_attempts_per_unit = max_attempts_per_unit
        self._rng = random.Random(random_seed)

    def generate(
        self,
        layout: Layout,
        mode: Optional[LayoutMode] = None,
        replace_existing: bool = False,
        score_generated: bool = False,
    ) -> Layout:
        """Generate one new Layout with placements for every engineering unit."""
        self._validate_layout_input(layout)
        selected_mode = self._mode(mode, layout)
        try:
            boundary_geometry = self.geometry_engine.boundary_to_polygon(layout.boundary)
        except GeometryError as error:
            raise CandidateGenerationError("Invalid site boundary: %s. Recheck boundary vertices." % error)
        self._preflight_fit(layout.units, boundary_geometry)
        bounds = boundary_geometry.bounds
        exclusions = self._exclusion_geometries(layout)
        soft_zones = [zone_geometry(zone).buffer(zone.clearance) for zone in layout.site_zones
                      if zone.classification == ConstraintClassification.SOFT]
        access_paths = access_geometries(layout)
        ordered_units = self._ordered_units(layout.units)
        existing = self._existing_placements(layout.placements)
        process_range = self._process_range(layout.units)
        profile = get_plant_profile(layout.plant_type)
        cluster_anchors = self._cluster_anchors(layout.units, bounds, profile) if profile.use_wtp_knowledge else {}
        group_anchors = self._group_anchors(layout, bounds)
        sampling_relationships = list(layout.proximity_relationships)
        for edge in layout.flow_graph.edges if layout.flow_graph else []:
            sampling_relationships.append(SpatialRelationship(
                "flow_sample_%s" % edge.flow_id, edge.source_unit_id, edge.target_unit_id,
                SpatialRelationshipType.PREFERRED_NEAR,
                max(bounds[2] - bounds[0], bounds[3] - bounds[1]) * 0.25,
            ))

        placed_units: Dict[str, EngineeringUnit] = {}
        placed_placements: Dict[str, Placement] = {}
        placed_geometries: Dict[str, object] = {}
        generated_placements: List[Placement] = []

        for unit in ordered_units:
            existing_placement = existing.get(unit.unit_id)
            if not replace_existing and existing_placement is not None:
                if self._placement_is_valid(
                    unit,
                    existing_placement,
                    boundary_geometry,
                    placed_units,
                    placed_placements,
                    placed_geometries,
                    exclusions,
                ) and self._access_is_valid(unit, existing_placement, access_paths) and self._satisfies_placed_hard_relationships(
                    unit, existing_placement, layout.proximity_relationships, placed_units, placed_placements
                ):
                    self._record_placement(
                        unit,
                        existing_placement,
                        placed_units,
                        placed_placements,
                        placed_geometries,
                    )
                    generated_placements.append(existing_placement)
                    continue

            placement = self._generate_unit_placement(
                unit,
                selected_mode,
                bounds,
                boundary_geometry,
                placed_units,
                placed_placements,
                placed_geometries,
                process_range,
                cluster_anchors.get(profile.inferred_group(unit)) or group_anchors.get(unit.system_group),
                sampling_relationships,
                exclusions,
                access_paths,
                soft_zones,
            )
            self._record_placement(unit, placement, placed_units, placed_placements, placed_geometries)
            generated_placements.append(placement)

        candidate = Layout(
            layout_id="%s_candidate" % layout.layout_id,
            boundary=layout.boundary,
            units=list(layout.units),
            placements=generated_placements,
            flow_graph=layout.flow_graph,
            roads=list(layout.roads),
            drains=list(layout.drains),
            constraints=list(layout.constraints),
            violations=[],
            statistics=None,
            optimization_score=None,
            layout_mode=selected_mode,
            metadata=copy.deepcopy(layout.metadata),
            plant_type=layout.plant_type,
            system_groups=copy.deepcopy(layout.system_groups),
            proximity_relationships=copy.deepcopy(layout.proximity_relationships),
            site_zones=copy.deepcopy(layout.site_zones),
            existing_structures=copy.deepcopy(layout.existing_structures),
            corridors=copy.deepcopy(layout.corridors),
            group_relationships=copy.deepcopy(layout.group_relationships),
        )
        if layout.group_relationships and any(not row["satisfied"] and row["classification"] == "hard"
                                              for row in group_relationship_results(candidate)):
            raise CandidateGenerationError("Candidate violates hard group relationship")

        if score_generated and self.scoring_engine is not None:
            self.scoring_engine.score_layout(candidate, update_layout=True)

        return candidate

    def generate_many(
        self,
        layout: Layout,
        count: int = 5,
        mode: Optional[LayoutMode] = None,
        replace_existing: bool = False,
        score_generated: bool = False,
    ) -> List[Layout]:
        if count <= 0:
            return []

        candidates: List[Layout] = []
        global_attempt_limit = max(count * 10, count)
        attempts = 0
        last_error = None
        while len(candidates) < count and attempts < global_attempt_limit:
            attempts += 1
            try:
                candidate = self.generate(
                    layout,
                    mode=mode,
                    replace_existing=replace_existing,
                    score_generated=score_generated,
                )
            except CandidateGenerationError as error:
                last_error = error
                continue
            candidate.layout_id = "%s_%03d" % (candidate.layout_id, len(candidates) + 1)
            candidates.append(candidate)

        if not candidates:
            raise CandidateGenerationError("Could not generate any candidates: %s" % last_error)
        if len(candidates) < count:
            raise CandidateGenerationError("Generated %s of %s requested candidates" % (len(candidates), count))
        return candidates

    def _generate_unit_placement(
        self,
        unit: EngineeringUnit,
        mode: LayoutMode,
        bounds: Tuple[float, float, float, float],
        boundary_geometry,
        placed_units: Dict[str, EngineeringUnit],
        placed_placements: Dict[str, Placement],
        placed_geometries: Dict[str, object],
        process_range: Optional[Tuple[int, int]],
        cluster_anchor: Optional[Tuple[float, float]] = None,
        relationships=None,
        exclusions=(),
        access_paths=(),
        soft_zones=(),
    ) -> Placement:
        failures = {"boundary": 0, "site": 0, "overlap": 0, "clearance": 0,
                    "access": 0, "relationship": 0}
        for attempt in range(1, self.max_attempts_per_unit + 1):
            process_fraction = self._process_fraction(unit, process_range) if mode == LayoutMode.BALANCED else None
            active_anchor = cluster_anchor if attempt <= int(self.max_attempts_per_unit * 0.7) else None
            x, y = self._choose_cluster_aware_point(bounds, mode, process_fraction, active_anchor)
            if relationships and attempt <= int(self.max_attempts_per_unit * 0.65):
                related = [item for item in relationships if unit.unit_id in (item.unit_id_a, item.unit_id_b)
                           and (item.unit_id_b if item.unit_id_a == unit.unit_id else item.unit_id_a) in placed_placements]
                if related:
                    relation = self._rng.choice(related)
                    other_id = relation.unit_id_b if unit.unit_id == relation.unit_id_a else relation.unit_id_a
                    other = placed_placements[other_id].centroid
                    reach = max(relation.distance, 1.0)
                    if relation.relationship_type == SpatialRelationshipType.MIN_DISTANCE:
                        reach += max(unit.width or unit.diameter or 1.0, unit.length or 1.0)
                    angle = self._rng.uniform(0, 6.283185307179586)
                    x = self._clamp(other.easting + self._rng.uniform(0.7, 1.2) * reach * math.cos(angle), bounds[0], bounds[2])
                    y = self._clamp(other.northing + self._rng.uniform(0.7, 1.2) * reach * math.sin(angle), bounds[1], bounds[3])
            rotation = 0.0 if unit.shape_type == ShapeType.CIRCLE else self._rng.choice(ROTATIONS)
            placement = Placement(
                placement_id="P-%s-%03d" % (unit.unit_id, attempt),
                unit_id=unit.unit_id,
                centroid=Coordinate(x, y),
                rotation=rotation,
            )
            if not self._placement_is_valid(
                unit,
                placement,
                boundary_geometry,
                placed_units,
                placed_placements,
                placed_geometries,
                exclusions,
                failures,
            ):
                continue
            if not self._access_is_valid(unit, placement, access_paths):
                failures["access"] += 1
                continue
            if soft_zones and attempt < int(self.max_attempts_per_unit * 0.7):
                footprint = self.geometry_engine.unit_to_geometry(unit, placement)
                if any(footprint.intersection(zone).area > 1e-8 for zone in soft_zones) and self._rng.random() < 0.7:
                    continue
            if not self._satisfies_placed_hard_relationships(unit, placement, relationships or [], placed_units, placed_placements):
                failures["relationship"] += 1
                continue
            return placement

        raise CandidateGenerationError(
            "No feasible placement found for unit %s after %s attempts. Diagnostic guidance: "
            "site area %.1f, approximate placed footprint area %.1f, hard site obstacles %s; "
            "rejections boundary=%s, site=%s, overlap=%s, clearance=%s, access=%s, hard relationships=%s. "
            "Check site dimensions, exclusions, unit size/clearance, hard distance rules and access corridors."
            % (unit.unit_id, self.max_attempts_per_unit, boundary_geometry.area,
               sum(shape.area for shape in placed_geometries.values()), len(exclusions),
               failures["boundary"], failures["site"], failures["overlap"],
               failures["clearance"], failures["access"], failures["relationship"])
        )

    def _placement_is_valid(
        self,
        unit: EngineeringUnit,
        placement: Placement,
        boundary_geometry,
        placed_units: Dict[str, EngineeringUnit],
        placed_placements: Dict[str, Placement],
        placed_geometries: Dict[str, object],
        exclusions=(),
        failures=None,
    ) -> bool:
        try:
            geometry = self.geometry_engine.unit_to_geometry(unit, placement)
        except GeometryError:
            if failures is not None:
                failures["boundary"] += 1
            return False
        if not self.geometry_engine.is_inside_boundary(geometry, boundary_geometry):
            if failures is not None:
                failures["boundary"] += 1
            return False
        clearance = max(unit.required_clearance, unit.maintenance_clearance)
        occupied = geometry.buffer(clearance) if clearance else geometry
        if any(occupied.intersection(zone).area > 1e-8 for zone in exclusions):
            if failures is not None:
                failures["site"] += 1
            return False
        for placed_unit_id, placed_geometry in placed_geometries.items():
            if self.geometry_engine.overlaps(geometry, placed_geometry):
                if failures is not None:
                    failures["overlap"] += 1
                return False
            if self.geometry_engine.clearance_violation(
                unit,
                placement,
                placed_units[placed_unit_id],
                placed_placements[placed_unit_id],
            ):
                if failures is not None:
                    failures["clearance"] += 1
                return False
        return True

    def _record_placement(
        self,
        unit: EngineeringUnit,
        placement: Placement,
        placed_units: Dict[str, EngineeringUnit],
        placed_placements: Dict[str, Placement],
        placed_geometries: Dict[str, object],
    ) -> None:
        placed_units[unit.unit_id] = unit
        placed_placements[unit.unit_id] = placement
        placed_geometries[unit.unit_id] = self.geometry_engine.unit_to_geometry(unit, placement)

    def _ordered_units(self, units: Iterable[EngineeringUnit]) -> List[EngineeringUnit]:
        indexed = list(enumerate(units))
        return [unit for _, unit in sorted(indexed, key=lambda item: self._order_key(item[0], item[1]))]

    def _order_key(self, index: int, unit: EngineeringUnit):
        if unit.process_order is None:
            return (1, index)
        return (0, unit.process_order, index)

    def _existing_placements(self, placements: Iterable[Placement]) -> Dict[str, Placement]:
        existing: Dict[str, Placement] = {}
        for placement in placements:
            existing[placement.unit_id] = placement
        return existing

    def _validate_layout_input(self, layout: Layout) -> None:
        if not layout.units:
            raise CandidateGenerationError("Layout must contain at least one EngineeringUnit")

        unit_ids = set()
        for unit in layout.units:
            if unit.unit_id in unit_ids:
                raise CandidateGenerationError("Duplicate unit_id in layout.units: %s" % unit.unit_id)
            unit_ids.add(unit.unit_id)

        placement_unit_ids = set()
        for placement in layout.placements:
            if placement.unit_id not in unit_ids:
                raise CandidateGenerationError(
                    "Existing placement %s references unknown unit_id %s"
                    % (placement.placement_id, placement.unit_id)
                )
            if placement.unit_id in placement_unit_ids:
                raise CandidateGenerationError(
                    "Duplicate existing placement for unit_id %s" % placement.unit_id
                )
            placement_unit_ids.add(placement.unit_id)

    def _preflight_fit(self, units, boundary_geometry) -> None:
        minx, miny, maxx, maxy = boundary_geometry.bounds
        site_width, site_height = maxx - minx, maxy - miny
        footprint_area = 0.0
        for unit in units:
            if unit.shape_type in (ShapeType.RECTANGLE, ShapeType.SQUARE):
                width, length = unit.width, unit.length
                fits_envelope = ((length <= site_width and width <= site_height) or
                                 (width <= site_width and length <= site_height))
            elif unit.shape_type == ShapeType.CIRCLE:
                fits_envelope = unit.diameter <= min(site_width, site_height)
            else:
                fits_envelope = True
            if not fits_envelope:
                raise CandidateGenerationError(
                    "No feasible placement for unit %s: footprint dimensions exceed the %.1f x %.1f "
                    "site envelope. Diagnostic guidance: site area %.1f. Reduce the unit size or enlarge "
                    "the site boundary." % (unit.unit_id, site_width, site_height, boundary_geometry.area))
            try:
                footprint_area += self.geometry_engine.unit_to_geometry(
                    unit, Placement("preflight-%s" % unit.unit_id, unit.unit_id, Coordinate(0, 0))).area
            except GeometryError as error:
                raise CandidateGenerationError("Unit %s cannot form a valid footprint: %s. Check shape and dimensions."
                                               % (unit.unit_id, error))
        if footprint_area > boundary_geometry.area + 1e-8:
            raise CandidateGenerationError(
                "No feasible placement for unit %s: total unit footprint area %.1f exceeds site area %.1f. "
                "Diagnostic guidance: reduce unit sizes/count or enlarge the site boundary."
                % (units[-1].unit_id, footprint_area, boundary_geometry.area))

    def _mode(self, mode: Optional[LayoutMode], layout: Layout) -> LayoutMode:
        value = mode or layout.layout_mode or LayoutMode.BALANCED
        if isinstance(value, LayoutMode):
            return value
        return LayoutMode(value)

    def _process_range(self, units: Iterable[EngineeringUnit]) -> Optional[Tuple[int, int]]:
        orders = [unit.process_order for unit in units if unit.process_order is not None]
        if not orders:
            return None
        return min(orders), max(orders)

    def _process_fraction(self, unit: EngineeringUnit, process_range: Optional[Tuple[int, int]]) -> Optional[float]:
        if unit.process_order is None or process_range is None:
            return None
        min_order, max_order = process_range
        if min_order == max_order:
            return 0.5
        # Keep a small edge margin so early/late units do not hug the boundary.
        raw = float(unit.process_order - min_order) / float(max_order - min_order)
        return 0.1 + raw * 0.8

    def _cluster_anchors(self, units: Iterable[EngineeringUnit], bounds: Tuple[float, float, float, float], profile=None) -> Dict[str, Tuple[float, float]]:
        profile = profile or get_plant_profile("wtp")
        clusters = {profile.inferred_group(unit) for unit in units}
        clusters.discard(None)
        minx, miny, maxx, maxy = bounds
        width = maxx - minx
        height = maxy - miny
        defaults = {
            "hydraulic": (minx + width * 0.42, miny + height * 0.55),
            "sludge": (minx + width * 0.22, miny + height * 0.22),
            "chemical": (minx + width * 0.25, miny + height * 0.78),
            "clear_water": (minx + width * 0.72, miny + height * 0.76),
        }
        return {cluster: defaults.get(cluster, (minx + width * 0.5, miny + height * 0.5)) for cluster in clusters}

    def _choose_cluster_aware_point(
        self,
        bounds: Tuple[float, float, float, float],
        mode: LayoutMode,
        process_fraction: Optional[float],
        cluster_anchor: Optional[Tuple[float, float]],
    ) -> Tuple[float, float]:
        if cluster_anchor is None:
            return choose_point(self._rng, bounds, mode, process_fraction=process_fraction)

        minx, miny, maxx, maxy = bounds
        width = maxx - minx
        height = maxy - miny
        anchor_x, anchor_y = cluster_anchor
        if mode == LayoutMode.BALANCED and process_fraction is not None:
            local_x = anchor_x + (process_fraction - 0.5) * width * 0.22
        else:
            local_x = anchor_x
        x = self._clamp(self._rng.gauss(local_x, max(width, 1.0) / 12.0), minx, maxx)
        y = self._clamp(self._rng.gauss(anchor_y, max(height, 1.0) / 12.0), miny, maxy)
        return x, y

    def _clamp(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    def _group_anchors(self, layout: Layout, bounds: Tuple[float, float, float, float]) -> Dict[str, Tuple[float, float]]:
        group_ids = sorted({unit.system_group for unit in layout.units if unit.system_group})
        if not group_ids:
            return {}
        minx, miny, maxx, maxy = bounds
        columns = max(1, math.ceil(len(group_ids) ** 0.5))
        rows = math.ceil(len(group_ids) / columns)
        return {group_id: (minx + (maxx - minx) * ((index % columns) + 0.5) / columns,
                           miny + (maxy - miny) * ((index // columns) + 0.5) / rows)
                for index, group_id in enumerate(group_ids)}

    def _satisfies_placed_hard_relationships(self, unit, placement, relationships, placed_units, placed_placements) -> bool:
        geometry = self.geometry_engine.unit_to_geometry(unit, placement)
        for item in relationships:
            if item.classification != ConstraintClassification.HARD or unit.unit_id not in (item.unit_id_a, item.unit_id_b):
                continue
            other_id = item.unit_id_b if unit.unit_id == item.unit_id_a else item.unit_id_a
            if other_id not in placed_placements:
                continue
            other = self.geometry_engine.unit_to_geometry(placed_units[other_id], placed_placements[other_id])
            distance = self.geometry_engine.distance(geometry, other)
            if item.relationship_type == SpatialRelationshipType.MIN_DISTANCE and distance + 1e-6 < item.distance:
                return False
            if item.relationship_type == SpatialRelationshipType.MAX_DISTANCE and distance > item.distance + 1e-6:
                return False
            if item.relationship_type == SpatialRelationshipType.TARGET_DISTANCE and abs(distance - item.distance) > 1e-6:
                return False
        return True

    def _exclusion_geometries(self, layout):
        try:
            return [shape for _, shape in hard_site_obstacles(layout)]
        except GeometryError as error:
            raise CandidateGenerationError(str(error))

    def _access_is_valid(self, unit, placement, access_paths):
        if not unit.access_required or unit.max_access_distance is None or unit.access_classification != ConstraintClassification.HARD:
            return True
        footprint = self.geometry_engine.unit_to_geometry(unit, placement)
        return bool(access_paths) and min(footprint.distance(shape) for _, shape in access_paths) <= unit.max_access_distance + 1e-6
