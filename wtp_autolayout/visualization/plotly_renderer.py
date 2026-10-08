"""Interactive Plotly layout renderer."""

from pathlib import Path
from typing import Dict, Optional

try:
    import plotly.graph_objects as go
except ImportError:  # pragma: no cover - exercised only when optional dependency is absent
    go = None

from wtp_autolayout.geometry import GeometryEngine
from wtp_autolayout.profiles import get_plant_profile
from wtp_autolayout.models import Layout
from wtp_autolayout.geometry.routing import FlowRouter
from wtp_autolayout.geometry.site import corridor_geometry, structure_geometry, zone_geometry

from .errors import VisualizationError
from .styles import unit_color


class PlotlyLayoutRenderer:
    """Render an interactive plant layout with hoverable engineering metadata."""

    def __init__(
        self,
        geometry_engine: Optional[GeometryEngine] = None,
        show_clearance: bool = False,
        show_flow: bool = True,
        show_labels: bool = True,
        show_violations: bool = True,
    ):
        if go is None:
            raise VisualizationError("Plotly renderer requires the plotly package")
        self.geometry_engine = geometry_engine or GeometryEngine()
        self.show_clearance = show_clearance
        self.show_flow = show_flow
        self.show_labels = show_labels
        self.show_violations = show_violations

    def render(self, layout: Layout, title: Optional[str] = None):
        fig = go.Figure()
        self._draw_boundary(fig, layout)
        placements = {placement.unit_id: placement for placement in layout.placements}
        units = {unit.unit_id: unit for unit in layout.units}
        self._draw_infrastructure(fig, layout)
        self._draw_site_features(fig, layout)

        if self.show_clearance:
            for unit in layout.units:
                placement = placements.get(unit.unit_id)
                if placement is not None:
                    self._draw_clearance(fig, unit, placement)

        for unit in layout.units:
            placement = placements.get(unit.unit_id)
            if placement is not None:
                self._draw_unit(fig, unit, placement, get_plant_profile(layout.plant_type).inferred_group(unit))

        if self.show_flow and layout.flow_graph is not None:
            routes = {route.flow_id: route for route in FlowRouter(self.geometry_engine).route(layout)}
            for edge in layout.flow_graph.edges:
                source = placements.get(edge.source_unit_id)
                target = placements.get(edge.target_unit_id)
                if source is not None and target is not None:
                    self._draw_flow(fig, edge, source, target, routes.get(edge.flow_id))

        if self.show_violations:
            self._draw_violations(fig, layout, placements)

        fig.update_layout(
            title=title or layout.metadata.get("project_name") or layout.layout_id,
            xaxis_title="Easting",
            yaxis_title="Northing",
            yaxis={"scaleanchor": "x", "scaleratio": 1},
            hovermode="closest",
            legend_title="Layers",
        )
        minx, miny, maxx, maxy = self.geometry_engine.boundary_to_polygon(layout.boundary).bounds
        fig.add_annotation(x=minx + (maxx - minx) * 0.08, y=miny + (maxy - miny) * 0.91,
                           ax=minx + (maxx - minx) * 0.08, ay=miny + (maxy - miny) * 0.83,
                           xref="x", yref="y", axref="x", ayref="y", text="N", showarrow=True,
                           arrowhead=2, arrowcolor="black", arrowwidth=2)
        return fig

    def export_html(self, layout: Layout, output_path, title: Optional[str] = None) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig = self.render(layout, title=title)
        fig.write_html(str(path), include_plotlyjs="cdn", full_html=True)
        return str(path)

    def _draw_boundary(self, fig, layout: Layout) -> None:
        boundary = self.geometry_engine.boundary_to_polygon(layout.boundary)
        x, y = boundary.exterior.xy
        fig.add_trace(
            go.Scatter(
                x=list(x),
                y=list(y),
                mode="lines",
                name="Boundary",
                line={"color": "black", "width": 2},
                hovertext="Site boundary<br>Area: %.2f" % boundary.area,
                hoverinfo="text",
            )
        )

    def _draw_unit(self, fig, unit, placement, group=None) -> None:
        geometry = self.geometry_engine.unit_to_geometry(unit, placement)
        x, y = geometry.exterior.xy
        cluster = group or "unclassified"
        hover = [
            "ID: %s" % unit.unit_id,
            "Name: %s" % unit.name,
            "Category: %s" % unit.category.value,
            "Dimensions: %s" % self._dimensions(unit),
            "Coordinates: %.2f, %.2f" % (placement.centroid.easting, placement.centroid.northing),
            "Elevation: %s" % (placement.centroid.elevation if placement.centroid.elevation is not None else "N/A"),
            "Clearance: %.2f" % unit.required_clearance,
            "Cluster: %s" % cluster,
        ]
        fig.add_trace(
            go.Scatter(
                x=list(x),
                y=list(y),
                fill="toself",
                mode="lines+text" if self.show_labels else "lines",
                text=[unit.name or unit.unit_id] + [""] * (len(x) - 1),
                name=unit.name or unit.unit_id,
                legendgroup="Units",
                fillcolor=unit_color(unit),
                line={"color": "black", "width": 1},
                opacity=0.65,
                hovertext="<br>".join(hover),
                hoverinfo="text",
            )
        )

    def _draw_clearance(self, fig, unit, placement) -> None:
        geometry = self.geometry_engine.unit_to_clearance_geometry(unit, placement)
        x, y = geometry.exterior.xy
        fig.add_trace(
            go.Scatter(
                x=list(x),
                y=list(y),
                fill="toself",
                mode="lines",
                name="Clearance",
                legendgroup="Clearance",
                line={"color": "rgba(120,120,120,0.5)", "dash": "dot"},
                fillcolor="rgba(120,120,120,0.12)",
                hovertext="%s clearance %.2f" % (unit.unit_id, unit.required_clearance),
                hoverinfo="text",
            )
        )

    def _draw_flow(self, fig, edge, source, target, route=None) -> None:
        length = route.length if route else self._distance(source, target)
        points = route.points if route else ((source.centroid.easting, source.centroid.northing),
                                              (target.centroid.easting, target.centroid.northing))
        hover = [
            "Source: %s" % edge.source_unit_id,
            "Destination: %s" % edge.target_unit_id,
            "Length: %.2f" % length,
            "Pipe type: %s" % (edge.pipe_or_channel_type or edge.flow_type.value),
            "Gravity preference: %s" % edge.gravity_preferred,
        ]
        fig.add_trace(
            go.Scatter(
                x=[point[0] for point in points],
                y=[point[1] for point in points],
                mode="lines",
                name="Flow",
                legendgroup="Flow",
                line={"color": "#0B3D91", "width": 2},
                hovertext="<br>".join(hover),
                hoverinfo="text",
            )
        )
        fig.add_annotation(x=points[-1][0], y=points[-1][1], ax=points[-2][0], ay=points[-2][1],
                           xref="x", yref="y", axref="x", ayref="y", text="", showarrow=True,
                           arrowhead=3, arrowcolor="#0B3D91", arrowwidth=1.5)

    def _draw_infrastructure(self, fig, layout: Layout) -> None:
        for road in layout.roads:
            if len(road.path) < 2:
                continue
            fig.add_trace(
                go.Scatter(
                    x=[point.easting for point in road.path],
                    y=[point.northing for point in road.path],
                    mode="lines",
                    name="Road",
                    legendgroup="Roads",
                    line={"color": "#6F6F6F", "width": max(float(road.width or 3.0), 2.0)},
                    hovertext="Road: %s<br>Type: %s<br>Width: %s"
                    % (road.road_id, road.road_type or "N/A", road.width if road.width is not None else "N/A"),
                    hoverinfo="text",
                )
            )

        for drain in layout.drains:
            if len(drain.path) < 2:
                continue
            fig.add_trace(go.Scatter(
                x=[point.easting for point in drain.path],
                y=[point.northing for point in drain.path], mode="lines",
                name="Drain", legendgroup="Drains",
                line={"color": "#4E79A7", "width": 2, "dash": "dash"},
                hovertext="Drain: %s<br>Flow direction: %s" % (
                    drain.drain_id, drain.flow_direction or "N/A"), hoverinfo="text"))

    def _draw_site_features(self, fig, layout: Layout) -> None:
        colors = {"exclusion": "rgba(185,50,50,0.28)", "restricted": "rgba(190,100,50,0.24)",
                  "reserved": "rgba(115,100,150,0.22)", "expansion": "rgba(65,150,90,0.22)"}
        for zone in layout.site_zones:
            polygon = zone_geometry(zone)
            x, y = polygon.exterior.xy
            fig.add_trace(go.Scatter(x=list(x), y=list(y), mode="lines", fill="toself",
                                     name=zone.zone_type.value.title(), legendgroup=zone.zone_type.value,
                                     fillcolor=colors[zone.zone_type.value],
                                     line={"color": colors[zone.zone_type.value], "width": 2},
                                     hovertext="%s: %s<br>%s<br>%s" % (zone.zone_id, zone.name,
                                          zone.classification.value, zone.provenance), hoverinfo="text"))
        for structure in layout.existing_structures:
            polygon = structure_geometry(structure)
            x, y = polygon.exterior.xy
            fig.add_trace(go.Scatter(x=list(x), y=list(y), mode="lines", fill="toself",
                                     name="Existing structure", legendgroup="Existing structures",
                                     fillcolor="rgba(95,105,110,0.55)", line={"color": "#464f52", "width": 2},
                                     hovertext="Fixed: %s<br>%s" % (structure.structure_id, structure.name),
                                     hoverinfo="text"))
        for corridor in layout.corridors:
            geometry = corridor_geometry(corridor)
            coords = list(geometry.exterior.coords) if geometry.geom_type == "Polygon" else list(geometry.coords)
            fig.add_trace(go.Scatter(x=[point[0] for point in coords], y=[point[1] for point in coords],
                                     mode="lines", name=corridor.corridor_type.value.title() + " corridor",
                                     legendgroup="Corridors", line={"color": "#54798a", "width": 2,
                                                                    "dash": "dot"},
                                     hovertext="%s<br>Width %.1f" % (corridor.name, corridor.width),
                                     hoverinfo="text"))

    def _draw_violations(self, fig, layout: Layout, placements: Dict[str, object]) -> None:
        for violation in layout.violations:
            points = [placements[unit_id] for unit_id in violation.affected_units if unit_id in placements]
            if not points:
                continue
            x = sum(point.centroid.easting for point in points) / float(len(points))
            y = sum(point.centroid.northing for point in points) / float(len(points))
            fig.add_trace(
                go.Scatter(
                    x=[x],
                    y=[y],
                    mode="markers",
                    name="Violation",
                    legendgroup="Violations",
                    marker={"color": "red", "size": 12, "symbol": "x"},
                    hovertext="%s<br>%s" % (violation.constraint_id, violation.description),
                    hoverinfo="text",
                )
            )

    def _dimensions(self, unit) -> str:
        if unit.diameter is not None:
            return "diameter %.2f" % unit.diameter
        if unit.width is not None and unit.length is not None:
            return "%.2f x %.2f" % (unit.width, unit.length)
        return "N/A"

    def _distance(self, source, target) -> float:
        dx = source.centroid.easting - target.centroid.easting
        dy = source.centroid.northing - target.centroid.northing
        return (dx * dx + dy * dy) ** 0.5
