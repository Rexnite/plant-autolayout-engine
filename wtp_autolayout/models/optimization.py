"""Optimization result entity."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .common import enum_from_value, require_id, require_non_negative, require_non_negative_int
from .enums import LayoutMode, OptimizationStatus
from .layout import Layout


@dataclass
class OptimizationResult:
    """Output metadata for one optimization execution."""

    result_id: str
    algorithm: str
    runtime: float
    iterations: int
    status: OptimizationStatus
    best_layout: Optional[Layout] = None
    candidate_layouts: List[Layout] = field(default_factory=list)
    candidate_count: int = 0
    final_score: Optional[float] = None
    layout_mode: Optional[LayoutMode] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_id(self.result_id, "result_id")
        if not isinstance(self.algorithm, str) or not self.algorithm.strip():
            raise ValueError("algorithm is required")
        self.status = enum_from_value(OptimizationStatus, self.status)
        if self.layout_mode is not None:
            self.layout_mode = enum_from_value(LayoutMode, self.layout_mode)
        require_non_negative(self.runtime, "runtime")
        require_non_negative_int(self.iterations, "iterations")
        require_non_negative_int(self.candidate_count, "candidate_count")
        require_non_negative(self.final_score, "final_score")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id,
            "algorithm": self.algorithm,
            "runtime": self.runtime,
            "iterations": self.iterations,
            "status": self.status.value,
            "best_layout": self.best_layout.to_dict() if self.best_layout else None,
            "candidate_layouts": [layout.to_dict() for layout in self.candidate_layouts],
            "candidate_count": self.candidate_count,
            "final_score": self.final_score,
            "layout_mode": self.layout_mode.value if self.layout_mode else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OptimizationResult":
        return cls(
            result_id=data["result_id"],
            algorithm=data["algorithm"],
            runtime=data["runtime"],
            iterations=data["iterations"],
            status=enum_from_value(OptimizationStatus, data["status"]),
            best_layout=Layout.from_dict(data["best_layout"]) if data.get("best_layout") else None,
            candidate_layouts=[Layout.from_dict(item) for item in data.get("candidate_layouts", [])],
            candidate_count=data.get("candidate_count", 0),
            final_score=data.get("final_score"),
            layout_mode=enum_from_value(LayoutMode, data["layout_mode"]) if data.get("layout_mode") else None,
            metadata=data.get("metadata", {}),
        )
