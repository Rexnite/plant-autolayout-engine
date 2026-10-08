"""Simple simulated annealing refinement."""

import copy
import math
import random
from typing import Tuple

from wtp_autolayout.geometry import GeometryEngine
from wtp_autolayout.scoring import ScoringEngine

from .local_search import propose_neighbor
from .errors import OptimizationError
from .result import CandidateResult


def refine_simulated_annealing(
    initial: CandidateResult,
    scoring_engine: ScoringEngine,
    geometry_engine: GeometryEngine,
    rng: random.Random,
    max_iterations: int,
    initial_temperature: float = 10.0,
    cooling_rate: float = 0.95,
) -> Tuple[object, object, int]:
    """Refine using score-higher-is-better simulated annealing."""
    if not math.isfinite(initial_temperature) or initial_temperature <= 0:
        raise OptimizationError("initial_temperature must be finite and positive")
    if not math.isfinite(cooling_rate) or not 0 < cooling_rate <= 1:
        raise OptimizationError("cooling_rate must be finite and between 0 and 1")
    current_layout = copy.deepcopy(initial.layout)
    current_score = initial.scoring_result
    best_layout = copy.deepcopy(current_layout)
    best_score = current_score
    temperature = initial_temperature
    completed = 0

    for iteration in range(max_iterations):
        completed = iteration + 1
        proposed_layout = propose_neighbor(current_layout, geometry_engine, rng)
        temperature = max(temperature * cooling_rate, 1e-9)
        if proposed_layout is None:
            continue

        proposed_score = scoring_engine.score_layout(proposed_layout)
        if not proposed_score.passed_hard_constraints:
            continue

        delta = proposed_score.score - current_score.score
        if delta >= 0 or rng.random() < math.exp(delta / temperature):
            current_layout = proposed_layout
            current_score = proposed_score
            if proposed_score.score > best_score.score:
                best_layout = copy.deepcopy(proposed_layout)
                best_score = proposed_score

    return best_layout, best_score, completed
