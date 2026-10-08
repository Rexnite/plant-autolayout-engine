"""Geometry adapters for fixed site features and access corridors."""

from shapely.geometry import LineString, Polygon
from functools import lru_cache

from wtp_autolayout.models import ConstraintClassification, CorridorType

from .errors import GeometryError


def polygon_from_vertices(vertices):
    return _polygon(tuple((float(point.easting), float(point.northing)) for point in vertices))


@lru_cache(maxsize=256)
def _polygon(points):
    polygon = Polygon(points)
    if not polygon.is_valid or polygon.area <= 0:
        raise GeometryError("site polygon must be valid with positive area")
    return polygon


def zone_geometry(zone):
    return polygon_from_vertices(zone.vertices)


def structure_geometry(structure):
    return polygon_from_vertices(structure.vertices)


def corridor_geometry(corridor):
    points = tuple((float(point.easting), float(point.northing)) for point in corridor.path)
    return _corridor(points, float(corridor.width))


@lru_cache(maxsize=256)
def _corridor(points, width):
    line = LineString(points)
    if line.length <= 0:
        raise GeometryError("corridor path must have positive length")
    return line.buffer(width / 2.0, cap_style=2) if width else line


def hard_site_obstacles(layout):
    """Return (id, geometry) pairs; unit clearance is applied by the caller."""
    obstacles = []
    for zone in layout.site_zones:
        if zone.classification == ConstraintClassification.HARD:
            obstacles.append((zone.zone_id, zone_geometry(zone).buffer(zone.clearance)))
    for structure in layout.existing_structures:
        obstacles.append((structure.structure_id, structure_geometry(structure).buffer(structure.clearance)))
    for corridor in layout.corridors:
        if corridor.classification == ConstraintClassification.HARD:
            obstacles.append((corridor.corridor_id, corridor_geometry(corridor).buffer(corridor.setback)))
    for index, entry in enumerate(layout.metadata.get("exclusion_zones", [])):
        vertices = entry.get("vertices") if isinstance(entry, dict) else entry
        try:
            polygon = Polygon([(point["easting"], point["northing"])
                               if isinstance(point, dict) else tuple(point) for point in vertices])
        except (TypeError, ValueError, KeyError) as error:
            raise GeometryError("invalid legacy exclusion %s: %s" % (index, error))
        if not polygon.is_valid or polygon.area <= 0:
            raise GeometryError("invalid legacy exclusion %s polygon" % index)
        obstacles.append(("legacy_exclusion_%s" % index, polygon))
    return obstacles


def access_geometries(layout):
    paths = [(corridor.corridor_id, corridor_geometry(corridor))
             for corridor in layout.corridors if corridor.corridor_type in (CorridorType.ACCESS, CorridorType.ROAD)]
    for road in layout.roads:
        if len(road.path) >= 2:
            line = LineString([(point.easting, point.northing) for point in road.path])
            if line.length > 0:
                paths.append((road.road_id, line.buffer(road.width / 2.0, cap_style=2) if road.width else line))
    return paths


def routing_corridors(layout):
    return [(item.corridor_id, corridor_geometry(item)) for item in layout.corridors
            if item.corridor_type in (CorridorType.ROUTING, CorridorType.UTILITY)]
