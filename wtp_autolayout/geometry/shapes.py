"""Shapely shape construction helpers."""

from shapely.affinity import rotate, translate
from shapely.geometry import Point, Polygon, box

from wtp_autolayout.models import Boundary, EngineeringUnit, Placement, ShapeType

from .errors import GeometryError


def boundary_to_polygon(boundary: Boundary) -> Polygon:
    """Convert a Boundary into a valid Shapely polygon."""
    if len(boundary.vertices) < 3:
        raise GeometryError("Boundary requires at least 3 vertices")

    coordinates = [(vertex.easting, vertex.northing) for vertex in boundary.vertices]
    polygon = Polygon(coordinates)
    _validate_geometry(polygon, "boundary polygon")
    return polygon


def unit_to_geometry(unit: EngineeringUnit, placement: Placement):
    """Create a Shapely footprint for an EngineeringUnit at a Placement."""
    if placement.unit_id != unit.unit_id:
        raise GeometryError("Placement unit_id must match EngineeringUnit unit_id")

    if unit.shape_type == ShapeType.RECTANGLE:
        geometry = _rectangle(unit.width, unit.length)
        geometry = _rotate_and_translate(geometry, placement.rotation, placement.centroid.easting, placement.centroid.northing)
    elif unit.shape_type == ShapeType.SQUARE:
        side = _square_side(unit)
        geometry = _rectangle(side, side)
        geometry = _rotate_and_translate(geometry, placement.rotation, placement.centroid.easting, placement.centroid.northing)
    elif unit.shape_type == ShapeType.CIRCLE:
        if unit.diameter is None:
            raise GeometryError("Circular unit requires diameter")
        geometry = Point(placement.centroid.easting, placement.centroid.northing).buffer(unit.diameter / 2.0)
    else:
        raise GeometryError("Unsupported unit shape for Phase 3 geometry: %s" % unit.shape_type.value)

    _validate_geometry(geometry, "unit footprint %s" % unit.unit_id)
    return geometry


def _rectangle(width, length) -> Polygon:
    if width is None or length is None:
        raise GeometryError("Rectangular unit requires width and length")
    return box(-float(length) / 2.0, -float(width) / 2.0, float(length) / 2.0, float(width) / 2.0)


def _square_side(unit: EngineeringUnit) -> float:
    side = unit.width if unit.width is not None else unit.length
    if side is None:
        raise GeometryError("Square unit requires width or length")
    return float(side)


def _rotate_and_translate(geometry, rotation_degrees: float, x: float, y: float):
    rotated = rotate(geometry, rotation_degrees, origin=(0, 0), use_radians=False)
    return translate(rotated, xoff=x, yoff=y)


def _validate_geometry(geometry, label: str) -> None:
    if geometry.is_empty:
        raise GeometryError("%s is empty" % label)
    if not geometry.is_valid:
        raise GeometryError("%s is invalid" % label)
    if geometry.area <= 0:
        raise GeometryError("%s area must be positive" % label)
