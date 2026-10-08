"""Layout entities."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .boundary import Boundary
from .common import enum_from_value, require_id, require_non_negative, require_non_negative_int
from .constraint import Constraint
from .engineering_unit import EngineeringUnit
from .enums import LayoutMode, PlantType, SpatialRelationshipType
from .flow import FlowGraph
from .infrastructure import Drain, Road
from .group_relationship import GroupRelationship, GroupRelationshipType
from .site import Corridor, ExistingStructure, SiteZone
from .placement import Placement
from .spatial_relationship import SpatialRelationship
from .system_group import SystemGroup
from .violation import Violation


@dataclass
class LayoutStatistics:
    """Numerical indicators for comparing candidate layouts."""

    total_pipeline_length: Optional[float] = None
    total_occupied_area: Optional[float] = None
    remaining_free_land: Optional[float] = None
    number_of_violations: int = 0
    total_penalty: float = 0.0
    gravity_compliance: Optional[float] = None
    road_coverage: Optional[float] = None
    drainage_coverage: Optional[float] = None
    constraint_satisfaction_percentage: Optional[float] = None
    runtime: Optional[float] = None
    optimization_iterations: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_negative(self.total_pipeline_length, "total_pipeline_length")
        require_non_negative(self.total_occupied_area, "total_occupied_area")
        require_non_negative(self.remaining_free_land, "remaining_free_land")
        require_non_negative_int(self.number_of_violations, "number_of_violations")
        require_non_negative(self.total_penalty, "total_penalty")
        require_non_negative(self.gravity_compliance, "gravity_compliance")
        require_non_negative(self.road_coverage, "road_coverage")
        require_non_negative(self.drainage_coverage, "drainage_coverage")
        require_non_negative(self.constraint_satisfaction_percentage, "constraint_satisfaction_percentage")
        require_non_negative(self.runtime, "runtime")
        require_non_negative_int(self.optimization_iterations, "optimization_iterations")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_pipeline_length": self.total_pipeline_length,
            "total_occupied_area": self.total_occupied_area,
            "remaining_free_land": self.remaining_free_land,
            "number_of_violations": self.number_of_violations,
            "total_penalty": self.total_penalty,
            "gravity_compliance": self.gravity_compliance,
            "road_coverage": self.road_coverage,
            "drainage_coverage": self.drainage_coverage,
            "constraint_satisfaction_percentage": self.constraint_satisfaction_percentage,
            "runtime": self.runtime,
            "optimization_iterations": self.optimization_iterations,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LayoutStatistics":
        return cls(
            total_pipeline_length=data.get("total_pipeline_length"),
            total_occupied_area=data.get("total_occupied_area"),
            remaining_free_land=data.get("remaining_free_land"),
            number_of_violations=data.get("number_of_violations", 0),
            total_penalty=data.get("total_penalty", 0.0),
            gravity_compliance=data.get("gravity_compliance"),
            road_coverage=data.get("road_coverage"),
            drainage_coverage=data.get("drainage_coverage"),
            constraint_satisfaction_percentage=data.get("constraint_satisfaction_percentage"),
            runtime=data.get("runtime"),
            optimization_iterations=data.get("optimization_iterations"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Layout:
    """Complete candidate treatment plant layout."""

    layout_id: str
    boundary: Boundary
    units: List[EngineeringUnit] = field(default_factory=list)
    placements: List[Placement] = field(default_factory=list)
    flow_graph: Optional[FlowGraph] = None
    roads: List[Road] = field(default_factory=list)
    drains: List[Drain] = field(default_factory=list)
    constraints: List[Constraint] = field(default_factory=list)
    violations: List[Violation] = field(default_factory=list)
    statistics: Optional[LayoutStatistics] = None
    optimization_score: Optional[float] = None
    layout_mode: Optional[LayoutMode] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    plant_type: PlantType = PlantType.WTP
    system_groups: List[SystemGroup] = field(default_factory=list)
    proximity_relationships: List[SpatialRelationship] = field(default_factory=list)
    site_zones: List[SiteZone] = field(default_factory=list)
    existing_structures: List[ExistingStructure] = field(default_factory=list)
    corridors: List[Corridor] = field(default_factory=list)
    group_relationships: List[GroupRelationship] = field(default_factory=list)

    def __post_init__(self) -> None:
        require_id(self.layout_id, "layout_id")
        require_non_negative(self.optimization_score, "optimization_score")
        if self.layout_mode is not None:
            self.layout_mode = enum_from_value(LayoutMode, self.layout_mode)
        self.plant_type = enum_from_value(PlantType, self.plant_type)
        group_ids = [group.group_id for group in self.system_groups]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("duplicate system group ID")
        for label, values in (("site zone", [item.zone_id for item in self.site_zones]),
                              ("existing structure", [item.structure_id for item in self.existing_structures]),
                              ("corridor", [item.corridor_id for item in self.corridors]),
                              ("group relationship", [item.relationship_id for item in self.group_relationships])):
            if len(values) != len(set(values)):
                raise ValueError("duplicate %s ID" % label)
        for item in self.group_relationships:
            if item.group_id_a not in group_ids or item.group_id_b not in group_ids:
                raise ValueError("group relationship %s references unknown group" % item.relationship_id)
        group_seen = set()
        group_bounds = {}
        for item in self.group_relationships:
            pair = frozenset((item.group_id_a, item.group_id_b))
            key = (pair, item.relationship_type)
            if key in group_seen:
                raise ValueError("duplicate group relationship for %s" % sorted(pair))
            group_seen.add(key)
            group_bounds.setdefault(pair, {})[item.relationship_type] = item.distance
        for pair, bounds in group_bounds.items():
            minimum = bounds.get(GroupRelationshipType.MIN_DISTANCE)
            maximum = bounds.get(GroupRelationshipType.MAX_DISTANCE)
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError("conflicting group distances for %s" % sorted(pair))
        unit_ids = {unit.unit_id for unit in self.units}
        for unit in self.units:
            if self.system_groups and unit.system_group and unit.system_group not in group_ids:
                raise ValueError("unit %s references unknown system group %s" % (unit.unit_id, unit.system_group))
        seen = set()
        relationship_ids = set()
        bounds_by_pair = {}
        hard_bounds_by_pair = {}
        for relationship in self.proximity_relationships:
            if relationship.relationship_id in relationship_ids:
                raise ValueError("duplicate relationship ID %s" % relationship.relationship_id)
            relationship_ids.add(relationship.relationship_id)
            if relationship.unit_id_a not in unit_ids or relationship.unit_id_b not in unit_ids:
                raise ValueError("relationship %s references unknown unit" % relationship.relationship_id)
            key = (frozenset((relationship.unit_id_a, relationship.unit_id_b)), relationship.relationship_type)
            if key in seen:
                raise ValueError("duplicate relationship for %s and %s" % (relationship.unit_id_a, relationship.unit_id_b))
            seen.add(key)
            bounds_by_pair.setdefault(key[0], {})[relationship.relationship_type] = relationship.distance
            if relationship.classification.value == "hard":
                hard_bounds_by_pair.setdefault(key[0], {})[relationship.relationship_type] = relationship.distance
        for pair, bounds in bounds_by_pair.items():
            minimum = bounds.get(SpatialRelationshipType.MIN_DISTANCE)
            maximum = bounds.get(SpatialRelationshipType.MAX_DISTANCE)
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError("conflicting minimum and maximum distance for %s" % sorted(pair))
        for pair, bounds in hard_bounds_by_pair.items():
            target = bounds.get(SpatialRelationshipType.TARGET_DISTANCE)
            if target is not None and (target < bounds.get(SpatialRelationshipType.MIN_DISTANCE, 0.0)
                                       or target > bounds.get(SpatialRelationshipType.MAX_DISTANCE, float("inf"))):
                raise ValueError("conflicting hard target distance for %s" % sorted(pair))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layout_id": self.layout_id,
            "boundary": self.boundary.to_dict(),
            "units": [unit.to_dict() for unit in self.units],
            "placements": [placement.to_dict() for placement in self.placements],
            "flow_graph": self.flow_graph.to_dict() if self.flow_graph else None,
            "roads": [road.to_dict() for road in self.roads],
            "drains": [drain.to_dict() for drain in self.drains],
            "constraints": [constraint.to_dict() for constraint in self.constraints],
            "violations": [violation.to_dict() for violation in self.violations],
            "statistics": self.statistics.to_dict() if self.statistics else None,
            "optimization_score": self.optimization_score,
            "layout_mode": self.layout_mode.value if self.layout_mode else None,
            "metadata": self.metadata,
            "plant_type": self.plant_type.value,
            "system_groups": [group.to_dict() for group in self.system_groups],
            "proximity_relationships": [item.to_dict() for item in self.proximity_relationships],
            "site_zones": [item.to_dict() for item in self.site_zones],
            "existing_structures": [item.to_dict() for item in self.existing_structures],
            "corridors": [item.to_dict() for item in self.corridors],
            "group_relationships": [item.to_dict() for item in self.group_relationships],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Layout":
        return cls(
            layout_id=data["layout_id"],
            boundary=Boundary.from_dict(data["boundary"]),
            units=[EngineeringUnit.from_dict(item) for item in data.get("units", [])],
            placements=[Placement.from_dict(item) for item in data.get("placements", [])],
            flow_graph=FlowGraph.from_dict(data["flow_graph"]) if data.get("flow_graph") else None,
            roads=[Road.from_dict(item) for item in data.get("roads", [])],
            drains=[Drain.from_dict(item) for item in data.get("drains", [])],
            constraints=[Constraint.from_dict(item) for item in data.get("constraints", [])],
            violations=[Violation.from_dict(item) for item in data.get("violations", [])],
            statistics=LayoutStatistics.from_dict(data["statistics"]) if data.get("statistics") else None,
            optimization_score=data.get("optimization_score"),
            layout_mode=enum_from_value(LayoutMode, data["layout_mode"]) if data.get("layout_mode") else None,
            metadata=data.get("metadata", {}),
            plant_type=data.get("plant_type", "wtp"),
            system_groups=[SystemGroup.from_dict(item) for item in data.get("system_groups", [])],
            proximity_relationships=[SpatialRelationship.from_dict(item) for item in data.get("proximity_relationships", [])],
            site_zones=[SiteZone.from_dict(item) for item in data.get("site_zones", [])],
            existing_structures=[ExistingStructure.from_dict(item) for item in data.get("existing_structures", [])],
            corridors=[Corridor.from_dict(item) for item in data.get("corridors", [])],
            group_relationships=[GroupRelationship.from_dict(item) for item in data.get("group_relationships", [])],
        )
