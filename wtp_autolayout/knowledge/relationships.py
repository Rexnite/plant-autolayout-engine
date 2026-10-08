"""Preferred adjacency and separation rules for WTP units."""

from typing import Dict, Optional

from .clusters import get_cluster


PREFERRED_ADJACENCY: Dict[tuple, str] = {
    ("flash mixer", "drop chamber"): "preferred_adjacency",
    ("drop chamber", "clarifier"): "preferred_adjacency",
    ("cwr", "pump house"): "preferred_adjacency",
    ("clear water reservoir", "pump house"): "preferred_adjacency",
}

PREFERRED_DISTANCES = {
    "preferred_adjacency": 25.0,
    "same_cluster": 45.0,
    "pipe_accessibility": 80.0,
}

SEPARATION_RULES = {
    ("sludge", "residential"): 30.0,
    ("sludge", "admin"): 30.0,
    ("chemical", "residential"): 25.0,
    ("chemical", "admin"): 25.0,
}


def get_relationship(unit_a, unit_b) -> Optional[str]:
    """Return the preferred relationship between two unit-like objects."""
    text_a = _normalize(unit_a)
    text_b = _normalize(unit_b)
    for (source, target), relationship in PREFERRED_ADJACENCY.items():
        if source in text_a and target in text_b:
            return relationship
        if source in text_b and target in text_a:
            return relationship

    cluster_a = get_cluster(unit_a)
    cluster_b = get_cluster(unit_b)
    if cluster_a and cluster_a == cluster_b:
        return "same_cluster"
    if "chemical house" in text_a or "chemical house" in text_b:
        return "pipe_accessibility"
    return None


def get_preferred_distance(relationship: Optional[str] = None) -> float:
    """Return a preferred distance threshold for a relationship."""
    if relationship is None:
        return PREFERRED_DISTANCES["same_cluster"]
    return PREFERRED_DISTANCES.get(relationship, PREFERRED_DISTANCES["same_cluster"])


def get_separation_rule(unit_a, unit_b) -> Optional[float]:
    """Return minimum separation distance for an incompatible pair, if any."""
    type_a = _separation_type(unit_a)
    type_b = _separation_type(unit_b)
    if type_a is None or type_b is None:
        return None
    return SEPARATION_RULES.get((type_a, type_b)) or SEPARATION_RULES.get((type_b, type_a))


def _separation_type(unit) -> Optional[str]:
    text = _normalize(unit)
    cluster = get_cluster(unit)
    if cluster in ("sludge", "chemical"):
        return cluster
    if "admin" in text:
        return "admin"
    if "residential" in text or "building" in text:
        return "residential"
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
