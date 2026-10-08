"""Runtime optimization result objects."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from wtp_autolayout.models import Layout, OptimizationStatus
from wtp_autolayout.scoring import ScoringResult


@dataclass
class CandidateResult:
    """Scored candidate layout with rank."""

    layout: Layout
    scoring_result: ScoringResult
    rank: int


@dataclass
class OptimizationRunResult:
    """Runtime result for one optimization execution."""

    best_layout: Optional[Layout]
    best_score_result: Optional[ScoringResult]
    candidate_results: List[CandidateResult] = field(default_factory=list)
    algorithm: str = "ranked"
    iterations: int = 0
    runtime_seconds: float = 0.0
    status: OptimizationStatus = OptimizationStatus.FAILED
    metadata: Dict[str, Any] = field(default_factory=dict)
