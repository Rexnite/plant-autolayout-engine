"""Penalty and engineering reward calculation for plant layouts."""

import math
from typing import Dict, Iterable, List, Optional, Tuple

from wtp_autolayout.constraints import ConstraintEngine
from wtp_autolayout.models import (
    Constraint,
    ConstraintClassification,
    Layout,
    LayoutStatistics,
    Violation,
)

from .errors import ScoringError
from .objectives import EngineeringObjectiveCalculator
from .result import ObjectiveBreakdown, ScoringResult
from .rewards import DEFAULT_OBJECTIVE_WEIGHTS, ENGINEERING_BASE_SCORE, MAX_ENGINEERING_REWARD
from wtp_autolayout.objective_ids import SUPPORTED_OBJECTIVES
from .weights import DEFAULT_CONSTRAINT_WEIGHTS, DEFAULT_HARD_CONSTRAINT_IDS
from wtp_autolayout.profiles import get_plant_profile


class ScoringEngine:
    """Convert constraint violations into a numerical layout score."""

    def __init__(
        self,
        constraint_engine: Optional[ConstraintEngine] = None,
        weight_overrides: Optional[Dict[str, float]] = None,
        objective_calculator: Optional[EngineeringObjectiveCalculator] = None,
        reward_weight_overrides: Optional[Dict[str, float]] = None,
        enable_engineering_rewards: bool = True,
    ):
        self.constraint_engine = constraint_engine
        self.weights = dict(DEFAULT_CONSTRAINT_WEIGHTS)
        if weight_overrides:
            self.weights.update(weight_overrides)
        self.reward_weights = dict(DEFAULT_OBJECTIVE_WEIGHTS)
        self._reward_overrides = dict(reward_weight_overrides or {})
        if reward_weight_overrides:
            self.reward_weights.update(reward_weight_overrides)
        self.objective_calculator = objective_calculator or EngineeringObjectiveCalculator()
        self.enable_engineering_rewards = enable_engineering_rewards
        self._validate_weights()

    def score_layout(self, layout: Layout, update_layout: bool = False) -> ScoringResult:
        if self.constraint_engine is not None:
            violations = self.constraint_engine.evaluate(layout)
            constraints = self.constraint_engine.constraints
        else:
            violations = list(layout.violations)
            constraints = layout.constraints
        result = self.score_violations(violations, constraints=constraints)
        if self.enable_engineering_rewards:
            result = self._apply_engineering_rewards(layout, result)
        if update_layout:
            self._update_layout(layout, result)
        return result

    def score_violations(
        self,
        violations: Iterable[Violation],
        constraints: Optional[Iterable[Constraint]] = None,
    ) -> ScoringResult:
        violation_list = list(violations)
        classification_by_constraint = self._classification_map(constraints)

        hard_penalty = 0.0
        soft_penalty = 0.0
        hard_violation_count = 0
        soft_violation_count = 0
        penalty_by_constraint: Dict[str, float] = {}
        penalty_by_severity: Dict[str, float] = {}

        for violation in violation_list:
            weight = self.weights.get(violation.constraint_id, 1.0)
            weighted_penalty = violation.penalty * weight
            if not math.isfinite(weighted_penalty):
                raise ScoringError("Weighted penalty overflow for constraint %s; reduce its penalty or weight."
                                   % violation.constraint_id)
            classification = classification_by_constraint.get(
                violation.constraint_id,
                ConstraintClassification(violation.metadata["classification"])
                if violation.metadata.get("classification") else self._fallback_classification(violation.constraint_id),
            )

            if classification == ConstraintClassification.HARD:
                hard_penalty += weighted_penalty
                hard_violation_count += 1
            else:
                soft_penalty += weighted_penalty
                soft_violation_count += 1

            penalty_by_constraint[violation.constraint_id] = (
                penalty_by_constraint.get(violation.constraint_id, 0.0) + weighted_penalty
            )
            severity_key = violation.severity.value
            penalty_by_severity[severity_key] = penalty_by_severity.get(severity_key, 0.0) + weighted_penalty

        total_penalty = hard_penalty + soft_penalty
        if not math.isfinite(total_penalty):
            raise ScoringError("Total penalty overflow; reduce penalty weights or input distances.")
        normalized_penalty = total_penalty
        score = max(0.0, 100.0 - normalized_penalty)

        return ScoringResult(
            total_penalty=total_penalty,
            hard_penalty=hard_penalty,
            soft_penalty=soft_penalty,
            violation_count=len(violation_list),
            hard_violation_count=hard_violation_count,
            soft_violation_count=soft_violation_count,
            score=score,
            passed_hard_constraints=hard_violation_count == 0,
            violations=violation_list,
            penalty_by_constraint=penalty_by_constraint,
            penalty_by_severity=penalty_by_severity,
        )

    def rank_layouts(
        self,
        layouts: Iterable[Layout],
        update_layout: bool = False,
    ) -> List[Tuple[Layout, ScoringResult]]:
        ranked = [(layout, self.score_layout(layout, update_layout=update_layout)) for layout in layouts]
        ranked.sort(key=lambda item: item[1].score, reverse=True)
        return ranked

    def _validate_weights(self) -> None:
        for constraint_id, weight in self.weights.items():
            if not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight < 0:
                raise ScoringError("Scoring weight for %s must be non-negative" % constraint_id)
        for objective_id, weight in self.reward_weights.items():
            if objective_id not in SUPPORTED_OBJECTIVES:
                raise ScoringError("Unknown engineering objective %s" % objective_id)
            if not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight < 0:
                raise ScoringError("Reward weight for %s must be non-negative" % objective_id)

    def _classification_map(self, constraints: Optional[Iterable[Constraint]]) -> Dict[str, ConstraintClassification]:
        mapping: Dict[str, ConstraintClassification] = {}
        if constraints is None:
            return mapping
        for constraint in constraints:
            mapping[constraint.constraint_id] = constraint.classification
        return mapping

    def _fallback_classification(self, constraint_id: str) -> ConstraintClassification:
        if constraint_id in DEFAULT_HARD_CONSTRAINT_IDS:
            return ConstraintClassification.HARD
        return ConstraintClassification.SOFT

    def _update_layout(self, layout: Layout, result: ScoringResult) -> None:
        layout.optimization_score = result.score
        layout.violations = list(result.violations)
        if layout.statistics is None:
            layout.statistics = LayoutStatistics()
        layout.statistics.total_penalty = result.total_penalty
        layout.statistics.number_of_violations = result.violation_count
        layout.statistics.constraint_satisfaction_percentage = 100.0 if result.violation_count == 0 else result.score
        layout.statistics.metadata["reward_by_objective"] = dict(result.reward_by_objective)
        layout.statistics.metadata["hard_violation_count"] = result.hard_violation_count
        layout.statistics.metadata["soft_violation_count"] = result.soft_violation_count
        layout.statistics.metadata["score_breakdown"] = result.to_dict()

    def _apply_engineering_rewards(self, layout: Layout, result: ScoringResult) -> ScoringResult:
        profile = get_plant_profile(layout.plant_type)
        weights = dict(profile.objective_weights)
        weights.update(self._reward_overrides)
        for name, weight in weights.items():
            if not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight < 0:
                raise ScoringError("Reward weight for %s must be non-negative" % name)
        weight_total = sum(weights.values())
        scale = min(1.0, MAX_ENGINEERING_REWARD / weight_total) if weight_total else 1.0
        active = {name for name, weight in weights.items() if weight > 0}
        normalized_rewards = self.objective_calculator.calculate_all(layout, selected=active)
        reward_by_objective = {
            objective_id: normalized_rewards.get(objective_id, 0.0) * weight * scale
            for objective_id, weight in weights.items()
        }
        reward_total = sum(reward_by_objective.values())
        raw = self.objective_calculator.raw_metrics(layout, selected=active)
        explanations = self.objective_calculator.explanations()
        breakdown = {name: ObjectiveBreakdown(raw_metric=raw.get(name),
                     normalized_metric=normalized_rewards.get(name, 0.0),
                     configured_weight=weight, effective_weight=weight * scale,
                     weighted_contribution=reward_by_objective[name], penalty=0.0,
                     explanation=explanations.get(name, "Engineering quality metric."))
                     for name, weight in weights.items()}
        score = max(0.0, min(100.0, ENGINEERING_BASE_SCORE - result.total_penalty + reward_total))
        return ScoringResult(
            total_penalty=result.total_penalty,
            hard_penalty=result.hard_penalty,
            soft_penalty=result.soft_penalty,
            violation_count=result.violation_count,
            hard_violation_count=result.hard_violation_count,
            soft_violation_count=result.soft_violation_count,
            score=score,
            passed_hard_constraints=result.passed_hard_constraints,
            violations=result.violations,
            penalty_by_constraint=result.penalty_by_constraint,
            penalty_by_severity=result.penalty_by_severity,
            reward_total=reward_total,
            reward_by_objective=reward_by_objective,
            objective_breakdown=breakdown,
            base_score=ENGINEERING_BASE_SCORE,
            weight_scale=scale,
        )
