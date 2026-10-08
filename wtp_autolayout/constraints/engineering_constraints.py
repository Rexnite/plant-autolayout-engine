"""Engineering constraints and WTP unit classification heuristics."""

from typing import Dict, Iterable, List, Tuple

from shapely.geometry import Point

from wtp_autolayout.models import (
    ConstraintClassification,
    ConstraintType,
    EngineeringUnit,
    Layout,
    Placement,
    Severity,
    UnitCategory,
    Violation,
)

from .base import BaseConstraint


def _text(unit: EngineeringUnit) -> str:
    return " ".join([unit.name or "", unit.system_group or ""]).lower()


def _contains_any(text: str, words: Iterable[str]) -> bool:
    return any(word in text for word in words)


def is_sludge_unit(unit: EngineeringUnit) -> bool:
    text = _text(unit)
    return unit.category == UnitCategory.SLUDGE or _contains_any(text, ("sludge", "thickener", "dewatering", "centrifuge"))


def is_chemical_unit(unit: EngineeringUnit) -> bool:
    text = _text(unit)
    return unit.category == UnitCategory.CHEMICAL or _contains_any(text, ("chemical", "chlorine", "alum", "lime", "dosing"))


def is_residential_or_admin_unit(unit: EngineeringUnit) -> bool:
    text = _text(unit)
    return unit.category in (UnitCategory.RESIDENTIAL, UnitCategory.HUMAN_OCCUPANCY) or _contains_any(
        text, ("admin", "administration", "residential", "quarters", "staff", "office", "laboratory", "lab")
    )


def is_clear_water_unit(unit: EngineeringUnit) -> bool:
    text = _text(unit)
    return unit.category == UnitCategory.CLEAN_WATER or _contains_any(text, ("clear water", "treated_water", "treated water", "reservoir"))


def _unit_maps(layout: Layout) -> Tuple[Dict[str, EngineeringUnit], Dict[str, Placement]]:
    return ({unit.unit_id: unit for unit in layout.units}, {placement.unit_id: placement for placement in layout.placements})


def _point(placement: Placement) -> Point:
    return Point(placement.centroid.easting, placement.centroid.northing)


def _location_between(placement_a: Placement, placement_b: Placement):
    return {
        "type": "Point",
        "coordinates": [
            (placement_a.centroid.easting + placement_b.centroid.easting) / 2.0,
            (placement_a.centroid.northing + placement_b.centroid.northing) / 2.0,
        ],
    }


class DistanceSeparationConstraint(BaseConstraint):
    """Base for centroid-distance engineering separation rules."""

    minimum_distance: float = 0.0

    def _distance(self, placement_a: Placement, placement_b: Placement) -> float:
        return float(_point(placement_a).distance(_point(placement_b)))

    def _pair_violations(
        self,
        pairs: Iterable[Tuple[EngineeringUnit, EngineeringUnit]],
        placements_by_id: Dict[str, Placement],
        description_template: str,
        action: str,
    ) -> List[Violation]:
        violations = []
        for unit_a, unit_b in pairs:
            placement_a = placements_by_id.get(unit_a.unit_id)
            placement_b = placements_by_id.get(unit_b.unit_id)
            if placement_a is None or placement_b is None:
                continue
            distance = self._distance(placement_a, placement_b)
            if distance < self.minimum_distance:
                shortfall = self.minimum_distance - distance
                violations.append(
                    self._violation(
                        suffix=str(len(violations) + 1),
                        affected_units=[unit_a.unit_id, unit_b.unit_id],
                        penalty=shortfall,
                        description=description_template % (unit_a.unit_id, unit_b.unit_id, distance, self.minimum_distance),
                        suggested_action=action,
                        location=_location_between(placement_a, placement_b),
                    )
                )
        return violations


class SludgeIsolationConstraint(DistanceSeparationConstraint):
    def __init__(self, minimum_distance: float = 30.0, enabled: bool = True):
        self.minimum_distance = minimum_distance
        super().__init__(
            constraint_id="C-009",
            name="Sludge Isolation",
            constraint_type=ConstraintType.SLUDGE,
            classification=ConstraintClassification.SOFT,
            severity=Severity.HIGH,
            weight=1.0,
            enabled=enabled,
            description="Sludge units should be separated from occupied and clean-water units.",
        )

    def evaluate_with_context(self, layout: Layout, context=None) -> List[Violation]:
        units_by_id, placements_by_id = _unit_maps(layout)
        sludge_units = [unit for unit in units_by_id.values() if is_sludge_unit(unit)]
        protected_units = [unit for unit in units_by_id.values() if is_residential_or_admin_unit(unit) or is_clear_water_unit(unit)]
        return self._pair_violations(
            ((sludge, protected) for sludge in sludge_units for protected in protected_units if sludge.unit_id != protected.unit_id),
            placements_by_id,
            "Sludge unit %s is too close to protected unit %s: %.2f m; minimum is %.2f m.",
            "Move sludge facilities farther from occupied and clean-water areas.",
        )


class ChemicalSafetyConstraint(DistanceSeparationConstraint):
    def __init__(self, minimum_distance: float = 25.0, enabled: bool = True):
        self.minimum_distance = minimum_distance
        super().__init__(
            constraint_id="C-010",
            name="Chemical Safety",
            constraint_type=ConstraintType.CHEMICAL,
            classification=ConstraintClassification.SOFT,
            severity=Severity.HIGH,
            weight=1.0,
            enabled=enabled,
            description="Chemical units should be separated from occupied units.",
        )

    def evaluate_with_context(self, layout: Layout, context=None) -> List[Violation]:
        units_by_id, placements_by_id = _unit_maps(layout)
        chemical_units = [unit for unit in units_by_id.values() if is_chemical_unit(unit)]
        occupied_units = [unit for unit in units_by_id.values() if is_residential_or_admin_unit(unit)]
        return self._pair_violations(
            ((chemical, occupied) for chemical in chemical_units for occupied in occupied_units if chemical.unit_id != occupied.unit_id),
            placements_by_id,
            "Chemical unit %s is too close to occupied unit %s: %.2f m; minimum is %.2f m.",
            "Move chemical facilities farther from occupied areas.",
        )


class ResidentialSeparationConstraint(DistanceSeparationConstraint):
    def __init__(self, minimum_distance: float = 30.0, enabled: bool = True):
        self.minimum_distance = minimum_distance
        super().__init__(
            constraint_id="C-011",
            name="Residential Separation",
            constraint_type=ConstraintType.RESIDENTIAL,
            classification=ConstraintClassification.SOFT,
            severity=Severity.HIGH,
            weight=1.0,
            enabled=enabled,
            description="Residential and administrative units should be separated from sludge and chemical units.",
        )

    def evaluate_with_context(self, layout: Layout, context=None) -> List[Violation]:
        units_by_id, placements_by_id = _unit_maps(layout)
        occupied_units = [unit for unit in units_by_id.values() if is_residential_or_admin_unit(unit)]
        risk_units = [unit for unit in units_by_id.values() if is_sludge_unit(unit) or is_chemical_unit(unit)]
        return self._pair_violations(
            ((occupied, risk) for occupied in occupied_units for risk in risk_units if occupied.unit_id != risk.unit_id),
            placements_by_id,
            "Occupied unit %s is too close to risk unit %s: %.2f m; minimum is %.2f m.",
            "Move occupied facilities farther from sludge and chemical areas.",
        )


class ProcessAdjacencyConstraint(BaseConstraint):
    def __init__(self, max_preferred_distance: float = 100.0, enabled: bool = True):
        self.max_preferred_distance = max_preferred_distance
        super().__init__(
            constraint_id="C-005",
            name="Process Adjacency",
            constraint_type=ConstraintType.PROCESS_SEQUENCE,
            classification=ConstraintClassification.SOFT,
            severity=Severity.HIGH,
            weight=1.0,
            enabled=enabled,
            description="Connected flow units should remain within preferred adjacency distance.",
        )

    def evaluate_with_context(self, layout: Layout, context=None) -> List[Violation]:
        if layout.flow_graph is None:
            return []
        _, placements_by_id = _unit_maps(layout)
        violations = []
        for edge in layout.flow_graph.edges:
            source = placements_by_id.get(edge.source_unit_id)
            target = placements_by_id.get(edge.target_unit_id)
            if source is None or target is None:
                continue
            distance = float(_point(source).distance(_point(target)))
            if distance > self.max_preferred_distance:
                excess = distance - self.max_preferred_distance
                violations.append(
                    self._violation(
                        suffix=str(len(violations) + 1),
                        affected_units=[edge.source_unit_id, edge.target_unit_id],
                        penalty=excess,
                        description="Flow edge %s spans %.2f m; preferred maximum is %.2f m." % (edge.flow_id, distance, self.max_preferred_distance),
                        suggested_action="Place connected process units closer together where practical.",
                        location=_location_between(source, target),
                    )
                )
        return violations


class GravityFlowConstraint(BaseConstraint):
    def __init__(self, enabled: bool = True):
        super().__init__(
            constraint_id="C-006",
            name="Gravity Flow",
            constraint_type=ConstraintType.GRAVITY,
            classification=ConstraintClassification.SOFT,
            severity=Severity.HIGH,
            weight=1.0,
            enabled=enabled,
            description="Gravity-preferred flow edges should not rise from source to target.",
        )

    def evaluate_with_context(self, layout: Layout, context=None) -> List[Violation]:
        if layout.flow_graph is None:
            return []
        _, placements_by_id = _unit_maps(layout)
        violations = []
        for edge in layout.flow_graph.edges:
            if not edge.gravity_preferred:
                continue
            source = placements_by_id.get(edge.source_unit_id)
            target = placements_by_id.get(edge.target_unit_id)
            if source is None or target is None:
                continue
            source_elevation = source.centroid.elevation
            target_elevation = target.centroid.elevation
            if source_elevation is None or target_elevation is None:
                continue
            if source_elevation < target_elevation:
                rise = target_elevation - source_elevation
                violations.append(
                    self._violation(
                        suffix=str(len(violations) + 1),
                        affected_units=[edge.source_unit_id, edge.target_unit_id],
                        penalty=rise,
                        description="Gravity flow edge %s rises %.2f m from source to target." % (edge.flow_id, rise),
                        suggested_action="Adjust elevations or placement sequence to support gravity flow.",
                        location=_location_between(source, target),
                    )
                )
        return violations
