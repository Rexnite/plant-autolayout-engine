"""Optimization orchestration for Phase 7."""

import copy
import random
import time
from typing import List, Optional

from wtp_autolayout.candidates import CandidateGenerationError, CandidateGenerator
from wtp_autolayout.geometry import GeometryEngine
from wtp_autolayout.models import Layout, LayoutMode, OptimizationStatus
from wtp_autolayout.scoring import ScoringEngine

from .annealing import refine_simulated_annealing
from .errors import OptimizationError
from .local_search import refine_local_search
from .result import CandidateResult, OptimizationRunResult


class Optimizer:
    """Generate, score, and lightly refine candidate layouts."""

    def __init__(
        self,
        candidate_generator: CandidateGenerator,
        scoring_engine: ScoringEngine,
        geometry_engine: Optional[GeometryEngine] = None,
        random_seed: Optional[int] = None,
        initial_candidate_count: int = 10,
        max_iterations: int = 100,
        mode: Optional[LayoutMode] = None,
        algorithm: str = "simulated_annealing",
    ):
        if initial_candidate_count <= 0:
            raise OptimizationError("initial_candidate_count must be positive")
        if max_iterations < 0:
            raise OptimizationError("max_iterations must be non-negative")
        self.candidate_generator = candidate_generator
        self.scoring_engine = scoring_engine
        self.geometry_engine = geometry_engine or GeometryEngine()
        self.random_seed = random_seed
        self.initial_candidate_count = initial_candidate_count
        self.max_iterations = max_iterations
        self.mode = mode
        self.algorithm = algorithm
        self._rng = random.Random(random_seed)

    def generate_ranked_candidates(
        self,
        layout: Layout,
        count: int = 5,
        mode: Optional[LayoutMode] = None,
    ) -> OptimizationRunResult:
        start = time.perf_counter()
        selected_mode = self._mode(mode)
        try:
            candidates = self.candidate_generator.generate_many(
                copy.deepcopy(layout),
                count=count,
                mode=selected_mode,
                score_generated=False,
            )
        except CandidateGenerationError as error:
            raise OptimizationError("Candidate generation failed: %s" % error)

        candidate_results = self._score_and_rank(candidates)
        status = self._status(candidate_results)
        return OptimizationRunResult(
            best_layout=candidate_results[0].layout if candidate_results else None,
            best_score_result=candidate_results[0].scoring_result if candidate_results else None,
            candidate_results=candidate_results,
            algorithm="ranked",
            iterations=0,
            runtime_seconds=time.perf_counter() - start,
            status=status,
            metadata={"algorithm": "ranked", "mode": selected_mode.value, "candidate_count": len(candidate_results)},
        )

    def optimize(
        self,
        layout: Layout,
        mode: Optional[LayoutMode] = None,
        algorithm: Optional[str] = None,
    ) -> OptimizationRunResult:
        selected_algorithm = algorithm or self.algorithm
        if selected_algorithm == "ranked":
            return self.generate_ranked_candidates(layout, count=self.initial_candidate_count, mode=mode)
        if selected_algorithm not in ("local_search", "simulated_annealing"):
            raise OptimizationError("Unsupported optimization algorithm: %s" % selected_algorithm)

        start = time.perf_counter()
        selected_mode = self._mode(mode)
        try:
            candidates = self.candidate_generator.generate_many(
                copy.deepcopy(layout),
                count=self.initial_candidate_count,
                mode=selected_mode,
                score_generated=False,
            )
        except CandidateGenerationError as error:
            raise OptimizationError("Candidate generation failed: %s" % error)

        candidate_results = self._score_and_rank(candidates)
        if not candidate_results:
            raise OptimizationError("No scored candidates were generated")

        initial_best = self._best_feasible(candidate_results) or candidate_results[0]
        if selected_algorithm == "local_search":
            best_layout, best_score, iterations = refine_local_search(
                initial_best,
                self.scoring_engine,
                self.geometry_engine,
                self._rng,
                self.max_iterations,
            )
        else:
            best_layout, best_score, iterations = refine_simulated_annealing(
                initial_best,
                self.scoring_engine,
                self.geometry_engine,
                self._rng,
                self.max_iterations,
            )

        refined = CandidateResult(layout=best_layout, scoring_result=best_score, rank=1)
        all_results = self._rerank([refined] + candidate_results)
        status = self._status(all_results)
        return OptimizationRunResult(
            best_layout=all_results[0].layout,
            best_score_result=all_results[0].scoring_result,
            candidate_results=all_results,
            algorithm=selected_algorithm,
            iterations=iterations,
            runtime_seconds=time.perf_counter() - start,
            status=status,
            metadata={
                "algorithm": selected_algorithm,
                "mode": selected_mode.value,
                "initial_candidate_count": self.initial_candidate_count,
                "max_iterations": self.max_iterations,
            },
        )

    def _score_and_rank(self, layouts: List[Layout]) -> List[CandidateResult]:
        return self._rerank(
            [CandidateResult(layout=layout, scoring_result=self.scoring_engine.score_layout(layout), rank=0) for layout in layouts]
        )

    def _rerank(self, candidate_results: List[CandidateResult]) -> List[CandidateResult]:
        ranked = sorted(candidate_results,
                        key=lambda item: (item.scoring_result.passed_hard_constraints,
                                          item.scoring_result.score), reverse=True)
        return [
            CandidateResult(layout=result.layout, scoring_result=result.scoring_result, rank=index)
            for index, result in enumerate(ranked, start=1)
        ]

    def _best_feasible(self, candidate_results: List[CandidateResult]) -> Optional[CandidateResult]:
        for result in candidate_results:
            if result.scoring_result.passed_hard_constraints:
                return result
        return None

    def _status(self, candidate_results: List[CandidateResult]) -> OptimizationStatus:
        if not candidate_results:
            return OptimizationStatus.FAILED
        if candidate_results[0].scoring_result.passed_hard_constraints:
            return OptimizationStatus.SUCCESSFUL
        return OptimizationStatus.PARTIAL

    def _mode(self, mode: Optional[LayoutMode]) -> LayoutMode:
        value = mode or self.mode or LayoutMode.BALANCED
        if isinstance(value, LayoutMode):
            return value
        return LayoutMode(value)
