"""Flow graph entities."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .common import enum_from_value, require_id, require_non_negative
from .enums import FlowType


@dataclass
class FlowEdge:
    """Directed process or utility connection between two units."""

    flow_id: str
    source_unit_id: str
    target_unit_id: str
    flow_type: FlowType
    gravity_preferred: bool = False
    estimated_flow_rate: Optional[float] = None
    pipe_or_channel_type: Optional[str] = None
    relative_priority: float = 1.0
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_id(self.flow_id, "flow_id")
        require_id(self.source_unit_id, "source_unit_id")
        require_id(self.target_unit_id, "target_unit_id")
        if self.source_unit_id == self.target_unit_id:
            raise ValueError("FlowEdge source and target cannot be same")
        self.flow_type = enum_from_value(FlowType, self.flow_type)
        require_non_negative(self.estimated_flow_rate, "estimated_flow_rate")
        require_non_negative(self.relative_priority, "relative_priority")
        require_non_negative(self.weight, "weight")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flow_id": self.flow_id,
            "source_unit_id": self.source_unit_id,
            "target_unit_id": self.target_unit_id,
            "flow_type": self.flow_type.value,
            "gravity_preferred": self.gravity_preferred,
            "estimated_flow_rate": self.estimated_flow_rate,
            "pipe_or_channel_type": self.pipe_or_channel_type,
            "relative_priority": self.relative_priority,
            "weight": self.weight,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlowEdge":
        return cls(
            flow_id=data["flow_id"],
            source_unit_id=data["source_unit_id"],
            target_unit_id=data["target_unit_id"],
            flow_type=enum_from_value(FlowType, data["flow_type"]),
            gravity_preferred=data.get("gravity_preferred", False),
            estimated_flow_rate=data.get("estimated_flow_rate"),
            pipe_or_channel_type=data.get("pipe_or_channel_type"),
            relative_priority=data.get("relative_priority", 1.0),
            weight=data.get("weight", 1.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class FlowGraph:
    """Directed process-flow representation without graph-library dependency."""

    graph_id: str
    unit_ids: List[str] = field(default_factory=list)
    edges: List[FlowEdge] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_id(self.graph_id, "graph_id")
        for unit_id in self.unit_ids:
            require_id(unit_id, "unit_id")
        for edge in self.edges:
            if not isinstance(edge, FlowEdge):
                raise ValueError("FlowGraph edges must be FlowEdge objects")
        if self.unit_ids:
            known_unit_ids = set(self.unit_ids)
            for edge in self.edges:
                if edge.source_unit_id not in known_unit_ids:
                    raise ValueError("FlowEdge source_unit_id must exist in FlowGraph unit_ids")
                if edge.target_unit_id not in known_unit_ids:
                    raise ValueError("FlowEdge target_unit_id must exist in FlowGraph unit_ids")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "unit_ids": list(self.unit_ids),
            "edges": [edge.to_dict() for edge in self.edges],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlowGraph":
        return cls(
            graph_id=data["graph_id"],
            unit_ids=list(data.get("unit_ids", [])),
            edges=[FlowEdge.from_dict(item) for item in data.get("edges", [])],
            metadata=data.get("metadata", {}),
        )
