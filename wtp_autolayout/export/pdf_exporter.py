"""PDF report exporter."""

import tempfile
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from wtp_autolayout.visualization import LayoutRenderer
from wtp_autolayout.constraints.spatial import proximity_results
from wtp_autolayout.geometry.flow_topology import flow_crossings


class PDFExporter:
    """Export simple engineering PDF reports."""

    def __init__(self, renderer=None):
        self.renderer = renderer or LayoutRenderer()

    def export_layout_report(self, layout, output_path, title=None, include_image: bool = True) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(str(path), pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        report_title = title or "Plant Layout Report"
        story.append(Paragraph(report_title, styles["Title"]))
        story.append(Paragraph("Generated: %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"), styles["Normal"]))
        story.append(Spacer(1, 12))

        score = layout.optimization_score if layout.optimization_score is not None else "N/A"
        metadata = layout.statistics.metadata if layout.statistics else {}
        diagnostics = metadata.get("diagnostics", {})
        routing = diagnostics.get("routing", {})
        breakdown = metadata.get("score_breakdown", {})
        settings = diagnostics.get("optimization_settings", {})
        relations = proximity_results(layout)
        proximity_passed = sum(bool(row["passed"]) for row in relations)
        summary_data = [
            ["Metric", "Value"],
            ["Layout ID", layout.layout_id],
            ["Plant type", layout.plant_type.value],
            ["Active profile", diagnostics.get("active_profile", layout.plant_type.value)],
            ["Algorithm", settings.get("algorithm", "N/A")],
            ["Layout mode", settings.get("layout_mode", "N/A")],
            ["Seed / candidates / iterations", "%s / %s / %s" % (settings.get("seed", "N/A"),
                settings.get("candidate_count", "N/A"), settings.get("iterations", "N/A"))],
            ["Score", score],
            ["Units", len(layout.units)],
            ["Placements", len(layout.placements)],
            ["Violations", len(layout.violations)],
            ["Hard / soft violations", "%s / %s" % (breakdown.get("hard_violation_count", 0),
                breakdown.get("soft_violation_count", 0))],
            ["Proximity satisfied", "%s / %s" % (proximity_passed, len(relations))],
            ["Flow crossings", len(flow_crossings(layout))],
            ["Routed flow length", "%.1f" % routing.get("routed_length", 0.0)],
            ["Routing fallbacks", routing.get("fallback_count", 0)],
            ["Corridor routes", routing.get("corridor_used_count", 0)],
            ["Site feature conflicts", len(diagnostics.get("site", []))],
            ["Runtime to report (s)", "%.2f" % (layout.statistics.runtime or 0.0) if layout.statistics else "N/A"],
        ]
        story.append(self._table(summary_data))
        story.append(Spacer(1, 12))

        components = breakdown.get("objective_breakdown", {})
        if components:
            story.append(Paragraph("Score Breakdown", styles["Heading2"]))
            story.append(self._table([["Base", "Hard penalty", "Soft penalty", "Rewards", "Final"]] +
                                     [["%.1f" % breakdown.get("base_score", 65),
                                       "%.1f" % breakdown.get("hard_penalty", 0),
                                       "%.1f" % breakdown.get("soft_penalty", 0),
                                       "%.1f" % breakdown.get("reward_total", 0),
                                       "%.1f" % breakdown.get("score", 0)]]))
            story.append(Spacer(1, 6))
            story.append(self._table([["Objective", "Quality", "Weight", "Effective", "Points"]] +
                                     [[name.replace("_", " ").title(),
                                       "%.2f" % value["normalized_metric"],
                                       "%.1f" % value["configured_weight"],
                                       "%.1f" % value["effective_weight"],
                                       "%.2f" % value["weighted_contribution"]]
                                      for name, value in components.items()]))
            story.append(Spacer(1, 12))

        if relations:
            story.append(Paragraph("Pairwise Distance Requirements", styles["Heading2"]))
            story.append(self._table([["Pair", "Rule", "Required", "Actual", "Pass"]] +
                                     [["%s / %s" % (row["unit_id_a"], row["unit_id_b"]),
                                       row["requirement"], "%.1f" % row["required_distance"],
                                       "%.1f" % row["actual_distance"], "Yes" if row["passed"] else "No"]
                                      for row in relations]))
            story.append(Spacer(1, 12))

        for heading, rows, headers, values in (
            ("Site Features", diagnostics.get("site", []), ["Unit", "Feature", "Type", "Area", "Class"],
             lambda row: [row["unit_id"], row["feature_id"], row["feature_type"],
                          "%.1f" % row["occupied_area"], row["classification"]]),
            ("Access Checks", diagnostics.get("access", []), ["Unit", "Corridor", "Actual", "Max", "Pass"],
             lambda row: [row["unit_id"], row["nearest_corridor"] or "none",
                          "%.1f" % row["actual_distance"] if row["actual_distance"] is not None else "N/A",
                          "%.1f" % row["required_maximum"] if row["required_maximum"] is not None else "N/A",
                          "Yes" if row["satisfied"] else "No"]),
            ("Group Rules", diagnostics.get("group_relationships", []), ["Groups", "Rule", "Required", "Actual", "Pass"],
             lambda row: [row["group_id_a"] + "/" + row["group_id_b"], row["requirement"],
                          "%.1f" % row["required_distance"], "%.1f" % row["actual_distance"],
                          "Yes" if row["satisfied"] else "No"]),
        ):
            if rows:
                story.append(Paragraph(heading, styles["Heading2"]))
                story.append(self._table([headers] + [values(row) for row in rows[:20]]))
                story.append(Spacer(1, 12))

        if diagnostics.get("crossings"):
            story.append(Paragraph("Topology Crossings", styles["Heading2"]))
            story.append(self._table([["Flow A", "Flow B", "Type / location"]] +
                                     [[row["edge_a"], row["edge_b"], "%s at (%.1f, %.1f)" %
                                       (row["kind"], row["coordinate"][0], row["coordinate"][1])]
                                      for row in diagnostics["crossings"]]))
            story.append(Spacer(1, 12))

        violation_rows = [["Constraint", "Severity", "Affected Units", "Penalty"]]
        for violation in layout.violations:
            violation_rows.append(
                [
                    violation.constraint_id,
                    violation.severity.value,
                    ", ".join(violation.affected_units),
                    "%.2f" % violation.penalty,
                ]
            )
        if len(violation_rows) == 1:
            violation_rows.append(["-", "-", "No violations", "0.00"])
        story.append(Paragraph("Violation Summary", styles["Heading2"]))
        story.append(self._table(violation_rows))
        story.append(Spacer(1, 12))
        story.append(Paragraph("Preliminary planning only. No hydraulic simulation, head-loss analysis, HAZOP, "
                               "regulatory verification, detailed piping, CAD/BIM or construction drawings.",
                               styles["Normal"]))
        for warning in diagnostics.get("warnings", []):
            story.append(Paragraph(str(warning), styles["Normal"]))

        if include_image:
            with tempfile.TemporaryDirectory() as temp_dir:
                image_path = Path(temp_dir) / "layout.png"
                self.renderer.save_png(layout, image_path, title=report_title)
                story.append(Spacer(1, 12))
                story.append(Image(str(image_path), width=480, height=360))
                doc.build(story)
        else:
            doc.build(story)

        return str(path)

    def _table(self, data):
        table = Table(data, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return table
