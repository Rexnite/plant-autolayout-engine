"""Process sequencing helpers for WTP engineering knowledge."""

from .relationships import get_preferred_distance, get_relationship, get_separation_rule

PROCESS_SEQUENCE_HINTS = (
    "raw water inlet",
    "cascade aerator",
    "flash mixer",
    "drop chamber",
    "clarifier",
    "filter",
    "clear water reservoir",
    "pump house",
)

__all__ = [
    "PROCESS_SEQUENCE_HINTS",
    "get_preferred_distance",
    "get_relationship",
    "get_separation_rule",
]
