"""Simple local-search refinement."""

import copy
import random
from typing import Optional, Tuple

from wtp_autolayout.geometry import GeometryEngine
from wtp_autolayout.models import ConstraintClassification, Coordinate, Layout, ShapeType
from wtp_autolayout.scoring import ScoringEngine
from wtp_autolayout.constraints.site import site_violations
from wtp_autolayout.constraints.spatial import proximity_violations

from .result import CandidateResult


ROTATIONS = (0.0, 90.0, 180.0, 270.0)


def refine_local_search(
    initial: CandidateResult,
    scoring_engine: ScoringEngine,
    geometry_engine: GeometryEngine,
    rng: random.Random,
    max_iterations: int,
) -> Tuple[Layout, object, int]:
    """Accept only score-improving feasible moves."""
    current_layout = copy.deepcopy(initial.layout)
    current_score = initial.scoring_result
    best_layout = copy.deepcopy(current_layout)
    best_score = current_score
    completed = 0

    for iteration in range(max_iterations):
        completed = iteration + 1
        proposed_layout = propose_neighbor(current_layout, geometry_engine, rng)
        if proposed_layout is None:
            continue
        proposed_score = scoring_engine.score_layout(proposed_layout)
        if not proposed_score.passed_hard_constraints:
            continue
        if proposed_score.score > current_score.score:
            current_layout = proposed_layout
            current_score = proposed_score
            if proposed_score.score > best_score.score:
                best_layout = copy.deepcopy(proposed_layout)
                best_score = proposed_score

    return best_layout, best_score, completed


def propose_neighbor(layout: Layout, geometry_engine: GeometryEngine, rng: random.Random) -> Optional[Layout]:
    """Move one placement slightly and keep only geometry-feasible proposals."""
    if not layout.placements:
        return None

    proposed = copy.deepcopy(layout)
    placement_index = rng.randrange(len(proposed.placements))
    placement = proposed.placements[placement_index]
    units_by_id = {unit.unit_id: unit for unit in proposed.units}
    unit = units_by_id.get(placement.unit_id)
    if unit is None:
        return None

    boundary = geometry_engine.boundary_to_polygon(proposed.boundary)
    minx, miny, maxx, maxy = boundary.bounds
    width = maxx - minx
    height = maxy - miny
    step_x = max(width * 0.05, 1.0)
    step_y = max(height * 0.05, 1.0)

    new_x = _clamp(placement.centroid.easting + rng.uniform(-step_x, step_x), minx, maxx)
    new_y = _clamp(placement.centroid.northing + rng.uniform(-step_y, step_y), miny, maxy)
    new_rotation = 0.0 if unit.shape_type == ShapeType.CIRCLE else rng.choice(ROTATIONS)

    proposed.placements[placement_index] = type(placement)(
        placement_id=placement.placement_id,
        unit_id=placement.unit_id,
        centroid=Coordinate(new_x, new_y, elevation=placement.centroid.elevation),
        rotation=new_rotation,
        geometry=placement.geometry,
        bounding_geometry=placement.bounding_geometry,
        occupied_area=placement.occupied_area,
        metadata=copy.deepcopy(placement.metadata),
    )

    validation = geometry_engine.validate_layout_geometry(proposed)
    if (
        validation.invalid_geometry_errors
        or validation.inside_boundary_violations
        or validation.overlap_violations
        or validation.clearance_violations
    ):
        return None
    if (proposed.site_zones or proposed.existing_structures or proposed.corridors or
            proposed.group_relationships or proposed.metadata.get("exclusion_zones") or
            any(unit.access_required and unit.access_classification == ConstraintClassification.HARD
                for unit in proposed.units)):
        if any(item.metadata.get("classification") == "hard" for item in site_violations(proposed)):
            return None
    if proposed.proximity_relationships:
        if any(item.metadata.get("classification") == "hard" for item in proximity_violations(proposed)):
            return None
    return proposed


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
