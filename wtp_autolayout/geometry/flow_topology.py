"""Straight-line process topology, separate from displayed routes."""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from shapely.geometry import LineString, Point

from wtp_autolayout.models import Layout


@dataclass(frozen=True)
class CrossingEvent:
    edge_a: str
    edge_b: str
    coordinate: Optional[Tuple[float, float]]
    kind: str

    def to_dict(self):
        return {"edge_a": self.edge_a, "edge_b": self.edge_b,
                "coordinate": list(self.coordinate) if self.coordinate else None, "kind": self.kind}


def flow_crossing_diagnostics(layout: Layout) -> List[CrossingEvent]:
    placements = {placement.unit_id: placement for placement in layout.placements}
    segments = []
    for edge in layout.flow_graph.edges if layout.flow_graph else []:
        source = placements.get(edge.source_unit_id)
        target = placements.get(edge.target_unit_id)
        if source is None or target is None:
            continue
        line = LineString([(source.centroid.easting, source.centroid.northing),
                           (target.centroid.easting, target.centroid.northing)])
        if line.length > 0:
            segments.append((edge, line))
    crossings: List[CrossingEvent] = []
    for index, (edge_a, line_a) in enumerate(segments):
        for edge_b, line_b in segments[index + 1:]:
            if {edge_a.source_unit_id, edge_a.target_unit_id} & {edge_b.source_unit_id, edge_b.target_unit_id}:
                continue
            intersection = line_a.intersection(line_b)
            if intersection.is_empty:
                continue
            endpoints = [Point(line_a.coords[0]), Point(line_a.coords[-1]),
                         Point(line_b.coords[0]), Point(line_b.coords[-1])]
            if intersection.geom_type == "Point" and any(intersection.distance(point) <= 1e-8 for point in endpoints):
                continue
            if intersection.geom_type == "Point":
                coordinate = (float(intersection.x), float(intersection.y))
                kind = "interior_crossing"
            elif intersection.geom_type in ("LineString", "MultiLineString"):
                if intersection.length <= 1e-8:
                    continue
                midpoint = intersection.interpolate(intersection.length / 2.0)
                coordinate = (float(midpoint.x), float(midpoint.y))
                kind = "collinear_overlap"
            else:
                point = intersection.representative_point()
                coordinate = (float(point.x), float(point.y))
                kind = "intersection"
            crossings.append(CrossingEvent(edge_a.flow_id, edge_b.flow_id, coordinate, kind))
    return crossings


def flow_crossings(layout: Layout) -> List[Tuple[str, str]]:
    return [(event.edge_a, event.edge_b) for event in flow_crossing_diagnostics(layout)]
