"""Centralized visualization styling."""

from wtp_autolayout.models import UnitCategory

BOUNDARY_COLOR = "black"
FLOW_COLOR = "#0B3D91"
VIOLATION_COLOR = "#D62728"
CLEARANCE_COLOR = "#BBBBBB"
ROAD_COLOR = "#6F6F6F"
DRAIN_COLOR = "#4E79A7"

PROCESS_COLOR = "#4C78A8"
CHEMICAL_COLOR = "#59A14F"
SLUDGE_COLOR = "#8C564B"
SUPPORT_COLOR = "#9E9E9E"
DEFAULT_UNIT_COLOR = "#B0C4DE"


def unit_color(unit) -> str:
    if unit.category in (UnitCategory.PROCESS, UnitCategory.HYDRAULIC, UnitCategory.CLEAN_WATER):
        return PROCESS_COLOR
    if unit.category == UnitCategory.CHEMICAL:
        return CHEMICAL_COLOR
    if unit.category == UnitCategory.SLUDGE:
        return SLUDGE_COLOR
    if unit.category in (UnitCategory.RESIDENTIAL, UnitCategory.HUMAN_OCCUPANCY, UnitCategory.UTILITY, UnitCategory.ELECTRICAL):
        return SUPPORT_COLOR

    text = " ".join([unit.name or "", unit.system_group or ""]).lower()
    if "chemical" in text or "chlorine" in text:
        return CHEMICAL_COLOR
    if "sludge" in text:
        return SLUDGE_COLOR
    if "admin" in text or "residential" in text or "staff" in text:
        return SUPPORT_COLOR
    return DEFAULT_UNIT_COLOR
