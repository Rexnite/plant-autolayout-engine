"""WTP engineering process clusters."""

from typing import Optional


HYDRAULIC_CLUSTER = {
    "cascade aerator",
    "inlet channel",
    "parshall flume",
    "distribution chamber",
    "flash mixer",
    "drop chamber",
    "clarifier",
    "filters",
    "filter",
    "rapid sand filter",
}

SLUDGE_CLUSTER = {
    "sludge sump",
    "sludge thickener",
    "centrifuge",
    "disposal",
}

CHEMICAL_CLUSTER = {
    "chemical house",
    "chlorine system",
}

CLEAR_WATER_CLUSTER = {
    "clear water reservoir",
    "cwr",
    "pump house",
}


def get_cluster(unit_type) -> Optional[str]:
    """Return the engineering cluster name for a unit-like object or text."""
    text = _normalize(unit_type)
    if _contains_any(text, HYDRAULIC_CLUSTER):
        return "hydraulic"
    if _contains_any(text, SLUDGE_CLUSTER):
        return "sludge"
    if _contains_any(text, CHEMICAL_CLUSTER):
        return "chemical"
    if _contains_any(text, CLEAR_WATER_CLUSTER):
        return "clear_water"
    return None


def _normalize(value) -> str:
    parts = []
    for attr in ("unit_id", "name", "system_group"):
        item = getattr(value, attr, None)
        if item:
            parts.append(str(item))
    if not parts:
        parts.append(str(value))
    return " ".join(parts).replace("_", " ").replace("-", " ").lower()


def _contains_any(text: str, options) -> bool:
    return any(option in text for option in options)
