"""Bounded orthogonal display routing; topology scores use straight flows separately."""

import heapq
import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple

from shapely.geometry import LineString

from wtp_autolayout.models import Layout

from .engine import GeometryEngine
from .site import hard_site_obstacles, routing_corridors


class RoutingStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FALLBACK = "FALLBACK"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class FlowRoute:
    flow_id: str
    source_unit_id: str
    target_unit_id: str
    points: Tuple[Tuple[float, float], ...]
    length: float
    flow_type: str
    gravity_preferred: bool
    fallback: bool = False
    status: RoutingStatus = RoutingStatus.SUCCESS
    straight_length: float = 0.0
    detour_ratio: float = 1.0
    bends: int = 0
    obstacle_conflicts: int = 0
    route_crossings: int = 0
    corridor_usage: str = "none"
    corridor_length: float = 0.0

    def to_dict(self):
        return {**vars(self), "status": self.status.value, "points": [list(point) for point in self.points]}


@dataclass(frozen=True)
class RouteResult:
    routes: Tuple[FlowRoute, ...]

    def to_dict(self):
        return {"routes": [route.to_dict() for route in self.routes],
                "straight_length": sum(route.straight_length for route in self.routes),
                "routed_length": sum(route.length for route in self.routes),
                "fallback_count": sum(route.fallback for route in self.routes),
                "obstacle_conflicts": sum(route.obstacle_conflicts for route in self.routes),
                "route_crossings": sum(route.route_crossings for route in self.routes),
                "bend_count": sum(route.bends for route in self.routes),
                "corridor_length": sum(route.corridor_length for route in self.routes),
                "corridor_used_count": sum(route.corridor_length > 0 for route in self.routes)}


class FlowRouter:
    def __init__(self, geometry_engine=None, routing_clearance: float = 2.0,
                 max_grid_lines: int = 48):
        if (not isinstance(routing_clearance, (int, float)) or isinstance(routing_clearance, bool) or
                not math.isfinite(routing_clearance) or routing_clearance < 0 or
                not isinstance(max_grid_lines, int) or isinstance(max_grid_lines, bool) or
                not 4 <= max_grid_lines <= 64):
            raise ValueError("routing clearance must be finite and non-negative; grid limit must be 4..64")
        self.geometry_engine = geometry_engine or GeometryEngine()
        self.routing_clearance = routing_clearance
        self.max_grid_lines = max_grid_lines

    def route(self, layout: Layout) -> List[FlowRoute]:
        return list(self.route_with_diagnostics(layout).routes)

    def route_with_diagnostics(self, layout: Layout) -> RouteResult:
        placements = {item.unit_id: item for item in layout.placements}
        units = {item.unit_id: item for item in layout.units}
        try:
            boundary = self.geometry_engine.boundary_to_polygon(layout.boundary)
            obstacles: Dict[str, object] = {}
            for unit_id, placement in placements.items():
                if unit_id in units:
                    try:
                        obstacles[unit_id] = self.geometry_engine.unit_to_geometry(units[unit_id], placement)
                    except Exception:
                        pass
            obstacles.update(hard_site_obstacles(layout))
            preferred = routing_corridors(layout)
        except Exception:
            return RouteResult(())

        routes: List[FlowRoute] = []
        previous: List[LineString] = []
        for edge in layout.flow_graph.edges if layout.flow_graph else []:
            source = placements.get(edge.source_unit_id)
            target = placements.get(edge.target_unit_id)
            if source is None or target is None:
                continue
            a = (float(source.centroid.easting), float(source.centroid.northing))
            b = (float(target.centroid.easting), float(target.centroid.northing))
            straight = math.dist(a, b)
            unrelated = [shape.buffer(self.routing_clearance) for key, shape in obstacles.items()
                         if key not in (edge.source_unit_id, edge.target_unit_id)]
            try:
                points = self._find_path(a, b, boundary, unrelated, previous, preferred)
                if points is None:
                    points = self._find_path(a, b, boundary, unrelated, [], preferred)
                status = RoutingStatus.SUCCESS if points is not None else RoutingStatus.FALLBACK
                if points is None:
                    points = (a, b)
                line = LineString(points)
                conflicts = sum(line.crosses(shape) or line.within(shape) for shape in unrelated)
                crossings = sum(line.crosses(other) for other in previous)
                corridor_length = sum(line.intersection(shape).length for _, shape in preferred)
                usage = ("none" if corridor_length <= 1e-8 else
                         "full" if corridor_length >= line.length - 1e-8 else "partial")
                if status == RoutingStatus.FALLBACK and conflicts:
                    status = RoutingStatus.BLOCKED
                previous.append(line)
                routes.append(FlowRoute(edge.flow_id, edge.source_unit_id, edge.target_unit_id,
                            tuple(points), line.length, edge.flow_type.value, edge.gravity_preferred,
                            status != RoutingStatus.SUCCESS, status, straight,
                            line.length / straight if straight else 1.0,
                            max(0, len(points) - 2), conflicts, crossings, usage, corridor_length))
            except Exception:
                routes.append(FlowRoute(edge.flow_id, edge.source_unit_id, edge.target_unit_id,
                            (a, b), straight, edge.flow_type.value, edge.gravity_preferred,
                            True, RoutingStatus.FAILED, straight))
        return RouteResult(tuple(routes))

    def _find_path(self, start, end, boundary, obstacles, prior, preferred=()):
        if start == end:
            return None
        minx, miny, maxx, maxy = boundary.bounds
        margin = max(self.routing_clearance, 1.0)
        xs = {start[0], end[0], minx + margin, maxx - margin}
        ys = {start[1], end[1], miny + margin, maxy - margin}
        for obstacle in obstacles:
            x0, y0, x1, y1 = obstacle.bounds
            xs.update((x0 - margin, x1 + margin))
            ys.update((y0 - margin, y1 + margin))
        for _, corridor in preferred:
            x0, y0, x1, y1 = corridor.bounds
            xs.update((x0, x1))
            ys.update((y0, y1))
        xs = self._limited_lines(xs, start[0], end[0], minx, maxx)
        ys = self._limited_lines(ys, start[1], end[1], miny, maxy)
        if start[0] not in xs or end[0] not in xs or start[1] not in ys or end[1] not in ys:
            return None
        begin = (xs.index(start[0]), ys.index(start[1]))
        goal = (xs.index(end[0]), ys.index(end[1]))
        queue = [(0.0, begin)]
        costs = {begin: 0.0}
        parent = {}
        obstacle_bounds = [(shape.bounds, shape) for shape in obstacles]
        prior_bounds = [(line.bounds, line) for line in prior]
        preferred_bounds = [(shape.bounds, shape) for _, shape in preferred]
        edge_costs = {}
        while queue:
            cost, node = heapq.heappop(queue)
            if cost != costs.get(node):
                continue
            if node == goal:
                break
            x, y = node
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                nx, ny = neighbor
                if not (0 <= nx < len(xs) and 0 <= ny < len(ys)):
                    continue
                edge = (node, neighbor) if node < neighbor else (neighbor, node)
                if edge not in edge_costs:
                    segment = LineString(((xs[x], ys[y]), (xs[nx], ys[ny])))
                    segment_bounds = segment.bounds
                    if (not boundary.covers(segment) or
                            any(self._bounds_overlap(segment_bounds, box) and segment.intersects(shape)
                                for box, shape in obstacle_bounds) or
                            any(self._bounds_overlap(segment_bounds, box) and segment.crosses(line)
                                for box, line in prior_bounds)):
                        edge_costs[edge] = None
                    else:
                        length = segment.length
                        corridor_length = sum(segment.intersection(shape).length
                                              for box, shape in preferred_bounds
                                              if self._bounds_overlap(segment_bounds, box))
                        corridor_fraction = min(1.0, corridor_length / length)
                        edge_costs[edge] = length * (1.0 - 0.25 * corridor_fraction)
                edge_cost = edge_costs[edge]
                if edge_cost is None:
                    continue
                next_cost = cost + edge_cost
                if next_cost < costs.get(neighbor, float("inf")):
                    costs[neighbor] = next_cost
                    parent[neighbor] = node
                    heapq.heappush(queue, (next_cost, neighbor))
        if goal not in costs:
            return None
        nodes = [goal]
        while nodes[-1] != begin:
            nodes.append(parent[nodes[-1]])
        points = [(xs[x], ys[y]) for x, y in reversed(nodes)]
        reduced = [points[0]]
        for index, point in enumerate(points[1:-1], start=1):
            following = points[index + 1]
            if (reduced[-1][0] == point[0] == following[0] or
                    reduced[-1][1] == point[1] == following[1]):
                continue
            reduced.append(point)
        reduced.append(points[-1])
        return tuple(reduced)

    def _limited_lines(self, values, a, b, lower, upper):
        selected = sorted(value for value in values if lower <= value <= upper)
        if len(selected) <= self.max_grid_lines:
            return selected
        keep = {a, b}
        remaining = sorted((value for value in selected if value not in keep),
                           key=lambda value: min(abs(value - a), abs(value - b)))
        keep.update(remaining[:self.max_grid_lines - len(keep)])
        return sorted(keep)

    @staticmethod
    def _bounds_overlap(a, b):
        return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]
