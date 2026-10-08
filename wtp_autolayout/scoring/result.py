"""Scoring result dataclass."""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from wtp_autolayout.models import Violation


@dataclass
class ObjectiveBreakdown:
    raw_metric: Any
    normalized_metric: float
    configured_weight: float
    effective_weight: float
    weighted_contribution: float
    penalty: float
    explanation: str

    def to_dict(self):
        return vars(self).copy()

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


@dataclass
class ScoringResult:
    """Transparent numerical summary of layout violations."""

    total_penalty: float
    hard_penalty: float
    soft_penalty: float
    violation_count: int
    hard_violation_count: int
    soft_violation_count: int
    score: float
    passed_hard_constraints: bool
    violations: List[Violation] = field(default_factory=list)
    penalty_by_constraint: Dict[str, float] = field(default_factory=dict)
    penalty_by_severity: Dict[str, float] = field(default_factory=dict)
    reward_total: float = 0.0
    reward_by_objective: Dict[str, float] = field(default_factory=dict)
    objective_breakdown: Dict[str, ObjectiveBreakdown] = field(default_factory=dict)
    base_score: float = 100.0
    weight_scale: float = 1.0

    def to_dict(self):
        return {
            "total_penalty": self.total_penalty,
            "hard_penalty": self.hard_penalty,
            "soft_penalty": self.soft_penalty,
            "violation_count": self.violation_count,
            "hard_violation_count": self.hard_violation_count,
            "soft_violation_count": self.soft_violation_count,
            "score": self.score,
            "passed_hard_constraints": self.passed_hard_constraints,
            "violations": [violation.to_dict() for violation in self.violations],
            "penalty_by_constraint": dict(self.penalty_by_constraint),
            "penalty_by_severity": dict(self.penalty_by_severity),
            "reward_total": self.reward_total,
            "reward_by_objective": dict(self.reward_by_objective),
            "objective_breakdown": {key: item.to_dict() for key, item in self.objective_breakdown.items()},
            "base_score": self.base_score,
            "weight_scale": self.weight_scale,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            total_penalty=data["total_penalty"],
            hard_penalty=data["hard_penalty"],
            soft_penalty=data["soft_penalty"],
            violation_count=data["violation_count"],
            hard_violation_count=data["hard_violation_count"],
            soft_violation_count=data["soft_violation_count"],
            score=data["score"],
            passed_hard_constraints=data["passed_hard_constraints"],
            violations=[Violation.from_dict(item) for item in data.get("violations", [])],
            penalty_by_constraint=dict(data.get("penalty_by_constraint", {})),
            penalty_by_severity=dict(data.get("penalty_by_severity", {})),
            reward_total=data.get("reward_total", 0.0),
            reward_by_objective=dict(data.get("reward_by_objective", {})),
            objective_breakdown={key: ObjectiveBreakdown.from_dict(item)
                                 for key, item in data.get("objective_breakdown", {}).items()},
            base_score=data.get("base_score", 100.0),
            weight_scale=data.get("weight_scale", 1.0),
        )
