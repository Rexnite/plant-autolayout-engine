"""Matplotlib renderer for engineering-style plant layouts."""

import os
import tempfile
from pathlib import Path
from typing import Dict, Optional

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib"))

import matplotlib

matplotlib.use("Agg")

from matplotlib import pyplot as plt
from matplotlib.patches import Patch, Polygon as MplPolygon

from wtp_autolayout.geometry import GeometryEngine, GeometryError
from wtp_autolayout.models import Layout
from wtp_autolayout.geometry.routing import FlowRouter
from wtp_autolayout.geometry.site import corridor_geometry, structure_geometry, zone_geometry

from .errors import VisualizationError
from .styles import (
    BOUNDARY_COLOR,
    CHEMICAL_COLOR,
    CLEARANCE_COLOR,
    DRAIN_COLOR,
    FLOW_COLOR,
    PROCESS_COLOR,
    ROAD_COLOR,
    SLUDGE_COLOR,
    SUPPORT_COLOR,
    VIOLATION_COLOR,
    unit_color,
)


class LayoutRenderer:
    """Render a plant layout with engineering-style layers."""

    def __init__(
        self,
        geometry_engine: Optional[GeometryEngine] = None,
        figure_size=(12, 9),
        show_clearance: bool = False,
        show_flow: bool = True,
        show_labels: bool = True,
        show_violations: bool = True,
    ):
        self.geometry_engine = geometry_engine or GeometryEngine()
        self.figure_size = figure_size
        self.show_clearance = show_clearance
        self.show_flow = show_flow
        self.show_labels = show_labels
        self.show_violations = show_violations

    def render(self, layout: Layout, output_path=None, title=None):
        fig, ax = plt.subplots(figsize=self.figure_size)
        ax.set_aspect("equal", adjustable="box")
        ax.set_title(title or layout.metadata.get("project_name") or layout.layout_id)
        ax.set_xlabel("Easting")
        ax.set_ylabel("Northing")

        try:
            boundary = self.geometry_engine.boundary_to_polygon(layout.boundary)
        except GeometryError as error:
            raise VisualizationError("Cannot render boundary: %s" % error)

        self._draw_polygon(ax, boundary, facecolor="none", edgecolor=BOUNDARY_COLOR, linewidth=2.0, label="Boundary")

        units_by_id = {unit.unit_id: unit for unit in layout.units}
        placements_by_id = {placement.unit_id: placement for placement in layout.placements}

        self._draw_infrastructure(ax, layout)
        self._draw_site_features(ax, layout)

        for placement in layout.placements:
            unit = units_by_id.get(placement.unit_id)
            if unit is None:
                continue
            try:
                footprint = self.geometry_engine.unit_to_geometry(unit, placement)
            except GeometryError:
                continue
            color = unit_color(unit)
            if self.show_clearance:
                clearance = self.geometry_engine.unit_to_clearance_geometry(unit, placement)
                self._draw_polygon(ax, clearance, facecolor=CLEARANCE_COLOR, edgecolor=CLEARANCE_COLOR, alpha=0.18, linewidth=0.5)
            self._draw_polygon(ax, footprint, facecolor=color, edgecolor="black", alpha=0.65, linewidth=1.0)
            if self.show_labels:
                label = unit.name or unit.unit_id
                ax.text(placement.centroid.easting, placement.centroid.northing, label, fontsize=8, ha="center", va="center")

        if self.show_flow and layout.flow_graph is not None:
            self._draw_flow(ax, layout, placements_by_id)

        if self.show_violations and layout.violations:
            self._draw_violations(ax, layout, placements_by_id)

        self._draw_north_arrow(ax, boundary.bounds)
        self._draw_legend(ax)
        ax.autoscale_view()
        fig.tight_layout()

        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(str(path), dpi=150, bbox_inches="tight")
        return fig

    def save_png(self, layout: Layout, output_path, title=None) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig = self.render(layout, output_path=None, title=title)
        fig.savefig(str(path), dpi=150, bbox_inches="tight")
        plt.close(fig)
        return str(path)

    def _draw_polygon(self, ax, geometry, facecolor, edgecolor, alpha=1.0, linewidth=1.0, label=None):
        if geometry.geom_type == "Polygon":
            self._draw_single_polygon(ax, geometry, facecolor, edgecolor, alpha, linewidth, label)
        elif geometry.geom_type == "MultiPolygon":
            for polygon in geometry.geoms:
                self._draw_single_polygon(ax, polygon, facecolor, edgecolor, alpha, linewidth, label)

    def _draw_single_polygon(self, ax, polygon, facecolor, edgecolor, alpha, linewidth, label):
        x, y = polygon.exterior.xy
        patch = MplPolygon(
            list(zip(x, y)),
            closed=True,
            facecolor=facecolor,
            edgecolor=edgecolor,
            alpha=alpha,
            linewidth=linewidth,
            label=label,
        )
        ax.add_patch(patch)

    def _draw_flow(self, ax, layout: Layout, placements_by_id: Dict[str, object]) -> None:
        for route in FlowRouter(self.geometry_engine).route(layout):
            x = [point[0] for point in route.points]
            y = [point[1] for point in route.points]
            ax.plot(x, y, color=FLOW_COLOR, linewidth=1.2, alpha=0.8)
            ax.annotate(
                "",
                xy=route.points[-1],
                xytext=route.points[-2],
                arrowprops={"arrowstyle": "->", "color": FLOW_COLOR, "lw": 1.2, "alpha": 0.8},
            )

    def _draw_infrastructure(self, ax, layout: Layout) -> None:
        for road in layout.roads:
            if len(road.path) < 2:
                continue
            x = [point.easting for point in road.path]
            y = [point.northing for point in road.path]
            linewidth = max(float(road.width or 3.0) * 0.15, 1.0)
            ax.plot(x, y, color=ROAD_COLOR, linewidth=linewidth, alpha=0.65, linestyle="-", zorder=1)
        for drain in layout.drains:
            if len(drain.path) < 2:
                continue
            x = [point.easting for point in drain.path]
            y = [point.northing for point in drain.path]
            ax.plot(x, y, color=DRAIN_COLOR, linewidth=1.1, alpha=0.75, linestyle="--", zorder=1)

    def _draw_site_features(self, ax, layout: Layout) -> None:
        colors = {"exclusion": "#c77973", "restricted": "#c99369",
                  "reserved": "#b5a7c5", "expansion": "#93c2a2"}
        for zone in layout.site_zones:
            color = colors[zone.zone_type.value]
            self._draw_polygon(ax, zone_geometry(zone), color, color, alpha=0.35, linewidth=1)
        for structure in layout.existing_structures:
            self._draw_polygon(ax, structure_geometry(structure), "#778386", "#495459",
                               alpha=0.7, linewidth=1)
        for corridor in layout.corridors:
            shape = corridor_geometry(corridor)
            if shape.geom_type == "Polygon":
                self._draw_polygon(ax, shape, "#9ab8bf", "#54798a", alpha=0.3, linewidth=1)
            else:
                x, y = shape.xy
                ax.plot(x, y, color="#54798a", linewidth=1.5, linestyle=":")

    def _draw_violations(self, ax, layout: Layout, placements_by_id: Dict[str, object]) -> None:
        for index, violation in enumerate(layout.violations, start=1):
            points = [placements_by_id[unit_id] for unit_id in violation.affected_units if unit_id in placements_by_id]
            if points:
                x = sum(point.centroid.easting for point in points) / len(points)
                y = sum(point.centroid.northing for point in points) / len(points)
            elif violation.location and violation.location.get("coordinates"):
                x, y = violation.location["coordinates"][:2]
            else:
                continue
            ax.scatter([x], [y], color=VIOLATION_COLOR, marker="x", s=80, linewidths=2)
            ax.text(x, y, "V%s" % index, color=VIOLATION_COLOR, fontsize=8, ha="left", va="bottom")

    def _draw_north_arrow(self, ax, bounds) -> None:
        minx, miny, maxx, maxy = bounds
        x = minx + (maxx - minx) * 0.08
        y = miny + (maxy - miny) * 0.9
        dy = (maxy - miny) * 0.06
        ax.annotate("N", xy=(x, y + dy), ha="center", va="bottom", fontsize=10, fontweight="bold")
        ax.annotate("", xy=(x, y + dy), xytext=(x, y), arrowprops={"arrowstyle": "->", "color": "black", "lw": 1.5})

    def _draw_legend(self, ax) -> None:
        handles = [
            Patch(facecolor=PROCESS_COLOR, edgecolor="black", label="Process / Hydraulic"),
            Patch(facecolor=CHEMICAL_COLOR, edgecolor="black", label="Chemical"),
            Patch(facecolor=SLUDGE_COLOR, edgecolor="black", label="Sludge"),
            Patch(facecolor=SUPPORT_COLOR, edgecolor="black", label="Support / Occupancy"),
            Patch(facecolor="none", edgecolor=BOUNDARY_COLOR, label="Boundary"),
            Patch(facecolor=ROAD_COLOR, edgecolor=ROAD_COLOR, label="Road"),
            Patch(facecolor=DRAIN_COLOR, edgecolor=DRAIN_COLOR, label="Drain"),
            Patch(facecolor=VIOLATION_COLOR, edgecolor=VIOLATION_COLOR, label="Violation"),
            Patch(facecolor="#c77973", label="Exclusion / restricted"),
            Patch(facecolor="#93c2a2", label="Expansion / reserved"),
            Patch(facecolor="#778386", label="Existing structure"),
            Patch(facecolor="#9ab8bf", label="Site corridor"),
        ]
        ax.legend(handles=handles, loc="upper right", fontsize=8)
