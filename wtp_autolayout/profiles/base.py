"""Profile registry; engineering rules stay outside the shared algorithms."""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple

from wtp_autolayout.models import EngineeringUnit, PlantType, SystemGroup
from wtp_autolayout.objective_ids import SUPPORTED_OBJECTIVES


@dataclass(frozen=True)
class PlantProfile:
    plant_type: PlantType
    display_name: str
    suggested_groups: Tuple[Tuple[str, str, float], ...]
    objective_weights: Dict[str, float] = field(default_factory=dict)
    use_wtp_constraints: bool = False
    use_wtp_knowledge: bool = False
    unit_templates: Tuple[Dict[str, object], ...] = ()
    group_preferences: Dict[str, str] = field(default_factory=dict)
    scoring_config: Dict[str, float] = field(default_factory=dict)
    suggested_relationships: Tuple[Tuple[str, str, str, float], ...] = ()
    process_flow_priority: float = 1.0

    def __post_init__(self) -> None:
        for name, value in self.objective_weights.items():
            if name not in SUPPORTED_OBJECTIVES:
                raise ValueError("unknown objective %s" % name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("invalid objective weight %s" % name)
        for name, value in self.scoring_config.items():
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("invalid scoring config %s" % name)
        if not math.isfinite(self.process_flow_priority) or self.process_flow_priority < 0:
            raise ValueError("process_flow_priority must be non-negative")
        allowed = {"strongly_clustered", "loosely_clustered", "neutral"}
        if any(value not in allowed for value in self.group_preferences.values()):
            raise ValueError("invalid group preference")

    def default_groups(self) -> List[SystemGroup]:
        return [SystemGroup(*group, preference=self.group_preferences.get(group[0], "loosely_clustered"))
                for group in self.suggested_groups]

    def default_units(self) -> List[EngineeringUnit]:
        return [EngineeringUnit.from_dict(dict(item)) for item in self.unit_templates]

    def inferred_group(self, unit: EngineeringUnit) -> Optional[str]:
        if not self.use_wtp_knowledge:
            return unit.system_group
        from wtp_autolayout.knowledge import get_cluster
        return unit.system_group or get_cluster(unit)

    def relationship(self, unit_a: EngineeringUnit, unit_b: EngineeringUnit) -> Optional[str]:
        if not self.use_wtp_knowledge:
            return None
        from wtp_autolayout.knowledge import get_relationship
        return get_relationship(unit_a, unit_b)

    def preferred_distance(self, relationship: Optional[str]) -> float:
        if not self.use_wtp_knowledge:
            return 45.0
        from wtp_autolayout.knowledge import get_preferred_distance
        return get_preferred_distance(relationship)

    def constraint_engine(self):
        from wtp_autolayout.constraints.engine import default_core_engine, default_wtp_engine
        return default_wtp_engine() if self.use_wtp_constraints else default_core_engine()


_PROFILES = {
    PlantType.WTP: PlantProfile(
        PlantType.WTP, "Water Treatment Plant",
        (("hydraulic", "Hydraulic Process", 45.0), ("sludge", "Sludge Handling", 55.0),
         ("chemical", "Chemical", 80.0), ("clear_water", "Clear Water", 50.0)),
        {"pipe_efficiency": 9.0, "gravity": 5.0, "cluster": 4.0,
         "group_arrangement": 5.0, "proximity": 5.0, "flow_crossing": 3.0,
         "compactness": 2.0, "expansion": 2.0}, True, True,
        (
            {"unit_id": "raw_water_inlet", "name": "Raw Water Inlet", "category": "process", "shape_type": "rectangle", "width": 12, "length": 10, "system_group": "hydraulic", "process_order": 1},
            {"unit_id": "flash_mixer", "name": "Flash Mixer", "category": "process", "shape_type": "rectangle", "width": 10, "length": 10, "system_group": "hydraulic", "process_order": 2},
            {"unit_id": "clarifier", "name": "Clarifier", "category": "process", "shape_type": "circle", "diameter": 24, "system_group": "hydraulic", "process_order": 3},
        ),
        group_preferences={"hydraulic": "strongly_clustered", "sludge": "strongly_clustered",
                           "chemical": "neutral", "clear_water": "loosely_clustered"},
        scoring_config={"pipe_distance_fraction": 0.25, "expansion_free_target": 0.35,
                        "expansion_zone_x_min": 0.58, "expansion_zone_y_min": 0.12,
                        "expansion_zone_y_max": 0.62},
        suggested_relationships=(("flash_mixer", "clarifier", "preferred_near", 45.0),),
    ),
    PlantType.PETROCHEMICAL: PlantProfile(
        PlantType.PETROCHEMICAL, "Petrochemical Plant",
        (("feed", "Feed Handling", 55.0), ("process", "Main Process", 55.0),
         ("storage", "Storage", 70.0), ("utilities", "Utilities", 70.0)),
        {"pipe_efficiency": 8.0, "gravity": 0.0, "cluster": 0.0,
         "group_arrangement": 9.0, "proximity": 9.0, "flow_crossing": 5.0,
         "compactness": 2.0, "expansion": 2.0}, False, False,
        (
            {"unit_id": "feed_pump", "name": "Feed Pump", "category": "process", "shape_type": "rectangle", "width": 12, "length": 10, "system_group": "feed", "process_order": 1},
            {"unit_id": "process_skid", "name": "Process Skid", "category": "process", "shape_type": "rectangle", "width": 24, "length": 18, "system_group": "process", "process_order": 2},
            {"unit_id": "product_tank", "name": "Product Tank", "category": "process", "shape_type": "circle", "diameter": 24, "system_group": "storage", "process_order": 3},
        ),
        group_preferences={"feed": "loosely_clustered", "process": "loosely_clustered",
                           "storage": "neutral", "utilities": "neutral"},
        scoring_config={"pipe_distance_fraction": 0.25, "expansion_free_target": 0.35},
    ),
}


def get_plant_profile(plant_type: PlantType) -> PlantProfile:
    return _PROFILES[PlantType(plant_type)]
