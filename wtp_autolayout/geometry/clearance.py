"""Clearance geometry helpers."""

from wtp_autolayout.models import EngineeringUnit

from .errors import GeometryError


def clearance_geometry(unit: EngineeringUnit, footprint):
    """Create buffered clearance geometry around a unit footprint."""
    clearance = max(unit.required_clearance or 0.0, unit.maintenance_clearance or 0.0)
    if clearance < 0:
        raise GeometryError("required_clearance must be non-negative")
    buffered = footprint.buffer(clearance)
    if buffered.is_empty or not buffered.is_valid or buffered.area <= 0:
        raise GeometryError("clearance geometry is invalid")
    return buffered
