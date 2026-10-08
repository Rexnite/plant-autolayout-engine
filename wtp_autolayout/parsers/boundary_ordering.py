"""Deterministic ordering for unordered ordinary site boundary points."""

import math
from typing import List

from shapely.geometry import MultiPoint, Polygon
from shapely.validation import explain_validity

from wtp_autolayout.models import Coordinate

from .errors import ParserError


def order_boundary(vertices: List[Coordinate], ordered: bool = False) -> List[Coordinate]:
    points = list(vertices)
    if len(points) > 3 and points[0].easting == points[-1].easting and points[0].northing == points[-1].northing:
        points.pop()
    xy = [(point.easting, point.northing) for point in points]
    if len(set(xy)) < 3:
        raise ParserError("Boundary needs at least three unique Easting/Northing points")
    if len(set(xy)) != len(xy):
        raise ParserError("Boundary contains duplicate points")
    if not ordered:
        hull = MultiPoint(xy).convex_hull
        if hull.geom_type != "Polygon" or hull.area <= 0:
            raise ParserError("Boundary points are collinear")
        if any(hull.boundary.distance(MultiPoint([point])) > 1e-7 for point in xy):
            raise ParserError("Unordered concave boundary is ambiguous; provide vertex_order for its perimeter")
        center_x = sum(x for x, _ in xy) / len(xy)
        center_y = sum(y for _, y in xy) / len(xy)
        points.sort(key=lambda point: (math.atan2(point.northing - center_y, point.easting - center_x),
                                       (point.easting - center_x) ** 2 + (point.northing - center_y) ** 2))
    polygon = Polygon([(point.easting, point.northing) for point in points])
    if not polygon.is_valid or polygon.area <= 0:
        raise ParserError("Invalid boundary (%s). Recheck vertex_order and Easting/Northing points."
                          % explain_validity(polygon))
    return points
